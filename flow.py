"""Flow State â€” press a hotkey, speak, and the text appears in
whatever window you're using. Runs 100% locally.

Dictate with the same keys, three ways (defaults):
  * HOLD Ctrl+Win  â€” speak while holding, release to finish
  * TAP  Ctrl+Win  â€” recording stays on; stops after a pause or another tap
  * Ctrl+Win+Space â€” continuous mode: the mic stays open and text flows in
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
from pathlib import Path
from tkinter import filedialog, messagebox

import keyboard
import numpy as np
import pyperclip

from flow_features import (
    PROFILE_PRESETS,
    HistoryStore,
    apply_vocabulary,
    choose_profile,
    polish_text,
    read_wav,
    transform_selected_text,
)
from flow_hub import Hub as ModernHub

# ---------------- settings you can change ----------------
HOTKEY = "ctrl+windows"           # dictation key or combo (hold OR tap)
CONTINUOUS_HOTKEY = "ctrl+windows+space"  # toggles open-mic continuous mode
COMMAND_HOTKEY = "ctrl+windows+alt"       # selected-text voice command toggle
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
POLISH = True           # local cleanup, self-correction, lists, and app profiles
PROFILE = "auto"        # auto, default, messages, email, notes, or coding
APP_PROFILES = {}       # optional {"process-name": "profile"} overrides
MICROPHONE = None       # None = system default, otherwise a sounddevice index
SOUND_CUES = True
SAVE_AUDIO = True       # retain WAV audio beside searchable history
HISTORY_DAYS = 30       # 0 = keep forever
THEME = "light"         # light or dark Hub theme
OPEN_HUB = False        # show the Hub after startup
# ----------------------------------------------------------

# settings.json (edited from the Hub's Options tab) overrides the defaults
BASE_DIR_ = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR_, "settings.json")
TWEAKABLE = [
    "HOTKEY", "CONTINUOUS_HOTKEY", "COMMAND_HOTKEY", "ENGINE", "INJECTION",
    "VERBATIM", "AUTO_STOP", "MAX_RECORD", "IDLE_FADE", "POLISH", "PROFILE",
    "APP_PROFILES", "MICROPHONE", "SOUND_CUES", "SAVE_AUDIO", "HISTORY_DAYS",
    "THEME", "OPEN_HUB",
]


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
DATA_DIR = os.path.join(BASE_DIR, "data")
HISTORY = HistoryStore(DATA_DIR)


def active_process_name() -> str:
    """Return the foreground executable name using Windows APIs only."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not handle:
            return ""
        try:
            size = ctypes.c_ulong(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(size)
            ):
                return os.path.basename(buf.value)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        pass
    return ""


def current_profile() -> str:
    if PROFILE in PROFILE_PRESETS:
        return PROFILE
    return choose_profile(active_process_name(), APP_PROFILES)


def _label(combo: str) -> str:
    names = {"windows": "Win", "ctrl": "Ctrl", "alt": "Alt",
             "shift": "Shift", "space": "Space"}
    return "+".join(names.get(p.strip(), p.strip().upper())
                    for p in combo.split("+"))


HOTKEY_LABEL = _label(HOTKEY)
CONTINUOUS_LABEL = _label(CONTINUOUS_HOTKEY)
COMMAND_LABEL = _label(COMMAND_HOTKEY)

ui_events = queue.Queue()   # thread-safe channel to the overlay (main thread)
preroll = deque(maxlen=max(1, int(PRE_ROLL * SAMPLE_RATE / BLOCK)))
chunks = []
recording = False
continuous_mode = False
command_mode = False
command_selection = ""
key_is_down = False
press_time = 0.0
busy = threading.Lock()
ACTIVE_ENGINE = None
sd = None
_audio_load_error = None


def load_audio_backend():
    """Load PortAudio only when startup actually needs microphone access."""
    global sd, _audio_load_error
    if sd is not None:
        return sd
    try:
        import sounddevice as backend
    except Exception as exc:
        _audio_load_error = exc
        return None
    sd = backend
    _audio_load_error = None
    return sd


# ---------------------------------------------------------------- engines

class MoonshineEngine:
    """Moonshine base int8 via sherpa-onnx â€” ~14x faster than Whisper on
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
        print("Moonshine model folder missing (%s) â€” falling back to Whisper.\n"
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


def finish_text(raw: str, profile: str | None = None) -> str:
    text = DICT.apply(clean_text(raw))
    text = apply_vocabulary(text, os.path.join(BASE_DIR, "vocabulary.txt"))
    if POLISH and not VERBATIM:
        text = polish_text(text, profile or current_profile())
    return text


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
APP_NAME = "FlowState"
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
TRAY_ICON_FILE = os.path.join(BASE_DIR, "models", "flow-tray.ico")


def _icon_font(size: int):
    from PIL import ImageFont

    for path in (
        r"C:\Windows\Fonts\georgiab.ttf",
        r"C:\Windows\Fonts\georgia.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def make_icon() -> None:
    """Draw the desktop and tray icons."""
    from PIL import Image, ImageDraw, ImageFilter

    scale = 4
    size = 256

    def downsample(image):
        return image.resize((size, size), Image.Resampling.LANCZOS)

    def rounded_mask(box_size, radius):
        mask = Image.new("L", box_size, 0)
        md = ImageDraw.Draw(mask)
        md.rounded_rectangle((0, 0, box_size[0] - 1, box_size[1] - 1),
                             radius=radius, fill=255)
        return mask

    big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    bd = ImageDraw.Draw(big)
    box = tuple(v * scale for v in (12, 12, 244, 244))
    shadow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(box, radius=54 * scale, fill=(28, 25, 20, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(5 * scale))
    big.alpha_composite(shadow, (0, 5 * scale))
    bd.rounded_rectangle(box, radius=54 * scale, fill="#f8f5ee",
                         outline="#26231d", width=8 * scale)
    for gx in range(48, 230, 26):
        width = 4 if gx % 52 == 0 else 2
        bd.line((gx * scale, 42 * scale, gx * scale, 214 * scale),
                fill="#ded6c6", width=width * scale)
    for gy in range(58, 208, 26):
        bd.line((34 * scale, gy * scale, 222 * scale, gy * scale),
                fill="#eee5d6", width=1 * scale)
    bd.line((30 * scale, 128 * scale, 226 * scale, 128 * scale),
            fill="#d3cabb", width=3 * scale)
    for color, cycles, amp, width, phase in (
        ("#1f7f93", 3.0, 26, 8, 1.2),
        ("#e8912a", 2.0, 40, 10, 2.6),
        ("#c8371e", 1.2, 54, 12, 0.0),
    ):
        pts = []
        for i in range(0, 101, 2):
            x = 34 + (224 - 34) * i / 100
            y = 132 + amp * math.sin(2 * math.pi * cycles * i / 100 + phase)
            pts.append((x * scale, y * scale))
        bd.line(pts, fill=color, width=width * scale, joint="curve")
    font = _icon_font(116 * scale)
    bd.text((29 * scale, 18 * scale), "F", fill=(38, 35, 29, 80), font=font)
    bd.text((25 * scale, 14 * scale), "F", fill="#c8371e", font=font)
    img = downsample(big)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((12, 12, 244, 244), radius=54, outline="#fdfbf6", width=2)
    try:
        img.save(ICON_FILE, sizes=[(256, 256), (64, 64), (48, 48),
                                   (32, 32), (16, 16)])
    except OSError:
        pass

    tray_big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    td = ImageDraw.Draw(tray_big)
    mic = "#8f8a80"
    dark = "#6f695e"
    light = "#b9b3a8"
    mic_shadow = Image.new("RGBA", tray_big.size, (0, 0, 0, 0))
    msd = ImageDraw.Draw(mic_shadow)
    msd.rounded_rectangle(tuple(v * scale for v in (84, 20, 172, 152)),
                          radius=42 * scale, fill=(0, 0, 0, 90))
    msd.arc(tuple(v * scale for v in (47, 83, 209, 195)), 0, 180,
            fill=(0, 0, 0, 90), width=23 * scale)
    msd.line(tuple(v * scale for v in (128, 193, 128, 226)),
             fill=(0, 0, 0, 90), width=23 * scale)
    msd.line(tuple(v * scale for v in (78, 226, 178, 226)),
             fill=(0, 0, 0, 90), width=23 * scale)
    mic_shadow = mic_shadow.filter(ImageFilter.GaussianBlur(3 * scale))
    tray_big.alpha_composite(mic_shadow, (0, 4 * scale))
    td.rounded_rectangle(tuple(v * scale for v in (84, 20, 172, 152)),
                         radius=42 * scale, fill=mic)
    td.line(tuple(v * scale for v in (108, 31, 108, 139)),
            fill=light, width=5 * scale)
    td.line(tuple(v * scale for v in (164, 43, 164, 132)),
            fill=dark, width=5 * scale)
    td.arc(tuple(v * scale for v in (47, 83, 209, 195)), 0, 180,
           fill=mic, width=23 * scale)
    td.arc(tuple(v * scale for v in (54, 91, 202, 187)), 0, 180,
           fill=light, width=5 * scale)
    td.line(tuple(v * scale for v in (128, 193, 128, 226)),
            fill=mic, width=23 * scale)
    td.line(tuple(v * scale for v in (78, 226, 178, 226)),
            fill=mic, width=23 * scale)
    small_font = _icon_font(70 * scale)
    td.text((109 * scale, 49 * scale), "F", fill=(38, 35, 29, 80),
            font=small_font)
    td.text((105 * scale, 45 * scale), "F", fill="#c8371e", font=small_font)
    tray = downsample(tray_big)
    try:
        tray.save(TRAY_ICON_FILE, sizes=[(256, 256), (64, 64), (48, 48),
                                         (32, 32), (16, 16)])
    except OSError:
        pass


# ---------------------------------------------------------------- sounds

def _make_cue(path: str, freqs, dur: float = 0.14, vol: float = 0.16) -> None:
    """Write a soft sine chime (gentle fade in/out) â€” far kinder on the ears
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
    if not SOUND_CUES:
        return
    path = CUE_START if start else CUE_STOP
    flags = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
    try:
        winsound.PlaySound(path, flags)  # async: returns immediately
    except RuntimeError:
        pass


# ---------------------------------------------------------------- output

def inject(text: str, trailing_space: bool = True) -> None:
    # If the user is still holding the hotkey (or any modifier), a synthetic
    # Ctrl+V would turn into Ctrl+Win+V etc. and paste nowhere â€” wait for
    # their fingers to leave the keyboard first.
    deadline = time.time() + 2.0
    while time.time() < deadline and any(
        keyboard.is_pressed(k) for k in ("ctrl", "windows", "alt", "shift")
    ):
        time.sleep(0.03)

    if INJECTION == "type":
        keyboard.write(text + (" " if trailing_space else ""), delay=TYPE_DELAY)
        return
    # Paste: put text on clipboard, Ctrl+V, then restore what was there.
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass  # clipboard held an image or was locked â€” nothing to restore
    pyperclip.copy(text + (" " if trailing_space else ""))
    keyboard.send("ctrl+v")
    if old is not None:
        # wait so even slow apps read the clipboard before we put it back
        time.sleep(1.2)
        try:
            pyperclip.copy(old)
        except Exception:
            pass


def log_history(
    text: str,
    *,
    original: str = "",
    audio: np.ndarray | None = None,
    duration: float = 0.0,
    latency: float = 0.0,
    engine: str = "",
    profile: str = "default",
    source: str = "dictation",
) -> dict:
    return HISTORY.add(
        original=original or text,
        final=text,
        duration=duration,
        latency=latency,
        engine=engine,
        profile=profile,
        audio=audio if SAVE_AUDIO else None,
        sample_rate=SAMPLE_RATE,
        source=source,
    )


def deliver_text(text: str, *, trailing_space: bool = True, **history) -> dict | None:
    """Insert completed text before slower, non-critical history persistence."""
    inject(text, trailing_space=trailing_space)
    try:
        return log_history(text, **history)
    except (OSError, ValueError) as exc:
        print("History save failed: %s" % exc)
        ui_events.put(("notice", "Text inserted; history save failed"))
        return None


def read_history() -> list:
    """Return (timestamp, text) pairs, including legacy history.txt."""
    modern = [
        (item.get("timestamp", "").replace("T", " "), item.get("final", ""))
        for item in HISTORY.read()
    ]
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
    return modern + entries


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
# transcribes each utterance IMMEDIATELY â€” so when you stop, only the last
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
    """Transcribes utterances the moment the VAD finishes them â€” while the
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
            profile = current_profile()
            piece = finish_text(text, profile)
            if piece:
                deliver_text(
                    piece,
                    original=text,
                    audio=data,
                    duration=len(data) / SAMPLE_RATE,
                    latency=time.time() - t0,
                    engine=getattr(ACTIVE_ENGINE, "name", ""),
                    profile=profile,
                    source="continuous",
                )
        else:
            partials.append(text)
            ui_events.put(("partial", text))


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


def transcribe_audio(audio: np.ndarray) -> str:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if len(samples) < SAMPLE_RATE * 0.25:
        return ""
    return " ".join(
        filter(None, (ACTIVE_ENGINE.transcribe(part) for part in split_audio(samples)))
    ).strip()


def transcribe_wav_path(path: str, source: str = "file") -> dict | None:
    audio = read_wav(path, SAMPLE_RATE)
    started = time.time()
    raw = transcribe_audio(audio)
    profile = current_profile()
    final = finish_text(raw, profile)
    if not final:
        return None
    return log_history(
        final,
        original=raw,
        audio=audio,
        duration=len(audio) / SAMPLE_RATE,
        latency=time.time() - started,
        engine=getattr(ACTIVE_ENGINE, "name", ""),
        profile=profile,
        source=source,
    )


def available_microphones() -> list[tuple[int, str]]:
    devices = []
    try:
        backend = load_audio_backend()
        if backend is None:
            return devices
        for index, info in enumerate(backend.query_devices()):
            if int(info.get("max_input_channels", 0)) > 0:
                devices.append((index, str(info.get("name", "Microphone"))))
    except Exception:
        pass
    return devices


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
    print("â— Recording%s..." % (" (continuous)" if continuous_mode else ""))


def stop_and_transcribe() -> None:
    global recording, command_mode, command_selection
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
        audio = np.concatenate(chunks).flatten() if chunks else np.zeros(0, dtype=np.float32)
        profile = current_profile()
        text = finish_text(raw, profile)
        if not text:
            print("Heard nothing intelligible.")
            return
        latency = time.time() - t0
        if command_mode:
            transformed = transform_selected_text(command_selection, text)
            if transformed is None:
                print("Command not supported; selected text was left unchanged.")
                ui_events.put(("notice", "Command not supported"))
                return
            deliver_text(
                transformed,
                trailing_space=False,
                original=text,
                audio=audio,
                duration=len(audio) / SAMPLE_RATE,
                latency=latency,
                engine=getattr(ACTIVE_ENGINE, "name", ""),
                profile=profile,
                source="command",
            )
            print("Command applied: %s" % text)
            return
        print("â†’ (%.1fs wait) %s" % (latency, text))
        deliver_text(
            text,
            original=raw,
            audio=audio,
            duration=len(audio) / SAMPLE_RATE,
            latency=latency,
            engine=getattr(ACTIVE_ENGINE, "name", ""),
            profile=profile,
        )
    finally:
        command_mode = False
        command_selection = ""
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
        print("â–  Continuous mode off.")


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
        print("â— Continuous mode on (mic locked open).")
    else:
        start_recording()


# ---------------------------------------------------------------- hotkeys

def capture_selected_text() -> str:
    """Copy selected text without leaving Flow State's marker in the clipboard."""
    marker = "__FLOW_STATE_SELECTION_%d__" % time.time_ns()
    old = None
    try:
        old = pyperclip.paste()
    except Exception:
        pass
    try:
        pyperclip.copy(marker)
        keyboard.send("ctrl+c")
        deadline = time.time() + 0.8
        while time.time() < deadline:
            time.sleep(0.03)
            copied = pyperclip.paste()
            if copied != marker:
                return copied.strip()
        return ""
    finally:
        if old is not None:
            try:
                pyperclip.copy(old)
            except Exception:
                pass


def toggle_command_mode() -> None:
    """Capture a selected-text command with a press-once/press-again flow."""
    global command_mode, command_selection
    if command_mode and recording:
        threading.Thread(target=_finish, daemon=True).start()
        return
    if recording:
        return
    selected = capture_selected_text()
    if not selected:
        ui_events.put(("notice", "Select text first"))
        print("Command mode needs selected text.")
        return
    command_selection = selected
    command_mode = True
    start_recording()
    ui_events.put(("notice", "Speak a command; press again to apply"))


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
    keyboard.add_hotkey(COMMAND_HOTKEY, toggle_command_mode)


# ---------------------------------------------------------------- tray icon

TRAY = None
TRAY_ICONS = {}


def start_tray() -> None:
    global TRAY, TRAY_ICONS
    import pystray
    from PIL import Image

    base = Image.open(TRAY_ICON_FILE).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
    TRAY_ICONS = {
        "idle": base.copy(),
        "recording": base.copy(),
        "continuous": base.copy(),
        "transcribing": base.copy(),
    }

    menu = pystray.Menu(
        pystray.MenuItem("Hold or tap %s Â· %s = open mic"
                         % (HOTKEY_LABEL, CONTINUOUS_LABEL),
                         None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Hub (history & dictionary)",
                         lambda icon, item: ui_events.put("hub")),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", lambda icon, item: ui_events.put("quit")),
    )
    TRAY = pystray.Icon("flow-state", TRAY_ICONS["idle"],
                        "Flow State", menu)
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
    """The floating bar. A paper-white pill with six thin ink curves â€” one
    per octave of your voice â€” drawn like a precision instrument chart.
    Stays visible after use and fades away after IDLE_FADE seconds. Drag to
    move; snaps to screen anchors; never steals keyboard focus."""

    W, H = 190, 26
    POLL_MS = 20
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

        # static art, drawn ONCE â€” animation only moves coordinates
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
        # microphone glyph (state indicator) â€” crisp vector art in place of the
        # old status dot. Recolours by state; drawn once, never rebuilt.
        cx, cy, _c = 11.0, mid, self.DOTS["idle"]
        # A compact badge, centered inside the 26px pill.
        self.canvas.create_oval(cx - 6.4, cy - 6.4, cx + 6.4, cy + 6.4,
                                fill=PAPER_DIM, outline=HAIRLINE, width=1)
        self._mic = [                                      # (item, colour option)
            (self.canvas.create_oval(cx - 1.35, cy - 4.3, cx + 1.35, cy + 0.8,
                                     fill=_c, outline=""), "fill"),      # capsule
            (self.canvas.create_arc(cx - 2.9, cy - 2.1, cx + 2.9, cy + 3.7,
                                    start=180, extent=180, style=tk.ARC,
                                    outline=_c, width=1.0), "outline"),  # cradle
            (self.canvas.create_line(cx, cy + 3.7, cx, cy + 4.9,
                                     fill=_c, width=1.0), "fill"),       # stem
            (self.canvas.create_line(cx - 1.9, cy + 5.1, cx + 1.9, cy + 5.1,
                                     fill=_c, width=1.0), "fill"),       # base
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
        self.partial_bg = self.canvas.create_rectangle(
            25, 4, self.W - 5, self.H - 4, fill=PAPER, outline="",
            state="hidden",
        )
        self.partial_text = self.canvas.create_text(
            31, mid, text="", anchor="w", width=self.W - 42,
            fill="#6f685c", font=("Segoe UI", 8), state="hidden",
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
        self.root.after(self.POLL_MS, self._poll)
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

    def _show_partial(self, text: str, duration: int = 1800):
        one_line = " ".join(text.split())
        if len(one_line) > 42:
            one_line = "..." + one_line[-39:]
        self.canvas.itemconfigure(self.partial_text, text=one_line, state="normal")
        self.canvas.itemconfigure(self.partial_bg, state="normal")
        self.canvas.tag_raise(self.partial_bg)
        self.canvas.tag_raise(self.partial_text)
        self.root.after(duration, self._hide_partial)

    def _hide_partial(self):
        self.canvas.itemconfigure(self.partial_bg, state="hidden")
        self.canvas.itemconfigure(self.partial_text, state="hidden")

    def _poll(self):
        try:
            while True:
                state = ui_events.get_nowait()
                if isinstance(state, tuple):
                    kind, text = state
                    if kind == "partial":
                        self._show_partial(text)
                    elif kind == "notice":
                        self._show_partial(text, 2600)
                    continue
                if state == "quit":
                    if TRAY:
                        TRAY.stop()
                    self.root.destroy()
                    os._exit(0)
                elif state == "hub":
                    self._open_hub()
                elif state in self.DOTS:
                    if state == "idle":
                        self._hide_partial()
                    self._show(state)
                else:  # "hide"
                    self.root.withdraw()
                    self.state = None
                    set_tray_state("idle")
        except queue.Empty:
            pass
        self.root.after(self.POLL_MS, self._poll)

    def _open_hub(self):
        if self.hub is None or not self.hub.top.winfo_exists():
            self.hub = ModernHub(self.root, sys.modules[__name__])
        self.hub.show()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------- main

def main() -> None:
    global vad_enabled, ACTIVE_ENGINE
    # Status prints use "â—"/"â†’". Under a redirected/piped stdout Windows
    # picks cp1252 (strict), so those chars raise UnicodeEncodeError and silently
    # kill the recording/finish worker threads. Force UTF-8 with replacement so a
    # print can never take a thread (and the dictation) down.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    want_hub = "--hub" in sys.argv or OPEN_HUB
    if not ipc_server():
        # another copy is already running â€” ask it to show its Hub instead
        ipc_send("hub")
        print("Already running; opened the Hub in the existing instance.")
        return
    try:  # per-monitor DPI awareness: crisp pixels, correct overlay placement
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    make_cues()
    make_icon()
    if HISTORY_DAYS:
        removed = HISTORY.prune(int(HISTORY_DAYS))
        if removed:
            print("History retention removed %d old dictation(s)." % removed)
    print("Loading speech model (first run may download it)...")
    audio_loader = threading.Thread(target=load_audio_backend, daemon=True)
    audio_loader.start()
    ACTIVE_ENGINE = load_engine()
    print("Engine: %s" % ACTIVE_ENGINE.name)
    # first inference pays a ~8s one-time warm-up cost â€” pay it now, at
    # startup, instead of on the user's first dictation
    ACTIVE_ENGINE.transcribe(np.zeros(SAMPLE_RATE // 2, dtype=np.float32))
    print("Engine warmed up.")

    audio_loader.join()
    if sd is None:
        raise RuntimeError("Audio backend failed to load") from _audio_load_error

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, blocksize=BLOCK, channels=1,
        dtype="float32", callback=audio_callback, device=MICROPHONE,
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
