# PROGRESS

## What this is
Local Wispr Flow clone for Windows (`flow.py`). 100% offline dictation:
hold/tap F8 → speak → text pasted into the active window.

## Current state (2026-07-02)
Working and verified end-to-end. Features: Moonshine base int8 ASR via
sherpa-onnx (default; faster-whisper fallback for non-English), Ctrl+Win
hold + tap-toggle hotkey (combo support; NOTE config var ENGINE=str,
runtime ACTIVE_ENGINE=object), Silero VAD auto-stop (tap, 1.5 s) + 45 s
hard cap, split_audio() chunks long takes at quiet points (fixes Moonshine
repetition loops), clipboard-paste injection (waits for modifiers released,
1.2 s clipboard restore; verified into a real Text widget), rule-based
cleanup + VERBATIM, dictionary.txt live-reload, 0.5 s pre-roll, overlay:
paper-white pill w/ 6 octave-band FFT curves (Aural Imbalance style),
drag + snap anchors + overlay_pos.txt, WS_EX_NOACTIVATE (no focus steal),
persistent canvas items + DPI-aware (smooth anim), pystray tray, soft
sine chime cues (models/cue_*.wav, SND_ASYNC), history.txt log.

## Key machine constraints (why choices were made)
Pentium Gold 5405U — 2 cores, **no AVX2**, 3.8 GB RAM, no GPU.
- faster-whisper base = ~35 s per 4 s clip here; Moonshine = ~1–2.5 s.
- App measured ~316 MB RAM with Moonshine loaded.
- Local LLM cleanup not viable on this box; `clean_text()` is the seam
  where a local LLM (Qwen 0.5B via llama.cpp/Ollama) slots in later.

## Layout
- `flow.py` — the whole app; config block at top
- `models/` — moonshine int8 + silero_vad.onnx (re-download cmds in README)
- `dictionary.txt` / `history.txt` — user data
- `RESEARCH.md` — cited deep-research on Wispr Flow + roadmap table
- `run.bat` — user entry point; venv is `.venv` (Python 3.12 via uv;
  system Python is 3.14 which ctranslate2 lacks wheels for)

## Since then (2026-07-03)
Incremental transcription (VAD segments transcribed while speaking; wait
after stop ≈ last segment only), engine warm-up at startup, continuous
mode (Ctrl+Win+Space, injects per segment), Hub window (history click-to-
copy, search, inline dictionary editing, Options tab -> settings.json,
live-apply except ENGINE/HOTKEY), single-instance via socket 47821 (2nd
launch = "open hub" IPC), autostart HKCU Run key (pythonw), desktop
shortcut "Whisper Flow.lnk" -> `flow.py --hub`, generated models/flow.ico.
NOTE: uv-venv pythonw.exe is a stub that spawns the real python.exe —
process checks must look at python.exe, not the stub.

## New laptop (2026-07-06)
Migrated to a much stronger box. Profile:
- CPU: 12th Gen Intel Core i5-1245U, 10 physical cores (2P+8E) / 12 threads.
- **AVX2: SUPPORTED** (old Pentium Gold 5405U had none — the single fact the
  whole engine choice hinged on). AVX also present.
- RAM: 15.65 GB (was 3.8 GB). GPU: Intel Iris Xe (iGPU, usable for small models).
Setup done end-to-end here: uv 0.11.26 installed via winget (not yet on this
shell's PATH — winget updated persistent user PATH, needs a new terminal),
git 2.55 + gh 2.96 already present, gh authed as Kariimc. `.venv` on Python
3.12.10, 35 pkgs, both models downloaded. App launched, warmed up, Ready
(340 MB RAM, socket 47821 bound, cues+icon generated).
Implication of AVX2: faster-whisper/CTranslate2 now runs at full speed (was
~35 s/4 s clip on the old box). small/distil-whisper for accuracy, and a
local-LLM "deep clean" in the clean_text seam, are both now viable —
pending user sign-off before changing ENGINE.
No personal data migrated: history.txt/settings.json absent, dictionary.txt
is the committed template only. User must bring dictionary.txt from old laptop.

## Live dictation test (2026-07-06) — PASSED
Hold-Ctrl+Win into Notepad, released, text inserted correctly. Waveform pill
appeared. One bug found and fixed along the way (see Gotchas): redirected
stdout crashed the recording thread on the "●"/"→" glyphs. Also replaced the
status dot with a vector mic glyph. Both landed on main (f7bf9e7).

## Engine benchmark on new laptop (2026-07-07)
Ran all three candidate engines against the same 7.89s SAPI-TTS test clip
(HANDOFF §7 method), transcript scored against the reference sentence:

| engine                              | load  | infer | score | notes |
|---|---|---|---|---|
| Moonshine base int8 (current)       | 1.23s | 0.30s | 100%  | current default |
| faster-whisper base int8 (AVX2)     | 1.16s | 2.32s | 100%  | ~8x slower than Moonshine |
| faster-whisper small int8 (AVX2)    | 3.21s | 7.00s | 100%  | ~23x slower than Moonshine |

**Recommendation: keep `ENGINE = "moonshine"`.** AVX2 makes faster-whisper
usable now (vs. ~35s/4s-clip unusable on the old Pentium), but it's still an
order of magnitude slower than Moonshine on this box for equal accuracy on
English. faster-whisper stays valuable as the manual non-English fallback
(LANGUAGE setting), which is its existing role — no code change needed, no
ENGINE flip made (per user's sign-off gate).

**Local-LLM "deep clean" pass** (HANDOFF §2, roadmap #2): now plausible with
10 cores/16 GB/AVX2 headroom (Moonshine's 0.3s leaves plenty of room for a
1-3s local 0.5-1B model call before it'd be noticeable), but it's a new
dependency + new seam implementation, not a config flip — needs its own
scoping/sign-off pass, not bundled into this benchmark. Not built yet.

## Dictionary (2026-07-07)
User has no dictionary.txt from the old laptop to migrate — nothing to
restore. Verified the live-reload mechanism itself works correctly (scratch
Dictionary instance, edited file, `.apply()` picked up the new rule with no
restart) so it's ready whenever rules get added via the file or the Hub.

## Next action
Roadmap "next" row: settings UI and/or per-app tone profiles, or scope the
local-LLM deep-clean pass if the user wants it built. User drives feature
picks from RESEARCH.md roadmap.

## Gotchas
- `keyboard` lib hotkey uses suppress=True on F8; Esc double-tap quits.
- Tkinter overlay owns the main thread; all UI changes go through
  `ui_events` queue. Tray updates piggyback on the same consumer.
- Don't run two instances (mic + hotkey conflict).
- TTS smoke-test trick: SAPI SpFileStream (format type 22 = 22.05 kHz,
  needs resample to 16 k in tests).
- Status prints use "●"/"→". Under a REDIRECTED/piped stdout Windows picks
  cp1252 (strict) not UTF-8, so those chars raise UnicodeEncodeError and
  silently KILL the recording/finish worker thread — symptom: start cue
  plays, then no text + hang. A real console is UTF-8 so it only bites
  headless/logged launches. Fixed: main() reconfigures stdout/stderr to
  utf-8, errors="replace" before any print.
- Overlay state indicator is now a vector mic glyph (Overlay._mic list of
  (item, colour-option) pairs), recoloured per state — not the old dot.
