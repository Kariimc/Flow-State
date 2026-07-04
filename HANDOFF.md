# Whisper Flow Clone — Engineering Handoff

A local, offline voice-dictation app for Windows in the spirit of Wispr Flow.
Hold or tap a hotkey, speak, and the text is inserted into whatever window has
focus. No audio ever leaves the machine. Single file: `flow.py` (~1,400 lines,
standard-library UI, no framework).

Status: working and verified end-to-end on the target machine. Built and tested
on an Intel Pentium Gold 5405U (2 cores, no AVX2, 3.8 GB RAM, no usable GPU) —
the whole design is shaped by that constraint, so it runs comfortably on far
better hardware.

---

## 1. Quick start

```powershell
# From the project folder, one time:
powershell -ExecutionPolicy Bypass -File setup.ps1
# then:
.\run.bat
```

`setup.ps1` creates the `.venv` (Python 3.12 via `uv`, or the `py` launcher as
fallback), installs `requirements.txt`, and downloads the two speech models into
`models/`. Sound cues and the desktop icon are generated on first launch.

Use it: hold or tap **Ctrl+Win**, speak, release. Text appears at your cursor.
- **Hold** Ctrl+Win = walkie-talkie (release to finish).
- **Tap** Ctrl+Win = hands-free; stops after ~1.5 s of silence, or tap again.
- **Ctrl+Win+Space** = continuous mode; mic stays open, text streams in until
  you press it again.
- **Esc twice** quickly = quit.

The desktop shortcut ("Whisper Flow") opens the **Hub** (History, Dictionary,
Options). The app also lives in the system tray and starts with Windows.

---

## 2. Why these technology choices (the hardware story)

The target CPU has **no AVX2**. This single fact drove the stack:

- **faster-whisper / CTranslate2** falls back to a generic SSE path without AVX2.
  Measured here: **~35 s to transcribe 4 s of audio** with `base`. Unusable.
- **Moonshine base int8 via sherpa-onnx (ONNX Runtime)** does the same clip in
  **~1–2.5 s**, with equal or better accuracy, a 58 MB model, and no AVX2
  requirement. This is the default engine. Whisper stays available as a config
  option for non-English dictation (it is slow on this box but correct).
- A **local LLM cleanup** step (Wispr's real magic) is not viable here — a
  0.5 B model would add 5–20 s per dictation competing for the same 2 cores. So
  cleanup is **rule-based** (`clean_text`, `Dictionary`) behind the same
  interface an LLM would use. On stronger hardware, swap `clean_text` for a
  local model call and nothing else changes. See RESEARCH.md §5.

Full research (Wispr feature/architecture teardown, open-source survey, the
community wishlist, and the hardware feasibility study with sources) is in
**RESEARCH.md**.

---

## 3. Architecture

### Responsiveness model (the important part)

Naïve record-then-transcribe made the app feel dead: you finish talking, then
wait 20–40 s while the whole clip is processed, and Moonshine loops/repeats on
long audio. The fix is **incremental transcription while you speak**:

```
mic (sounddevice, 0.1s blocks)
      │
      ▼
audio_callback ──► FFT → spectrum (6 octave bands, drives the waveform)
      │
      ├──► vad_queue ──► vad_worker (Silero VAD)
      │                     │  cuts speech into utterances at pauses
      │                     ▼
      │                  seg_queue ──► transcriber_worker (Moonshine)
      │                                   │ transcribes each utterance NOW
      │                                   ├─ continuous mode: inject immediately
      │                                   └─ hold/tap mode: collect in `partials`
      ▼
   chunks[] (raw fallback buffer if VAD finds nothing)
```

When you stop, only the final unspoken utterance still needs work, so the wait
after release is ~1–3 s instead of the whole recording. On startup we run one
throwaway `transcribe()` to pay Moonshine's ~2.5 s first-inference warm-up
before the user's first dictation.

### Threads

- **Main thread**: Tkinter overlay + Hub (Tkinter must own the main thread).
  Everything else talks to it through the `ui_events` queue.
- **sounddevice callback thread**: mic capture, spectrum FFT, feeds queues.
- **vad_worker thread**: Silero VAD segmentation + tap-mode auto-stop.
- **transcriber_worker thread**: runs the ASR engine on finished utterances.
- **pystray thread**: system tray icon (`run_detached`).
- **keyboard hooks**: global hotkeys (the `keyboard` library).
- **IPC thread**: single-instance socket server (see §6).

`busy` (a Lock) serializes the finish/stop paths so a key-release and a
VAD-auto-stop can't both transcribe the same recording.

### Feature → code map

| Feature | Where |
|---|---|
| ASR engines (Moonshine default, Whisper fallback) | `MoonshineEngine`, `WhisperEngine`, `load_engine` |
| Rule cleanup (fillers, spoken punctuation) | `clean_text` |
| Personal dictionary (live-reload replacements) | `Dictionary`, `read_rules`, `write_rules` |
| Incremental pipeline | `audio_callback`, `vad_worker`, `transcriber_worker` |
| Long-audio fallback split | `split_audio` |
| Hold / tap / continuous logic | `on_key_down/up`, `toggle_continuous`, `end_continuous` |
| Text insertion (paste + restore, or type) | `inject` |
| Waveform overlay (6 octave curves) | `Overlay` |
| Hub (history/dictionary/options) | `Hub` |
| Autostart + single-instance + desktop icon | `set_autostart`, `ipc_server/send`, `make_icon` |
| Settings persistence | `load_settings`, `save_settings`, `settings.json` |

---

## 4. Settings

Defaults live in the config block at the top of `flow.py`. `settings.json`
(written by the Hub's **Options** tab) overrides them at startup via
`load_settings()`. Keys in `TWEAKABLE`: `HOTKEY`, `CONTINUOUS_HOTKEY`, `ENGINE`,
`INJECTION`, `VERBATIM`, `AUTO_STOP`, `MAX_RECORD`, `IDLE_FADE`.

`VERBATIM`, `INJECTION`, `AUTO_STOP`, `IDLE_FADE`, `MAX_RECORD` are read at
use-time, so Options changes apply immediately. `ENGINE` and `HOTKEY` are read
at startup, so they need a restart.

---

## 5. Design system

Palette is deliberate — no violet, no generic blue gradients, no vibe-coded
look. It is the "Aural Imbalance" reference artwork: warm ink on paper.

```
INK       #26231d   PAPER    #f8f5ee   HAIRLINE #e3dccb
VERMILION #c8371e   AMBER    #e8912a   TEAL     #1f7f93
```

**Waveform**: a 190×26 paper-white pill with graph-paper hairlines and six thin
ink curves. Each curve is one octave of your voice (80 Hz–5 k Hz, `SPEC_BANDS`),
so speaking lights up the whole "chord" — bass swells the slow vermilion wave,
sibilants ripple the fast teal ones. Quiet high octaves are boosted with a sqrt
so all six stay visible. Drawn once at init; the animation only calls
`canvas.coords()` on existing items (rebuilding every frame is what made an
earlier version choppy). ~33 fps via `after(30, ...)`. The pill fades out after
`IDLE_FADE` seconds and never steals keyboard focus (WS_EX_NOACTIVATE).

**Icon** (`make_icon`): the same three-curve waveform on paper, generated to
`models/flow.ico`, used by the desktop shortcut and the Hub window.

---

## 6. Gotchas (hard-won — read before editing)

- **No `winsound.Beep` in the keyboard-hook path.** It blocks for its full
  duration and stalls the global hook, making every app stutter. We use async
  `winsound.PlaySound(...SND_ASYNC)` with soft generated sine chimes instead.
- **Wait for modifiers before pasting.** If the user still holds Ctrl/Win when
  transcription finishes, a synthetic Ctrl+V becomes Ctrl+Win+V and pastes
  nowhere. `inject()` polls `keyboard.is_pressed(...)` until the modifiers are
  released.
- **The overlay must not take focus.** Clicking/dragging a normal window steals
  focus from the target and the paste lands in the void. The pill sets
  WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW.
- **Long audio makes Moonshine loop.** Always segment (VAD, or `split_audio`
  as fallback) so no single chunk is longer than ~12–14 s.
- **DPI awareness matters.** `SetProcessDpiAwareness(2)` in `main()` — without
  it the overlay is placed at the wrong coordinates and renders blurry on
  scaled displays. Test screenshots also need it, or they grab the wrong region.
- **`pythonw.exe` from a uv venv is a stub** that re-spawns the real
  `python.exe`. Process/port checks must look at `python.exe`, not the stub.
- **`Fn` cannot be a hotkey.** Laptop firmware handles it; Windows never sees a
  keystroke. That's why the default is Ctrl+Win (same as Wispr on Windows).
- **Single instance** is enforced by binding TCP `127.0.0.1:47821`. A second
  launch (e.g. the desktop icon while it's already running) fails the bind and
  sends `"hub"` over that socket so the running copy opens its Hub instead of
  starting a duplicate.
- **Tkinter is single-threaded.** Never touch widgets off the main thread; push
  a string onto `ui_events` and let `Overlay._poll` handle it.

---

## 7. Testing approach

No formal test suite; verification is done by driving the real components and
screenshotting the real UI (the app is inherently GUI + audio + global hooks).
Patterns used during development, reproduce them when changing things:

- **Cleanup/dictionary**: call `clean_text` / `Dictionary.apply` on strings and
  assert exact output.
- **Engine + pipeline**: generate speech WAVs with Windows SAPI
  (`SpVoice`/`SpFileStream`, format type 22 = 22.05 kHz → resample to 16 k),
  feed them through `vad_worker`/`transcriber_worker` in a background thread at
  real-time pace, and assert the transcript plus the incremental timing.
- **Overlay/Hub**: launch with DPI awareness, drive states via `ui_events`, and
  `PIL.ImageGrab.grab(..., all_screens=True)` the pill/window to inspect it.
- **Injection**: `inject()` into a focused Tk `Text` widget and read it back.
- **Autostart/IPC/settings**: registry round-trip, socket handoff, JSON
  round-trip — all assertable without the GUI.

---

## 8. Roadmap (what's next)

Table-stakes and the top community asks are done: offline, private, low-RAM,
verbatim mode, dictionary, history, hold/tap/continuous, tray, autostart. From
RESEARCH.md §6, remaining ideas in rough priority:

1. **Per-app tone profiles** — casual in chat, formal in email, by active window.
2. **Local LLM "deep clean" mode** — optional, for capable hardware; slot into
   the `clean_text` seam.
3. **Streaming partial text** in continuous mode (show words mid-utterance).
4. **Usage stats** in the Hub (words/day, average transcribe speed).
5. **Packaging** — a Nuitka/Inno installer so it runs without the Python setup.

---

## 9. File inventory

Committed:
- `flow.py` — the entire app.
- `run.bat` — launches it in the venv.
- `setup.ps1` — creates the venv and downloads models.
- `requirements.txt` — Python deps.
- `dictionary.txt` — template (personal rules are git-ignored via runtime files).
- `README.md` — user guide. `RESEARCH.md` — the research. `PROGRESS.md` — working
  log. `HANDOFF.md` — this file.

Not committed (see `.gitignore`): `.venv/`, `models/*` (275 MB of models,
downloaded by setup + generated cues/icon), `history.txt`, `settings.json`,
`overlay_pos.txt`, `__pycache__/`, `.claude/`.
