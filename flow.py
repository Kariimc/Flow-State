"""Whisper Flow clone — press a hotkey, speak, and the text appears in
whatever window you're using. Runs 100% locally.

Dictate with the same keys, three ways (defaults):
  * HOLD Ctrl+Win  — speak while holding, release to finish
  * TAP  Ctrl+Win  — recording stays on; stops after a pause or another tap
  * Ctrl+Win+Space — continuous mode: the mic stays open and text flows in
                     as you speak, until you press it again
Press Esc twice quickly to quit.
"""

import ctypes
import json
import math
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import winsound
from collections import deque
from datetime import datetime

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd

# ---------------- settings you can change ----------------
HOTKEY = "ctrl+windows"           # dictation key or combo (hold OR tap)
CONTINUOUS_HOTKEY = "ctrl+windows+space"  # toggles open-mic continuous mode
ENGINE = "moonshine"    # "moonshine" (fast, English) or "whisper" (slower, any language)
WHISPER_SIZE = "base"   # only used when ENGINE = "whisper"
LANGUAGE = None         # only used with whisper: None = auto-detect, or e.g. "en"
INJECTION = "paste"     # "paste" (fast, recommended) or "type" (character by character)
VERBATIM = False        # True = exact transcript, no cleanup at all
PRE_ROLL = 0.5          # seconds of audio kept from BEFORE you press the key
HOLD_THRESHOLD = 0.5    # held longer than this = walkie-talkie mode
AUTO_STOP = 1.5         # tap mode: seconds of silence that end the recording (0 = off)
MAX_RECORD = 45         # hard cap in seconds for hold/tap mode (continuous has none)
IDLE_FADE = 60          # pill fades away after this many idle seconds
HISTORY_FILE = "history.txt"        # every transcript is appended here ("" to disable)
DICTIONARY_FILE = "dictionary.txt"  # your words & shortcuts, see the file itself
TYPE_DELAY = 0.005      # only used when INJECTION = "type"
# ----------------------------------------------------------

# settings.json (edited from the Hub's Options tab) overrides the defaults
BASE_DIR_ = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR_, "settings.json")
TWEAKABLE = ["HOTKEY", "CONTINUOUS_HOTKEY", "ENGINE", "INJECTION", "VERBATIM",
             "AUTO_STOP", "MAX_RECORD", "IDLE_FADE"]


def load_settings() -> None:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        globals().update({k: data[k] for k in TWEAKABLE if k in data})
    except (OSError, ValueError):
        pass


def save_settings(data: dict) -> None:
    current = {}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            current = json.load(f)
    except (OSError, ValueError):
        pass
    current.update(data)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    # VERBATIM / INJECTION / AUTO_STOP / IDLE_FADE / MAX_RECORD are read at
    # use-time, so they apply immediately; HOTKEY and ENGINE need a restart
    globals().update({k: v for k, v in data.items() if k in TWEAKABLE})


load_settings()

SAMPLE_RATE = 16000
BLOCK = 1600  # 0.1 s of audio per callback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOONSHINE_DIR = os.path.join(BASE_DIR, "models", "sherpa-onnx-moonshine-base-en-int8")
VAD_MODEL = os.path.join(BASE_DIR, "models", "silero_vad.onnx")


def _label(combo: str) -> str:
    names = {"windows": "Win", "ctrl": "Ctrl", "alt": "Alt",
             "shift": "Shift", "space": "Space"}
    return "+".join(names.get(p.strip(), p.strip().upper())
                    for p in combo.split("+"))


HOTKEY_LABEL = _label(HOTKEY)
CONTINUOUS_LABEL = _label(CONTINUOUS_HOTKEY)

ui_events = queue.Queue()   # thread-safe channel to the overlay (main thread)
preroll = deque(maxlen=max(1, int(PRE_ROLL * SAMPLE_RATE / BLOCK)))
chunks = []
recording = False
continuous_mode = False
key_is_down = False
press_time = 0.0
busy = threading.Lock()
ACTIVE_ENGINE = None


# ---------------------------------------------------------------- engines

class MoonshineEngine:
    """Moonshine base int8 via sherpa-onnx — ~14x faster than Whisper on
    CPUs without AVX2, English only."""

    name = "Moonshine base (English)"

    def __init__(self):
        import sherpa_onnx

        p = MOONSHINE_DIR
        self.rec = sherpa_onnx.OfflineRecognizer.from_moonshine(
            preprocessor=os.path.join(p, "preprocess.onnx"),
            encoder=os.path.join(p, "encode.int8.onnx"),
            uncached_decoder=os.path.join(p, "uncached_decode.int8.onnx"),
            cached_decoder=os.path.join(p, "cached_decode.int8.onnx"),
            tokens=os.path.join(p, "tokens.txt"),
            num_threads=2,
        )

    def transcribe(self, audio: np.ndarray) -> str:
        s = self.rec.create_stream()
        s.accept_waveform(SAMPLE_RATE, audio)
        self.rec.decode_stream(s)
        return s.result.text.strip()


class WhisperEngine:
    name = "Whisper %s (multilingual)" % WHISPER_SIZE

    def __init__(self):
        from faster_whisper import WhisperModel

        self.model = WhisperModel(WHISPER_SIZE, device="cpu", compute_type="int8")

    def transcribe(self, audio: np.ndarray) -> str:
        segments, _ = self.model.transcribe(
            audio, language=LANGUAGE, vad_filter=True, beam_size=1
        )
        return " ".join(seg.text.strip() for seg in segments).strip()


def load_engine():
    if ENGINE == "moonshine":
        if os.path.isdir(MOONSHINE_DIR):
            return MoonshineEngine()
        print("Moonshine model folder missing (%s) — falling back to Whisper.\n"
              "See README.md for the model download command." % MOONSHINE_DIR)
    return WhisperEngine()


# ---------------------------------------------------------------- cleanup

FILLERS = re.compile(r"\s*\b(?:um+|uh+|uhm+|erm+|mm-hmm|hmm+)\b[,.]?", re.I)

SPOKEN_PUNCT = [
    (r"new paragraph", "\n\n"),
    (r"new line", "\n"),
    (r"full stop", "."),
    (r"period", "."),
    (r"comma", ","),
    (r"question mark", "?"),
    (r"exclamation (?:mark|point)", "!"),
    (r"semicolon", ";"),
    (r"colon", ":"),
]


def clean_text(text: str) -> str:
    if VERBATIM:
        return text
    text = FILLERS.sub("", text)
    for phrase, sym in SPOKEN_PUNCT:
        text = re.sub(r"[,.]?\s*\b%s\b[,.]?" % phrase, sym, text, flags=re.I)
    text = re.sub(r" *\n *", "\n", text)            # no stray spaces around newlines
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)   # no space before punctuation
    text = re.sub(r"[ \t]{2,}", " ", text)          # collapse double spaces
    text = re.sub(r"([,.;:?!])(?=\w)", r"\1 ", text)  # space after punctuation
    return text.strip()


# ---------------------------------------------------------------- dictionary

class Dictionary:
    """User-editable replacements from dictionary.txt: one `spoken => typed`
    rule per line. Fixes names/jargon the model mishears and expands
    shortcuts. Reloads automatically when the file is saved, and applies
    even in VERBATIM mode (it corrects recognition, not style)."""

    def __init__(self, path: str):
        self.path = path
        self.mtime = None
        self.rules = []

    def _reload_if_changed(self) -> None:
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            self.rules = []
            return
        if mtime == self.mtime:
            return
        self.mtime = mtime
        entries = read_rules(self.path)
        # longest triggers first so "wispr flow" wins over "wispr"
        entries.sort(key=lambda e: len(e[0]), reverse=True)
        self.rules = [
            (re.compile(r"\b%s\b" % re.escape(spoken), re.I), typed)
            for spoken, typed in entries
        ]

    def apply(self, text: str) -> str:
        self._reload_if_changed()
        for pattern, typed in self.rules:
            text = pattern.sub(lambda _m: typed, text)
        return text


def read_rules(path: str) -> list:
    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=>" not in line:
                    continue
                spoken, typed = (part.strip() for part in line.split("=>", 1))
                if spoken and typed:
                    entries.append((spoken, typed))
    except OSError:
        pass
    return entries


DICT_HEADER = """# Your personal dictionary. One rule per line:
#
#     what you say  =>  what gets typed
#
# Lines starting with # are ignored. Save the file (or use the Hub window)
# and the app picks up changes on your next dictation.
"""


def write_rules(path: str, rules: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(DICT_HEADER + "\n")
        for spoken, typed in rules:
            f.write("%s => %s\n" % (spoken, typed))


DICT = Dictionary(os.path.join(BASE_DIR, DICTIONARY_FILE))


# ------------------------------------------------- autostart & one instance

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "WhisperFlowClone"
IPC_PORT = 47821


def autostart_cmd() -> str:
    pyw = os.path.join(BASE_DIR, ".venv", "Scripts", "pythonw.exe")
    return '"%s" "%s"' % (pyw, os.path.join(BASE_DIR, "flow.py"))


def get_autostart() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
        return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                        winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_cmd())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def ipc_server() -> bool:
    """Claim the single-instance socket. Returns False if another copy of
    the app already owns it. The desktop icon uses this channel to tell the
    running app 'open your Hub' instead of starting a duplicate."""
    import socket

    srv = socket.socket()
    try:
        srv.bind(("127.0.0.1", IPC_PORT))
        srv.listen(2)
    except OSError:
        return False

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
                msg = conn.recv(64).decode("utf-8", "ignore").strip()
                conn.close()
                if msg in ("hub", "quit"):
                    ui_events.put(msg)
            except OSError:
                return

    threading.Thread(target=loop, daemon=True).start()
    return True


def ipc_send(msg: str) -> bool:
    import socket

    try:
        s = socket.create_connection(("127.0.0.1", IPC_PORT), timeout=1.5)
        s.sendall(msg.encode())
        s.close()
        return True
    except OSError:
        return False


ICON_FILE = os.path.join(BASE_DIR, "models", "flow.ico")


def make_icon() -> None:
    """Draw the app icon: the pill's waveform on paper, as a desktop icon."""
    if os.path.exists(ICON_FILE):
        return
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 10, 246, 246), radius=58, fill="#f8f5ee",
                        outline="#26231d", width=9)
    for gx in range(52, 246, 27):
        d.line((gx, 44, gx, 212), fill="#e3dccb", width=3)
    d.line((32, 128, 224, 128), fill="#e3dccb", width=3)
    for color, cycles, amp, width, phase in (
        ("#1f7f93", 3.0, 32, 11, 1.2),
        ("#e8912a", 2.0, 50, 13, 2.6),
        ("#c8371e", 1.2, 68, 15, 0.0),
    ):
        pts = []
        for i in range(0, 101, 2):
            x = 32 + (224 - 32) * i / 100
            y = 128 + amp * math.sin(2 * math.pi * cycles * i / 100 + phase)
            pts.append((x, y))
        d.line(pts, fill=color, width=width, joint="curve")
        ex, ey = pts[-1]
        d.rectangle((ex - 8, ey - 8, ex + 8, ey + 8), fill=color)
    d.ellipse((40, 40, 68, 68), fill="#c8371e")
    try:
        img.save(ICON_FILE, sizes=[(256, 256), (64, 64), (48, 48),
                                   (32, 32), (16, 16)])
    except OSError:
        pass


# ---------------------------------------------------------------- sounds

def _make_cue(path: str, freqs, dur: float = 0.14, vol: float = 0.16) -> None:
    """Write a soft sine chime (gentle fade in/out) — far kinder on the ears
    than winsound.Beep's harsh square wave."""
    import wave as wavemod

    sr = 44100
    n = int(sr * dur)
    t = np.arange(n) / sr
    tone = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    fade = min(n // 6, int(sr * 0.02))
    env = np.ones(n)
    env[:fade] = np.linspace(0, 1, fade)
    env[-fade:] = np.linspace(1, 0, fade)
    pcm = (tone * env * vol * 32767).astype(np.int16)
    with wavemod.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


CUE_START = os.path.join(BASE_DIR, "models", "cue_start.wav")
CUE_STOP = os.path.join(BASE_DIR, "models", "cue_stop.wav")


def make_cues() -> None:
    try:
        if not os.path.exists(CUE_START):
            _make_cue(CUE_START, (523.25, 783.99))   # soft C5+G5
        if not os.path.exists(CUE_STOP):
            _make_cue(CUE_STOP, (392.0, 523.25))     # soft G4+C5
    except OSError:
        pass


def beep(start: bool) -> None:
    path = CUE_START if start else CUE_STOP
    flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    try:
        winsound.PlaySound(path, flags)  # async: returns immediately
    except RuntimeError:
        pass


# ---------------------------------------------------------------- output

def inject(text: str) -> None:
    # If the user is still holding the hotkey (or any modifier), a synthetic
    # Ctrl+V would turn into Ctrl+Win+V etc. and paste nowhere — wait for
    # their fingers to leave the keyboard first.
    deadline = time.time() + 2.0
    while time.time() < deadline and any(
        keyboard.is_pressed(k) for k in ("ctrl", "windows", "alt", "shift")
    ):
        time.sleep(0.03)

    if INJECTION == "type":
        keyboard.write(text + " ", delay=TYPE_DELAY)
        return
    # Paste: put text on clipboard, Ctrl+V, then restore what was there.
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass  # clipboard held an image or was locked — nothing to restore
    pyperclip.copy(text + " ")
    keyboard.send("ctrl+v")
    if old is not None:
        # wait so even slow apps read the clipboard before we put it back
        time.sleep(1.2)
        try:
            pyperclip.copy(old)
        except Exception:
            pass


def log_history(text: str) -> None:
    if not HISTORY_FILE:
        return
    path = os.path.join(BASE_DIR, HISTORY_FILE)
    with open(path, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text))


def read_history() -> list:
    """Parse history.txt into (timestamp, text) pairs, newest first."""
    path = os.path.join(BASE_DIR, HISTORY_FILE or "history.txt")
    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("[") and "] " in line:
                    ts, _, text = line[1:].partition("] ")
                    entries.append((ts, text))
                elif entries:
                    entries[-1] = (entries[-1][0], entries[-1][1] + "\n" + line)
    except OSError:
        pass
    entries.reverse()
    return entries


# ---------------------------------------------------------------- spectrum

# one band per OCTAVE of your voice (80 Hz - 5 kHz); each octave drives
# its own curve in the overlay
SPEC_BANDS = 6
spectrum = np.zeros(SPEC_BANDS)
_spec_peak = 0.05  # adapts to your voice volume so curves stay lively
_hann = np.hanning(BLOCK).astype(np.float32)
_freqs = np.fft.rfftfreq(BLOCK, 1.0 / SAMPLE_RATE)
_edges = 80.0 * 2.0 ** np.arange(SPEC_BANDS + 1)  # 80,160,...,5120 Hz
_band_idx = [
    np.where((_freqs >= _edges[i]) & (_freqs < _edges[i + 1]))[0]
    for i in range(SPEC_BANDS)
]


def _update_spectrum(mono: np.ndarray) -> None:
    global spectrum, _spec_peak
    mag = np.abs(np.fft.rfft(mono * _hann))
    bands = np.array([mag[idx].mean() if len(idx) else 0.0 for idx in _band_idx])
    _spec_peak = max(_spec_peak * 0.97, float(bands.max()), 0.05)
    spectrum = np.clip(bands / _spec_peak, 0.0, 1.0)


# ------------------------------------------------- capture & transcription
#
# Responsiveness architecture: while you speak, Silero VAD slices your
# speech into utterances at natural pauses, and a background worker
# transcribes each utterance IMMEDIATELY — so when you stop, only the last
# couple of seconds still need processing instead of the whole recording.

vad_queue = queue.Queue()   # ("audio", block) | ("reset",) | ("flush", event)
seg_queue = queue.Queue()   # ("seg", samples) | ("end", event)
partials = []               # transcribed pieces of the current dictation
vad_enabled = False


def audio_callback(indata, frames, time_info, status):
    block = indata.copy()
    preroll.append(block)
    if recording:
        _update_spectrum(block[:, 0])
        if vad_enabled:
            vad_queue.put(("audio", block))
        if not continuous_mode:
            chunks.append(block)
            if len(chunks) == MAX_RECORD * 10:  # hard cap hit exactly once
                print("  (auto-stop: %ds limit)" % MAX_RECORD)
                threading.Thread(target=_finish, daemon=True).start()


def vad_worker() -> None:
    """Feeds Silero VAD, emits finished speech utterances to the
    transcriber, and auto-stops tap-mode recordings after silence."""
    import sherpa_onnx

    cfg = sherpa_onnx.VadModelConfig()
    cfg.silero_vad.model = VAD_MODEL
    cfg.silero_vad.threshold = 0.5
    cfg.silero_vad.min_silence_duration = 0.35
    cfg.silero_vad.max_speech_duration = 12  # keep utterances Moonshine-sized
    cfg.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(cfg, buffer_size_in_seconds=120)

    window = 512  # silero processes fixed 512-sample windows
    buf = np.zeros(0, dtype=np.float32)
    had_speech = False
    last_speech = 0.0

    def drain():
        while not vad.empty():
            seg_queue.put(("seg", np.array(vad.front.samples, dtype=np.float32)))
            vad.pop()

    while True:
        msg = vad_queue.get()
        kind = msg[0]
        if kind == "reset":
            vad.reset()
            buf = np.zeros(0, dtype=np.float32)
            had_speech = False
        elif kind == "flush":
            vad.flush()
            drain()
            seg_queue.put(("end", msg[1]))
            vad.reset()
            buf = np.zeros(0, dtype=np.float32)
            had_speech = False
        else:  # audio
            buf = np.concatenate([buf, msg[1].flatten()])
            while len(buf) >= window:
                vad.accept_waveform(buf[:window])
                buf = buf[window:]
            drain()
            if vad.is_speech_detected():
                had_speech = True
                last_speech = time.time()
            elif (AUTO_STOP > 0 and had_speech and recording
                  and not key_is_down and not continuous_mode
                  and time.time() - last_speech > AUTO_STOP):
                had_speech = False
                print("  (auto-stop: silence)")
                threading.Thread(target=_finish, daemon=True).start()


def transcriber_worker() -> None:
    """Transcribes utterances the moment the VAD finishes them — while the
    recording is still going. In continuous mode the text is pasted
    immediately; otherwise pieces collect until the dictation ends."""
    while True:
        kind, data = seg_queue.get()
        if kind == "end":
            data.set()
            continue
        if len(data) < SAMPLE_RATE * 0.25:
            continue
        t0 = time.time()
        text = ACTIVE_ENGINE.transcribe(data)
        if not text:
            continue
        print("  piece (%.1fs audio, %.1fs work): %s"
              % (len(data) / SAMPLE_RATE, time.time() - t0, text))
        if continuous_mode:
            piece = DICT.apply(clean_text(text))
            if piece:
                log_history(piece)
                inject(piece)
        else:
            partials.append(text)


def split_audio(audio: np.ndarray, max_s: int = 14) -> list:
    """Fallback path (VAD unavailable): cut at the quietest moment of each
    8-14s stretch so chunks stay a size the model handles well."""
    max_len = max_s * SAMPLE_RATE
    parts = []
    start = 0
    while len(audio) - start > max_len:
        win = audio[start + 8 * SAMPLE_RATE: start + max_len]
        frames = win[: len(win) // BLOCK * BLOCK].reshape(-1, BLOCK)
        quietest = int(np.argmin((frames ** 2).mean(axis=1)))
        cut = start + 8 * SAMPLE_RATE + (quietest + 1) * BLOCK
        parts.append(audio[start:cut])
        start = cut
    parts.append(audio[start:])
    return parts


def start_recording() -> None:
    global recording, chunks
    del partials[:]
    if vad_enabled:
        vad_queue.put(("reset",))
        for b in preroll:  # give the VAD the moment just before the press
            vad_queue.put(("audio", b))
    chunks = list(preroll)
    recording = True
    ui_events.put("continuous" if continuous_mode else "recording")
    beep(start=True)
    print("● Recording%s..." % (" (continuous)" if continuous_mode else ""))


def stop_and_transcribe() -> None:
    global recording
    recording = False
    ui_events.put("transcribing")
    beep(start=False)
    try:
        t0 = time.time()
        if vad_enabled:
            done = threading.Event()
            vad_queue.put(("flush", done))
            done.wait(timeout=120)
            raw = " ".join(partials).strip()
            if not raw and chunks:  # VAD heard nothing; try the raw buffer
                audio = np.concatenate(chunks).flatten()
                if len(audio) >= SAMPLE_RATE * 0.3:
                    raw = " ".join(
                        filter(None, (ACTIVE_ENGINE.transcribe(p)
                                      for p in split_audio(audio)))
                    )
        else:
            if not chunks:
                print("No audio captured.")
                return
            audio = np.concatenate(chunks).flatten()
            if len(audio) < SAMPLE_RATE * 0.3:
                print("Recording too short, ignored.")
                return
            raw = " ".join(
                filter(None, (ACTIVE_ENGINE.transcribe(p)
                              for p in split_audio(audio)))
            )
        text = DICT.apply(clean_text(raw))
        if not text:
            print("Heard nothing intelligible.")
            return
        print("→ (%.1fs wait) %s" % (time.time() - t0, text))
        log_history(text)
        inject(text)
    finally:
        ui_events.put("idle")


def _finish() -> None:
    with busy:
        if recording and not continuous_mode:
            stop_and_transcribe()


def end_continuous() -> None:
    global recording, continuous_mode
    with busy:
        if not continuous_mode:
            return
        recording = False
        continuous_mode = False
        ui_events.put("transcribing")
        beep(start=False)
        if vad_enabled:
            done = threading.Event()
            vad_queue.put(("flush", done))
            done.wait(timeout=120)
            # the transcriber injects any final pieces itself; give the
            # queue a beat to empty
            deadline = time.time() + 60
            while not seg_queue.empty() and time.time() < deadline:
                time.sleep(0.1)
        ui_events.put("idle")
        print("■ Continuous mode off.")


def toggle_continuous() -> None:
    global continuous_mode
    if continuous_mode:
        threading.Thread(target=end_continuous, daemon=True).start()
        return
    if not vad_enabled:
        print("Continuous mode needs the VAD model (models/silero_vad.onnx).")
        return
    continuous_mode = True
    if recording:
        # already dictating via Ctrl+Win: lock the mic open instead
        ui_events.put("continuous")
        print("● Continuous mode on (mic locked open).")
    else:
        start_recording()


# ---------------------------------------------------------------- hotkeys

def on_key_down() -> None:
    global key_is_down, press_time
    if key_is_down or continuous_mode:
        return  # auto-repeat, or continuous mode owns the mic
    key_is_down = True
    press_time = time.time()
    if not recording:
        start_recording()
    else:
        threading.Thread(target=_finish, daemon=True).start()


def on_key_up() -> None:
    global key_is_down
    if not key_is_down:
        return  # a lone modifier release (e.g. Ctrl+C while dictating)
    key_is_down = False
    if continuous_mode:
        return
    if recording and time.time() - press_time >= HOLD_THRESHOLD:
        threading.Thread(target=_finish, daemon=True).start()


def register_hotkeys() -> None:
    parts = [p.strip() for p in HOTKEY.lower().split("+")]
    if len(parts) == 1:
        keyboard.on_press_key(parts[0], lambda e: on_key_down(), suppress=True)
        keyboard.on_release_key(parts[0], lambda e: on_key_up(), suppress=True)
    else:
        keyboard.add_hotkey(HOTKEY, on_key_down)
        for p in dict.fromkeys(parts):
            keyboard.on_release_key(p, lambda e: on_key_up())
    keyboard.add_hotkey(CONTINUOUS_HOTKEY, toggle_continuous)


# ---------------------------------------------------------------- tray icon

TRAY = None
TRAY_ICONS = {}


def start_tray() -> None:
    global TRAY, TRAY_ICONS
    import pystray
    from PIL import Image, ImageDraw

    def draw(color):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((24, 6, 40, 36), radius=8, fill=color)
        d.arc((16, 18, 48, 46), 0, 180, fill=color, width=5)
        d.line((32, 46, 32, 58), fill=color, width=5)
        return img

    TRAY_ICONS = {
        "idle": draw("#e8e2d4"),
        "recording": draw("#c8371e"),
        "continuous": draw("#c8371e"),
        "transcribing": draw("#e8912a"),
    }

    menu = pystray.Menu(
        pystray.MenuItem("Hold or tap %s · %s = open mic"
                         % (HOTKEY_LABEL, CONTINUOUS_LABEL),
                         None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Hub (history & dictionary)",
                         lambda icon, item: ui_events.put("hub")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda icon, item: ui_events.put("quit")),
    )
    TRAY = pystray.Icon("whisper-flow-clone", TRAY_ICONS["idle"],
                        "Whisper Flow Clone", menu)
    TRAY.run_detached()


def set_tray_state(state: str) -> None:
    if TRAY and TRAY_ICONS:
        TRAY.icon = TRAY_ICONS.get(state, TRAY_ICONS["idle"])


# ---------------------------------------------------------------- theme

INK = "#26231d"        # near-black warm ink
PAPER = "#f8f5ee"      # warm paper white
PAPER_DIM = "#efeadd"
HAIRLINE = "#e3dccb"
RIM = "#b9b1a0"
VERMILION = "#c8371e"
AMBER = "#e8912a"
TEAL = "#1f7f93"


# ---------------------------------------------------------------- overlay

class Overlay:
    """The floating bar. A paper-white pill with six thin ink curves — one
    per octave of your voice — drawn like a precision instrument chart.
    Stays visible after use and fades away after IDLE_FADE seconds. Drag to
    move; snaps to screen anchors; never steals keyboard focus."""

    W, H = 190, 26
    CURVE_COLORS = ["#c8371e", "#e8912a", "#1f7f93",
                    "#d9a53f", "#a32c14", "#4d9fb0"]
    CURVE_WIDTHS = [1.7, 1.3, 1.3, 1.1, 1.0, 1.0]
    CURVE_CYCLES = [1.3, 2.1, 3.2, 4.4, 5.7, 7.2]   # higher octave = more waves
    CURVE_SPEED = [0.10, -0.14, 0.17, -0.21, 0.26, -0.31]
    DOTS = {"recording": VERMILION, "continuous": VERMILION,
            "transcribing": AMBER, "idle": "#b6afa2"}
    SNAP_DIST = 150
    POS_FILE = os.path.join(BASE_DIR, "overlay_pos.txt")

    def __init__(self):
        self.state = None
        self.phase = 0.0
        self.idle_since = None
        self.fading = False
        self.pos = self._load_pos()
        self.hub = None
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        # everything magenta becomes see-through -> true rounded pill
        self.root.attributes("-transparentcolor", "#ff00ff")
        self.root.configure(bg="#ff00ff")
        self.canvas = tk.Canvas(self.root, width=self.W, height=self.H + 3,
                                bg="#ff00ff", highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)

        # static art, drawn ONCE — animation only moves coordinates
        def capsule(x0, y0, x1, y1, fill):
            cr = (y1 - y0) / 2
            self.canvas.create_oval(x0, y0, x0 + 2 * cr, y1, fill=fill, outline="")
            self.canvas.create_oval(x1 - 2 * cr, y0, x1, y1, fill=fill, outline="")
            self.canvas.create_rectangle(x0 + cr, y0, x1 - cr, y1,
                                         fill=fill, outline="")

        capsule(0, 2.5, self.W, self.H + 2.5, "#0b0c0e")   # drop shadow
        capsule(0, 0, self.W, self.H, RIM)                  # rim
        capsule(1.2, 1.2, self.W - 1.2, self.H - 1.2, PAPER)  # paper body
        mid = self.H // 2
        # graph-paper hairlines, like the reference artwork
        for gx in range(26, self.W - 10, 11):
            self.canvas.create_line(gx, 4, gx, self.H - 4, fill=HAIRLINE)
        self.canvas.create_line(20, mid, self.W - 7, mid, fill=HAIRLINE)
        # microphone glyph (state indicator) — crisp vector art in place of the
        # old status dot. Recolours by state; drawn once, never rebuilt.
        cx, _c = 11.0, self.DOTS["idle"]
        self._mic = [                                      # (item, colour option)
            (self.canvas.create_oval(cx - 2.4, 4, cx + 2.4, 13,
                                     fill=_c, outline=""), "fill"),      # capsule
            (self.canvas.create_arc(cx - 4.5, 6, cx + 4.5, 16,
                                    start=180, extent=180, style=tk.ARC,
                                    outline=_c, width=1.3), "outline"),  # cradle
            (self.canvas.create_line(cx, 16, cx, 19.5,
                                     fill=_c, width=1.3), "fill"),       # stem
            (self.canvas.create_line(cx - 3, 20, cx + 3, 20,
                                     fill=_c, width=1.3), "fill"),       # base
        ]
        # six octave curves + their little plotted-endpoint squares
        self.xs = list(range(21, self.W - 6, 4))
        self.k2pi = [2 * math.pi * c / len(self.xs) for c in self.CURVE_CYCLES]
        self.amps = [0.6] * SPEC_BANDS
        self.phases = [i * 1.7 for i in range(SPEC_BANDS)]
        flat = []
        for x in self.xs:
            flat += [x, mid]
        self.curves = [None] * SPEC_BANDS
        self.tips = [None] * SPEC_BANDS
        for i in reversed(range(SPEC_BANDS)):  # low octaves drawn on top
            self.curves[i] = self.canvas.create_line(
                *flat, fill=self.CURVE_COLORS[i],
                width=self.CURVE_WIDTHS[i], smooth=True,
            )
            tx = self.xs[-1]
            self.tips[i] = self.canvas.create_rectangle(
                tx - 1, mid - 1, tx + 2, mid + 2,
                fill=self.CURVE_COLORS[i], outline="",
            )
        # never steal focus from the window being dictated into
        self.root.update_idletasks()
        try:
            hwnd = (ctypes.windll.user32.GetParent(self.root.winfo_id())
                    or self.root.winfo_id())
            GWL_EXSTYLE = -20
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | 0x08000000 | 0x00000080
            )  # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        except Exception:
            pass
        self._place()
        self.root.after(100, self._poll)
        self.root.after(30, self._animate)

    # ---- position, drag & snap

    def _work_area(self):
        class RECT(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                        ("r", ctypes.c_long), ("b", ctypes.c_long)]

        rect = RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0,
                                                      ctypes.byref(rect), 0):
            return rect.l, rect.t, rect.r, rect.b
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _anchors(self):
        l, t, r, b = self._work_area()
        cx = l + (r - l - self.W) // 2
        by = b - self.H - 8   # Wispr Flow's spot: hugging the taskbar
        return {
            "bottom-center": (cx, by),
            "bottom-left": (l + 16, by),
            "bottom-right": (r - self.W - 16, by),
            "top-center": (cx, t + 8),
        }

    def _load_pos(self):
        try:
            kind, _, val = open(self.POS_FILE).read().strip().partition("=")
            if kind == "anchor":
                return val
            if kind == "xy":
                x, y = val.split(",")
                return (int(x), int(y))
        except (OSError, ValueError):
            pass
        return "bottom-center"

    def _save_pos(self):
        try:
            with open(self.POS_FILE, "w") as f:
                if isinstance(self.pos, str):
                    f.write("anchor=%s" % self.pos)
                else:
                    f.write("xy=%d,%d" % self.pos)
        except OSError:
            pass

    def _place(self):
        anchors = self._anchors()
        if isinstance(self.pos, str):
            x, y = anchors.get(self.pos, anchors["bottom-center"])
        else:
            x, y = self.pos
        self.root.geometry("%dx%d+%d+%d" % (self.W, self.H + 3, x, y))

    def _drag_start(self, e):
        self._grab = (e.x, e.y)

    def _drag_move(self, e):
        x = self.root.winfo_pointerx() - self._grab[0]
        y = self.root.winfo_pointery() - self._grab[1]
        self.root.geometry("+%d+%d" % (x, y))

    def _drag_end(self, e):
        x, y = self.root.winfo_x(), self.root.winfo_y()
        name, (ax, ay) = min(
            self._anchors().items(),
            key=lambda a: (a[1][0] - x) ** 2 + (a[1][1] - y) ** 2,
        )
        if ((ax - x) ** 2 + (ay - y) ** 2) ** 0.5 <= self.SNAP_DIST:
            self.pos = name       # close to an anchor spot: snap into it
        else:
            self.pos = (x, y)     # park it exactly where you dropped it
        self._save_pos()
        self._place()

    # ---- appearing, fading

    def _show(self, state):
        self.state = state
        self.fading = False
        self.idle_since = time.time() if state == "idle" else None
        for item, opt in self._mic:
            self.canvas.itemconfig(item, {opt: self.DOTS[state]})
        try:
            self.root.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self._place()
        self.root.deiconify()
        set_tray_state(state)

    def _fade_step(self, alpha):
        if not self.fading:
            return
        if alpha <= 0:
            self.root.withdraw()
            try:
                self.root.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            self.fading = False
            self.state = None
            return
        try:
            self.root.attributes("-alpha", alpha)
        except tk.TclError:
            self.root.withdraw()
            self.fading = False
            self.state = None
            return
        self.root.after(40, lambda: self._fade_step(alpha - 0.08))

    # ---- animation

    def _redraw_curves(self):
        c, mid = self.canvas, self.H // 2
        for i in range(SPEC_BANDS):
            a, k, ph = self.amps[i], self.k2pi[i], self.phases[i]
            coords = []
            for n, x in enumerate(self.xs):
                coords.append(x)
                coords.append(mid + a * math.sin(k * n + ph))
            c.coords(self.curves[i], *coords)
            ty = coords[-1]
            tx = self.xs[-1]
            c.coords(self.tips[i], tx - 1, ty - 1.5, tx + 2, ty + 1.5)

    def _animate(self):
        max_a = self.H / 2 - 3
        if self.state in ("recording", "continuous"):
            # every octave drives its own curve; sqrt lifts the quiet
            # high octaves so the whole chord stays visible
            for i in range(SPEC_BANDS):
                target = 0.5 + math.sqrt(float(spectrum[i])) * max_a
                self.amps[i] += (target - self.amps[i]) * 0.38
                self.phases[i] += self.CURVE_SPEED[i]
            self._redraw_curves()
        elif self.state == "transcribing":
            self.phase += 0.22
            for i in range(SPEC_BANDS):
                self.amps[i] = 1.6 + 1.4 * (1 + math.sin(self.phase * 0.8 + i * 0.9)) / 2
                self.phases[i] += self.CURVE_SPEED[i] * 0.6
            self._redraw_curves()
        elif self.state == "idle":
            # near-flat resting trace, barely breathing
            self.phase += 0.05
            for i in range(SPEC_BANDS):
                self.amps[i] += (0.8 - self.amps[i]) * 0.15
                self.phases[i] += self.CURVE_SPEED[i] * 0.25
            self._redraw_curves()
            if (self.idle_since and not self.fading
                    and time.time() - self.idle_since > IDLE_FADE):
                self.fading = True
                self._fade_step(1.0)
        self.root.after(30, self._animate)

    # ---- event pump

    def _poll(self):
        try:
            while True:
                state = ui_events.get_nowait()
                if state == "quit":
                    if TRAY:
                        TRAY.stop()
                    self.root.destroy()
                    os._exit(0)
                elif state == "hub":
                    self._open_hub()
                elif state in self.DOTS:
                    self._show(state)
                else:  # "hide"
                    self.root.withdraw()
                    self.state = None
                    set_tray_state("idle")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _open_hub(self):
        if self.hub is None or not self.hub.top.winfo_exists():
            self.hub = Hub(self.root)
        self.hub.show()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------- hub

class Hub:
    """History, Dictionary & Options window. Ink on paper: search either
    list, click a history entry to copy it, add/remove dictionary rules
    inline, and tweak the app's behavior."""

    def __init__(self, root):
        self.top = tk.Toplevel(root)
        self.top.title("Flow Hub")
        self.top.geometry("580x570")
        self.top.configure(bg=PAPER)
        self.top.minsize(500, 420)
        try:
            self.top.iconbitmap(ICON_FILE)
        except tk.TclError:
            pass
        self.tab = "history"
        self.entries = []
        self.rules = []

        header = tk.Frame(self.top, bg=PAPER)
        header.pack(fill="x", padx=18, pady=(14, 6))
        tk.Label(header, text="Flow Hub", font=("Georgia", 17, "bold"),
                 bg=PAPER, fg=INK).pack(side="left")
        self.status = tk.Label(header, text="", font=("Segoe UI", 9),
                               bg=PAPER, fg=VERMILION)
        self.status.pack(side="right")

        tabs = tk.Frame(self.top, bg=PAPER)
        tabs.pack(fill="x", padx=18)
        self.tab_btns = {}
        for key, label in (("history", "History"),
                           ("dictionary", "Dictionary"),
                           ("options", "Options")):
            b = tk.Label(tabs, text=label, font=("Segoe UI Semibold", 11),
                         bg=PAPER, fg=INK, padx=2, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 18))
            b.bind("<Button-1>", lambda e, k=key: self.switch(k))
            self.tab_btns[key] = b
        tk.Frame(self.top, bg=RIM, height=1).pack(fill="x", padx=18)

        self.search_row = tk.Frame(self.top, bg=PAPER)
        self.search_row.pack(fill="x", padx=18, pady=8)
        self.query = tk.StringVar()
        self.query.trace_add("write", lambda *a: self.refresh())
        tk.Label(self.search_row, text="Search", font=("Segoe UI", 9),
                 bg=PAPER, fg="#8a8272").pack(side="left", padx=(0, 8))
        tk.Entry(self.search_row, textvariable=self.query, font=("Segoe UI", 10),
                 bg=PAPER_DIM, fg=INK, relief="flat", insertbackground=INK,
                 highlightthickness=1, highlightbackground=HAIRLINE,
                 highlightcolor=VERMILION).pack(fill="x", expand=True, ipady=4)

        self.body = tk.Frame(self.top, bg=PAPER)
        self.body.pack(fill="both", expand=True, padx=18, pady=(0, 6))
        self.listbox = tk.Listbox(
            self.body, font=("Segoe UI", 10), bg=PAPER, fg=INK, relief="flat",
            highlightthickness=1, highlightbackground=HAIRLINE,
            selectbackground=PAPER_DIM, selectforeground=VERMILION,
            activestyle="none",
        )
        sb = tk.Scrollbar(self.body, command=self.listbox.yview)
        self.listbox.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        # dictionary editor row
        self.editor = tk.Frame(self.top, bg=PAPER)
        self.say_var, self.type_var = tk.StringVar(), tk.StringVar()

        def entry(parent, var, width):
            return tk.Entry(parent, textvariable=var, width=width,
                            font=("Segoe UI", 10), bg=PAPER_DIM, fg=INK,
                            relief="flat", insertbackground=INK,
                            highlightthickness=1, highlightbackground=HAIRLINE,
                            highlightcolor=VERMILION)

        entry(self.editor, self.say_var, 16).pack(side="left", ipady=4)
        tk.Label(self.editor, text="→", bg=PAPER, fg=INK,
                 font=("Segoe UI", 11)).pack(side="left", padx=6)
        entry(self.editor, self.type_var, 22).pack(side="left", ipady=4)

        def button(parent, text, cmd):
            b = tk.Label(parent, text=text, font=("Segoe UI Semibold", 10),
                         bg=INK, fg=PAPER, padx=12, pady=4, cursor="hand2")
            b.bind("<Button-1>", lambda e: cmd())
            return b

        button(self.editor, "Add rule", self.add_rule).pack(side="left",
                                                            padx=(10, 6))
        button(self.editor, "Delete selected", self.delete_rule).pack(side="left")

        # ---- options tab
        self.options = tk.Frame(self.top, bg=PAPER)
        self.autostart_var = tk.BooleanVar(value=get_autostart())
        self.verbatim_var = tk.BooleanVar(value=bool(VERBATIM))
        self.inject_var = tk.StringVar(value=INJECTION)
        self.engine_var = tk.StringVar(value=ENGINE)
        self.autostop_var = tk.StringVar(value=str(AUTO_STOP))
        self.fade_var = tk.StringVar(value=str(IDLE_FADE))
        self.maxrec_var = tk.StringVar(value=str(MAX_RECORD))
        self.hotkey_var = tk.StringVar(value=HOTKEY)

        def row(label):
            f = tk.Frame(self.options, bg=PAPER)
            f.pack(fill="x", pady=3)
            tk.Label(f, text=label, font=("Segoe UI", 10), bg=PAPER, fg=INK,
                     width=26, anchor="w").pack(side="left")
            return f

        def check(parent, var, text=""):
            tk.Checkbutton(parent, text=text, variable=var, bg=PAPER, fg=INK,
                           font=("Segoe UI", 10), activebackground=PAPER,
                           selectcolor=PAPER_DIM,
                           highlightthickness=0).pack(side="left")

        def radios(parent, var, values):
            for val, label in values:
                tk.Radiobutton(parent, text=label, value=val, variable=var,
                               bg=PAPER, fg=INK, font=("Segoe UI", 10),
                               activebackground=PAPER, selectcolor=PAPER_DIM,
                               highlightthickness=0).pack(side="left",
                                                          padx=(0, 10))

        check(row("Start with Windows"), self.autostart_var)
        check(row("Verbatim (no cleanup)"), self.verbatim_var)
        radios(row("Insert text by"), self.inject_var,
               [("paste", "pasting (fast)"), ("type", "typing (compatible)")])
        f = row("Auto-stop after silence (s)")
        entry(f, self.autostop_var, 6).pack(side="left", ipady=2)
        tk.Label(f, text="0 = off", font=("Segoe UI", 9), bg=PAPER,
                 fg="#8a8272").pack(side="left", padx=8)
        entry(row("Pill fades after idle (s)"), self.fade_var, 6).pack(
            side="left", ipady=2)
        entry(row("Max recording (s)"), self.maxrec_var, 6).pack(
            side="left", ipady=2)
        radios(row("Engine  (restart to apply)"), self.engine_var,
               [("moonshine", "Moonshine (EN, fast)"),
                ("whisper", "Whisper (any language)")])
        entry(row("Hotkey  (restart to apply)"), self.hotkey_var, 18).pack(
            side="left", ipady=2)
        foot = tk.Frame(self.options, bg=PAPER)
        foot.pack(fill="x", pady=(12, 0))
        button(foot, "Save options", self.save_options).pack(side="left")
        tk.Label(self.options,
                 text="Continuous mode: %s. Everything except Engine and "
                      "Hotkey applies immediately." % CONTINUOUS_LABEL,
                 font=("Segoe UI", 9), bg=PAPER, fg="#8a8272",
                 anchor="w", justify="left", wraplength=480).pack(
            fill="x", pady=(10, 0))

        self.hint = tk.Label(self.top, text="", font=("Segoe UI", 9),
                             bg=PAPER, fg="#8a8272", anchor="w")
        self.hint.pack(fill="x", padx=18, pady=(0, 10))
        self.switch("history")

    def show(self):
        self.refresh()
        self.top.deiconify()
        self.top.lift()

    def switch(self, tab):
        self.tab = tab
        for key, b in self.tab_btns.items():
            b.config(fg=VERMILION if key == tab else INK)
        self.editor.pack_forget()
        self.options.pack_forget()
        if tab == "options":
            self.search_row.pack_forget()
            self.body.pack_forget()
            self.options.pack(fill="both", expand=True, padx=18, pady=10,
                              before=self.hint)
            self.hint.config(text="")
            return
        self.search_row.pack(fill="x", padx=18, pady=8, before=self.hint)
        self.body.pack(fill="both", expand=True, padx=18, pady=(0, 6),
                       before=self.hint)
        if tab == "dictionary":
            self.editor.pack(fill="x", padx=18, pady=(0, 4), before=self.hint)
            self.hint.config(text="Select a rule to delete it, or type a new "
                                  "one and press Add rule.")
        else:
            self.hint.config(text="Click an entry to copy it to the clipboard.")
        self.refresh()

    def save_options(self):
        try:
            autostop = max(0.0, float(self.autostop_var.get()))
            fade = max(5, int(float(self.fade_var.get())))
            maxrec = max(5, int(float(self.maxrec_var.get())))
        except ValueError:
            self.flash("Numbers only in the seconds boxes")
            return
        hot = self.hotkey_var.get().strip().lower() or "ctrl+windows"
        save_settings({
            "VERBATIM": bool(self.verbatim_var.get()),
            "INJECTION": self.inject_var.get(),
            "AUTO_STOP": autostop,
            "IDLE_FADE": fade,
            "MAX_RECORD": maxrec,
            "ENGINE": self.engine_var.get(),
            "HOTKEY": hot,
        })
        try:
            set_autostart(bool(self.autostart_var.get()))
        except OSError:
            self.flash("Saved, but couldn't change autostart")
            return
        self.flash("Saved (engine & hotkey changes apply after restart)")

    def refresh(self):
        q = self.query.get().lower()
        self.listbox.delete(0, "end")
        if self.tab == "history":
            self.entries = [e for e in read_history()
                            if q in e[1].lower() or q in e[0]]
            for ts, text in self.entries:
                one = " ".join(text.split())
                if len(one) > 70:
                    one = one[:69] + "…"
                self.listbox.insert("end", " %s   %s" % (ts[5:16], one))
        else:
            self.rules = [r for r in read_rules(DICT.path)
                          if q in r[0].lower() or q in r[1].lower()]
            for spoken, typed in self.rules:
                self.listbox.insert("end", " %s  →  %s" % (spoken, typed))

    def on_select(self, _e):
        if self.tab != "history":
            return
        sel = self.listbox.curselection()
        if not sel:
            return
        pyperclip.copy(self.entries[sel[0]][1])
        self.flash("Copied to clipboard")

    def add_rule(self):
        spoken = self.say_var.get().strip()
        typed = self.type_var.get().strip()
        if not spoken or not typed:
            self.flash("Fill in both boxes first")
            return
        rules = [r for r in read_rules(DICT.path) if r[0].lower() != spoken.lower()]
        rules.append((spoken, typed))
        write_rules(DICT.path, rules)
        self.say_var.set("")
        self.type_var.set("")
        self.refresh()
        self.flash("Rule saved")

    def delete_rule(self):
        sel = self.listbox.curselection()
        if self.tab != "dictionary" or not sel:
            self.flash("Select a rule first")
            return
        victim = self.rules[sel[0]]
        rules = [r for r in read_rules(DICT.path) if r != victim]
        write_rules(DICT.path, rules)
        self.refresh()
        self.flash("Rule deleted")

    def flash(self, msg):
        self.status.config(text=msg)
        self.top.after(1800, lambda: self.status.config(text=""))


# ---------------------------------------------------------------- main

def main() -> None:
    global vad_enabled, ACTIVE_ENGINE
    # Status prints use "●"/"→". Under a redirected/piped stdout Windows
    # picks cp1252 (strict), so those chars raise UnicodeEncodeError and silently
    # kill the recording/finish worker threads. Force UTF-8 with replacement so a
    # print can never take a thread (and the dictation) down.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    want_hub = "--hub" in sys.argv
    if not ipc_server():
        # another copy is already running — ask it to show its Hub instead
        ipc_send("hub")
        print("Already running; opened the Hub in the existing instance.")
        return
    try:  # per-monitor DPI awareness: crisp pixels, correct overlay placement
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    make_cues()
    make_icon()
    print("Loading speech model (first run may download it)...")
    ACTIVE_ENGINE = load_engine()
    print("Engine: %s" % ACTIVE_ENGINE.name)
    # first inference pays a ~8s one-time warm-up cost — pay it now, at
    # startup, instead of on the user's first dictation
    ACTIVE_ENGINE.transcribe(np.zeros(SAMPLE_RATE // 2, dtype=np.float32))
    print("Engine warmed up.")

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, blocksize=BLOCK, channels=1,
        dtype="float32", callback=audio_callback,
    )
    stream.start()

    if os.path.exists(VAD_MODEL):
        vad_enabled = True
        threading.Thread(target=vad_worker, daemon=True).start()
        threading.Thread(target=transcriber_worker, daemon=True).start()
        print("Live transcription: on (speech is transcribed while you talk)")

    start_tray()
    register_hotkeys()

    # Quit on double-Esc so a single stray Esc doesn't kill the app
    last_esc = [0.0]

    def on_esc():
        now = time.time()
        if now - last_esc[0] < 0.6:
            print("Bye!")
            ui_events.put("quit")
        last_esc[0] = now

    keyboard.add_hotkey("esc", on_esc)

    print("Ready. Hold or tap %s to dictate; %s = continuous mode. "
          "Esc twice to quit." % (HOTKEY_LABEL, CONTINUOUS_LABEL))
    if want_hub:
        ui_events.put("hub")
    Overlay().run()  # the overlay owns the main thread (tkinter requirement)


if __name__ == "__main__":
    main()
