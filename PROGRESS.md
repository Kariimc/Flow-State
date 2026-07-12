# Flow State - Progress

**Updated:** 2026-07-11
**Last verified:** full desktop-context discovery ran 31 tests OK in 33.464s; 7 Python files compiled to an isolated cache; Recovery Inbox was visually checked in the native dark-mode Hub; its history-save guard proved red when removed and green restored; `git diff --check` passed.

## Where We Are

Flow State is the current project name and GitHub remote. Treat old
"Whisper clone" wording as stale.

The app is a local Windows dictation tool: Ctrl+Win hold/tap dictation,
continuous mode, tray icon, floating waveform pill, local history, dictionary,
vocabulary casing, selected-text commands, WAV file transcription, profiles,
polish cleanup, and a modern Hub options screen.

The Hub now has a paper/graph-paper layout, dark mode, a heavy red F brand,
red toggle knobs on neutral tracks, sidebar icon nav, and pages for History,
Recovery, Dictionary, General, Dictation, Audio & mic, Appearance, Privacy, Files &
meetings, and Statistics. Header/title clipping was fixed by reducing the
Georgia header sizes and increasing header height.

Performance work is active on branch `perf/reliability-baseline`. The first
slice inserts completed text before saving WAV/history data, so disk latency or
an ordinary history-write error cannot prevent the transcript from appearing.
The old implementation failed the new regression test; the fixed path passes.
The overlay now checks cross-thread state every 20 ms instead of 100 ms, and
audio initialization is lazy and overlaps model loading. The startup benchmark
raw samples were old 10048.0/4232.6/4413.4 ms and new
3476.3/3416.2/3046.1 ms; medians are used because the first old run was cold.

`DIFFERENTIATORS.md` is the evidence-backed ten-feature contract. Feature #5,
Clipboard Shield, is implemented: it restores the prior clipboard only when
the Windows clipboard change counter proves no newer data appeared, and falls
back to direct typing if clipboard access is locked.

Feature #1 Crash Journal is implemented. Every recognized segment is fsynced
under `data/recovery/` during normal, command, and continuous sessions. A
successful final history save removes the temporary journal; a crash or failed
save leaves it available for Recovery Inbox.

Recovery Inbox's text path is implemented in the Hub. It lists orphan journals
with a sidebar count, shows the recovered text and metadata, copies it, retries
delivery after hiding the Hub, and confirms removal. Retry deletes the journal
only when History persistence succeeds; failed delivery or failed history save
keeps the recovery copy. Recoverable audio/re-transcription is still required
before differentiator #2 is complete.

## Do Next

Finish #2 Recovery Inbox by attaching stopped-session audio to its contained
journal and retrying transcription when that audio exists. Retry the live
Notepad stop-to-insert measurement when desktop process launch is available.

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
- Tk tests must run outside the desktop sandbox; inside it Tcl reports a false
  `init.tcl` failure. A real desktop check reports Tcl/Tk 8.6.12.
- `benchmark_flow.py` is the repeatable baseline command. Its 2026-07-11 quick
  run: import median 604.8 ms/p95 790.4 ms, text finish median 0.2 ms/p95
  0.6 ms, text history median 2.3 ms, 10-second audio history median 3.8 ms.
- The live Notepad launch attempt was blocked by the desktop execution service's
  temporary usage limit, not by Flow State. Do not substitute a synthetic test;
  retry the real run when launch access returns.

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
- 2026-07-11 - Lazy-loaded PortAudio in parallel with the speech model and reduced overlay polling to 20 ms because profiling showed audio import was the largest avoidable startup cost and 100 ms polling dominated visual response.
- 2026-07-11 - Scoped “ten unique features” to documented gaps across Wispr Flow, Aqua Voice, and Superwhisper, and chose sequence-aware Clipboard Shield first because stale clipboard restoration can overwrite newer user data.
- 2026-07-11 - Fsynced recognized segments into a contained Crash Journal because long dictations must survive process interruption; journals are deleted only after final history persistence succeeds.
- 2026-07-11 - Replaced corrupted console glyphs with ASCII because `start_recording()` raised `UnicodeEncodeError` before stdout reconfiguration in direct/test invocation.
- 2026-07-12 - Kept Recovery Inbox journals until both redelivery and History save succeed because inserted text without durable History must remain recoverable.
