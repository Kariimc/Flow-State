# Flow State - Progress

**Updated:** 2026-07-11
**Last verified:** full unit discovery ran 14 tests OK, including transcript delivery under history-write failure; five Python files compiled to an isolated cache; import baseline 2314.4 ms, engine load 4303.5 ms, warmed 0.5-second silent inference 29.1-52.6 ms; `git diff --check` passed.

## Where We Are

Flow State is the current project name and GitHub remote. Treat old
"Whisper clone" wording as stale.

The app is a local Windows dictation tool: Ctrl+Win hold/tap dictation,
continuous mode, tray icon, floating waveform pill, local history, dictionary,
vocabulary casing, selected-text commands, WAV file transcription, profiles,
polish cleanup, and a modern Hub options screen.

The Hub now has a paper/graph-paper layout, dark mode, a heavy red F brand,
red toggle knobs on neutral tracks, sidebar icon nav, and pages for History,
Dictionary, General, Dictation, Audio & mic, Appearance, Privacy, Files &
meetings, and Statistics. Header/title clipping was fixed by reducing the
Georgia header sizes and increasing header height.

Performance work is active on branch `perf/reliability-baseline`. The first
slice inserts completed text before saving WAV/history data, so disk latency or
an ordinary history-write error cannot prevent the transcript from appearing.
The old implementation failed the new regression test; the fixed path passes.

## Do Next

Build the repeatable benchmark harness and Hub control-action matrix, then
measure key-to-overlay and stop-to-insert median/p95 in a live Notepad run.
Use refreshed competitor/community evidence to rank the ten differentiators.

## Don't Forget

- The repo remote is `https://github.com/Kariimc/Flow-State.git`.
- The local project folder is `C:\Users\Kariim\flow-state`.
- The venv was repaired after migration; `.venv\pyvenv.cfg` now points to the
  bundled Python 3.12 runtime under `C:\Users\Kariim\.cache\codex-runtimes`.
- The Flow State Desktop shortcut must target
  `C:\Users\Kariim\flow-state\.venv\Scripts\pythonw.exe` with
  `"C:\Users\Kariim\flow-state\flow.py" --hub`, working directory
  `C:\Users\Kariim\flow-state`, icon `models\flow.ico`.
- System-audio capture depends on Windows exposing Stereo Mix; speaker
  separation is not built.
- Tests include a bite-proof guard that history deletion never unlinks audio
  outside Flow State's owned `data\recordings` directory.
- Do not claim Flow State is faster than competitors or that a feature is
  exclusive until a matching benchmark or current competitor audit proves it.
- Run unittest and `py_compile` sequentially because parallel runs race on pyc
  files. The current cache target is locked, so compile to a separate path.

## Why It's Built This Way

- 2026-07-09 - Kept the feature logic in `flow_features.py` so risky text,
  audio, and history behavior can be tested without starting the GUI.
- 2026-07-09 - Replaced the old inline Hub with `flow_hub.py` so the options
  screen can grow without making the dictation loop harder to reason about.
- 2026-07-09 - Kept the toggle track neutral and made the knob red in both
  states because that matched Kariim's visual preference better than dark
  toggle bands or white knobs.
- 2026-07-09 - Used the same `models\flow.ico` for Desktop and tray so the
  app identity is consistent after the repo rename to Flow-State.
- 2026-07-09 - Superseded the first tray-icon parity pass with distinct polished icons: Desktop uses `models\flow.ico` with the red F in front of the waveform/graph paper, while the tray uses `models\flow-tray.ico`, a shaded grey mic with the red F centered in the mic head.
- 2026-07-09 - Centered the floating waveform bar's mic badge around the 26px pill midpoint (`mid = 13`), with a 12.8px circle and smaller mic glyph so it no longer hangs high or low inside the bar.
- 2026-07-11 - Made transcript insertion precede non-critical history persistence because user-visible delivery must survive storage errors and should not wait for WAV/fsync work.
