# Flow State - Progress

**Updated:** 2026-07-09
**Last verified:** real repo compile passed; `C:\Users\Kariim\flow-state\.venv\Scripts\python.exe -m unittest -v test_flow_features.py` ran 13 tests OK; Tk Hub smoke captured 9 light pages and 2 dark pages; Desktop shortcut target/icon verified.

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

## Do Next

Run a live dictated sentence into Notepad after restarting Flow State, then
decide whether to scope the optional local-LLM deep-clean pass. Do not rename
this back to Whisper clone; Flow State / Flow-State is the current name.

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
