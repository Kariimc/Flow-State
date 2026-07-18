# Flow State — Engineering Handoff

A local, offline voice-dictation app for Windows in the spirit of Wispr Flow.
Hold or tap a hotkey, speak, and the text is inserted into the captured target
window. No audio leaves the machine. The app uses three production modules:
`flow.py` for capture/delivery, `flow_features.py` for durable data and text
features, and `flow_hub.py` for the standard-library Tk UI.

Status: candidate branch `fix/waveform-text-transition` is ready for fresh merge
approval. It makes waveform and rendered text mutually exclusive pill phases,
uses a generation-bound timeout so stale phrases cannot hide newer text, and
restores the waveform from a flat baseline. Appearance now previews the real
Desktop/Hub and tray icon assets. All 122 tests passed in 83.810s, including 20
native Tk tests; all eight Python/test/benchmark files compile; browser review
confirmed both visual states and clean consoles. PID 23372 is still the previous
merged `main` build until approval, merge, and a controlled IPC restart. The
three existing local review artifacts remain untracked and excluded.

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
- **Ctrl+Win+Shift+Space** = pause or resume the same continuous session.
- **Esc twice** quickly = quit.

The desktop shortcut opens the **Hub**. Its navigation is History, Recovery,
Delivery queue, Dictionary, Accuracy, General, Dictation, Audio & mic, Appearance,
Privacy, Files & meetings, and Statistics. The app also lives in the system
tray and can start with Windows when the Hub's autostart setting is enabled.

---

## 2. Why these technology choices (the hardware story)

The original target CPU had **no AVX2**. This constraint drove the stack even
though the current laptop has more headroom:

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
- **correction watcher threads**: bounded read-only checks of one standard Windows edit control after insertion.
- **IPC thread**: single-instance socket server (see §6).

`busy` (a Lock) serializes the finish/stop paths so a key-release and a
VAD-auto-stop can't both transcribe the same recording.

### Feature → code map

| Feature | Where |
|---|---|
| ASR engines (Moonshine default, Whisper fallback) | `MoonshineEngine`, `WhisperEngine`, `load_engine` |
| Rule cleanup, profiles, corrections, vocabulary | `flow_features.py`, `finish_text` |
| Personal dictionary (live-reload replacements) | `Dictionary`, `read_rules`, `write_rules` |
| Reviewed correction memory and bounded edit watching | `CorrectionStore`, `extract_correction_pairs`, `watch_inserted_correction` |
| History, corrected labels, recordings, recovery, delivery queue | `HistoryStore`, `RecoveryJournal`, `DeliveryQueue` |
| Incremental pipeline | `audio_callback`, `vad_worker`, `transcriber_worker` |
| Long-audio fallback split | `split_audio` |
| Hold / tap / continuous / pause logic | `on_key_down/up`, `toggle_continuous`, `toggle_pause` |
| Focus/typing guards and delivery | `protect_delivery`, `deliver_text` |
| Clipboard Shield, scoped undo/redo | `inject`, `undo_last_insertion`, `redo_last_insertion` |
| Waveform overlay (6 octave curves) | `Overlay` |
| Hub pages and controls | `flow_hub.Hub` |
| Autostart + single instance + desktop/tray icons | `set_autostart`, `ipc_server/send`, `make_icon` |
| Settings persistence | `load_settings`, `save_settings`, `settings.json` |

---

## 4. Settings

Defaults live in the config block at the top of `flow.py`. `settings.json`
(written by the Hub settings pages) overrides them through `load_settings()`.
`TWEAKABLE` covers the six shortcuts, engine/injection, cleanup/profile,
microphone and cues, audio/history retention, correction approval mode, theme, and startup Hub behavior.
The Hub marks changes that need a restart; use-time values apply immediately.

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

**Brand art** (`assets/`): the shipped source art lives in `assets/` as the
committed brand source of truth — the diamond-topped chrome **F** wordmark, the
desktop app icon (graph-paper waveform on a dark rounded square), the tray
crystal, the light/dark pills, and the standalone waveform. Each was exported as
a JPEG with a baked-in transparency checkerboard; `assets/build_assets.py` keys
that out to real alpha (colour-key for isolated subjects, shape mask for the
framed icon/pills) and writes the clean transparent PNGs alongside the sources.

**Icons**: `models/flow.ico` (desktop/Hub) and `models/flow-tray.ico` (tray) are
built at startup from `assets/flow-icon.png` and `assets/flow-tray.png` by
`build_brand_icons()`, rebuilt whenever the source PNG is newer than the `.ico`.
If the brand PNGs are missing, `make_icon()` still draws the original vector
icons as a fallback. The `.ico` files stay generated (gitignored) under
`models/`. Tray state tinting derives from the tray artwork as before.

**Hub header**: the F wordmark is shown at the left of the Hub header
(`flow_hub.Hub`), loaded from the pre-sized `assets/flow-wordmark-72.png`
(Tk's `PhotoImage` cannot scale). Absent art falls back to the text titles.

**Overlay pill** (`Overlay`): still the live, voice-reactive vector pill — six
octave curves animated per frame, not a static image. The `assets/pill-*.png`
and `assets/waveform.png` art is committed for brand use but intentionally does
not replace the reactive overlay (a 190×26 static bitmap would drop the live
waveform, the app's signature; see build notes).

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

The formal suite is `test_flow_features.py`, `test_flow_hub.py`, and
`test_flow_runtime.py`. Run all 120 tests in one process from the repository root:

```powershell
.venv\Scripts\python.exe -m unittest -v
```

The suite drives pure features, runtime control paths, and native Tk pages.
Runtime/UI changes also need the focused real checks below:

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

The approved Hub roadmap, ten reliability differentiators, and Accuracy
Learning are shipped. Accuracy observations remain pending until explicit
approval. Candidate-engine comparison is the next evidence step, but it stays
blocked until History contains 12 corrected entries with saved audio.

Future ideas require a new decision rather than silent implementation:

1. **Local LLM deep clean** on hardware that can carry the added delay.
2. **True word-level streaming preview**, beyond current utterance delivery.
3. **Packaging** with an installer so Python setup is not required.
4. **Same-machine competitor testing**, only if Kariim chooses desktop installs.

---

## 9. File inventory

Committed:
- `flow.py` — capture, engines, overlay, delivery, tray, and runtime wiring.
- `flow_features.py` — text transforms and durable History/Recovery/Delivery stores.
- `flow_hub.py` — the full Hub UI.
- `test_flow_features.py`, `test_flow_hub.py`, `test_flow_runtime.py` — 97 tests.
- `benchmark_flow.py`, `native_delivery_benchmark.py` — repeatable performance probes.
- `run.bat` — launches it in the venv.
- `run.vbs` — launches it without a console window.
- `setup.ps1` — creates the venv and downloads models.
- `requirements.txt` — Python deps.
- `assets/` — committed brand art: source JPEGs, clean transparent PNGs, and
  `build_assets.py` (regenerates the PNGs and the two `.ico` files).
- `dictionary.txt`, `vocabulary.txt` — tracked starter content; review personal
  entries before pushing.
- `README.md` — user guide. `RESEARCH.md` — the research. `PROGRESS.md` — working
  log. `HANDOFF.md` — this file.

Not committed (see `.gitignore`): `.venv/`, `models/*` (275 MB of models,
downloaded by setup + generated cues/icons), `history.txt`, `history.jsonl`,
`settings.json`, `overlay_pos.txt`, `data/`, `__pycache__/`, `.claude/`.
