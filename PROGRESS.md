# Flow State - Progress

**Updated:** 2026-07-14
**Last verified:** Accuracy Learning is merged and pushed to main at 3a80d55, with exact-state docs at d425e3e. The exact merged tree passed all 120 tests in 89.931s, including 19 native Tk Hub tests, and all eight Python/test/benchmark files compile. Focused native checks proved 64-bit standard Edit/RichEdit reads, password-control exclusion, bounded correction watching, supported 800x560 and 940x680 Hub geometry, and clean Tk callback teardown. Independent general, Python, and security reviews were resolved before merge. Old PID 12844 closed through Flow State IPC, the merged build is resident as PID 23372, and a separate IPC hub request returned True.
**Documentation audit:** README and HANDOFF now describe the shipped local correction memory, explicit approval modes, corrected History labels, private 12-record benchmark gate, and the standard-control watcher boundary. No candidate engine has been downloaded or ranked.

## Where We Are

Flow State is the current project name and GitHub remote. Treat old
"Whisper clone" wording as stale.

The app is a local Windows dictation tool: Ctrl+Win hold/tap dictation,
continuous mode, tray icon, floating waveform pill, local history, dictionary,
vocabulary casing, selected-text commands, WAV file transcription, profiles,
polish cleanup, and a modern Hub options screen.

The Hub now has a paper/graph-paper layout, dark mode, a grand Bodoni F in the
muted-indigo brand color, matching toggle knobs on neutral tracks, sidebar icon nav, and pages for History,
Recovery, Delivery queue, Dictionary, Accuracy, General, Dictation, Audio & mic, Appearance, Privacy, Files &
meetings, and Statistics. Header/title clipping was fixed by reducing the
Georgia header sizes and increasing header height.

Startup is now UI-first: the overlay and requested Hub are created before the
speech model/audio warm-up begins on a background worker. The Hub reports
Starting, Ready, or Startup failed; engine-dependent WAV/retry actions are
blocked while loading. Existing icons and cues are reused instead of redrawn,
and a retained global audio-stream handle is stopped/closed on late startup
failure.

The Hub command audit now tests real success and forced failures for clipboard
copy, Dictionary add/delete, Clear History, queued/recovery/history deletion,
audio playback, microphone test, WAV import, History retry/reprocess, and Save
Changes. External failures stay in the Hub as status messages. Worker callbacks
use a guarded Tk post so closing the Hub during background work does not raise.

Clipboard Shield restoration now runs after delivery on a daemon worker instead
of sleeping 1.2 seconds inside the busy dictation lock. A locked generation
manager collapses rapid Flow pastes into the newest restore, preserves the first
real clipboard value, and adopts a newer external clipboard value when another
person or app takes over. Temporary Windows clipboard locks are retried three
times and a persistent failure is visible. The caller path measures 0.0043 ms
median/0.0065 ms p95 across 500 mocked-OS rounds; the actual restore still waits
1.2 seconds in the background so slow target apps can consume the paste safely.

The completed performance work is merged on `main`. Live VAD segments are
capped at 3.5 seconds and Moonshine uses the measured four-thread sweet spot on
this 12-thread machine. The final stop-time benchmark produced 185.2 ms median /
390.6 ms p95 / 453.1 ms max across 50 real-audio runs. A guarded Notepad check
proved exact insertion and isolated Windows delivery at 24.7 ms median / 57.9 ms
max. Tiny recognized only 2/5 complete clips exactly versus Base's 5/5, so Base
remains the quality-safe default. The no-install competitor measurements are
browser-only and must not be presented as a desktop-app ranking.

The merged delivery path inserts completed text before saving WAV/history data,
so ordinary persistence latency or failure cannot suppress the transcript. The
overlay checks cross-thread state every 20 ms, and lazy audio initialization
overlaps model loading. Startup benchmark samples improved from
10048.0/4232.6/4413.4 ms to 3476.3/3416.2/3046.1 ms; medians are used because
the first old run was cold.

`DIFFERENTIATORS.md` is the evidence-backed ten-feature contract. Feature #5,
Clipboard Shield, is implemented: it restores the prior clipboard only when
the Windows clipboard change counter proves no newer data appeared, and falls
back to direct typing if clipboard access is locked.

Feature #1 Crash Journal is implemented. Every recognized segment is fsynced
under `data/recovery/` during normal, command, and continuous sessions. A
successful final history save removes the temporary journal; a crash or failed
save leaves it available for Recovery Inbox.

Recovery Inbox is implemented in the Hub. It lists orphan journals
with a sidebar count, shows the recovered text and metadata, copies it, retries
delivery after hiding the Hub, and confirms removal. Retry deletes the journal
only when History persistence succeeds; failed delivery or failed history save
keeps the recovery copy. Stopped-session audio is atomically fsynced beside the
journal before transcription. Audio-backed rows retry transcription into
History, then remove both recovery files only after that History save succeeds.

Delivery Retry Queue is shipped on `main`. Insertion exceptions
fsync the exact text, intended process/window/title, profile, source, and failure
reason while History saves independently. The Hub lists pending deliveries,
copies/removes them, disables retry when the intended app is closed, and only
focuses a validated original or same-process window before retry. If the queue
write itself fails, Crash Journal remains instead of being falsely completed.

Focus Lock is shipped on `main`. The foreground process/window
is captured before the recording UI appears and compared again immediately before
insertion. A process or document-title mismatch writes the exact text to Delivery
Queue and saves History without calling the keyboard injection path.

Typing Collision Guard is shipped on `main`. A global key-down
counter ignores active recording, snapshots when recording stops, and holds normal
or command delivery when any newer keyboard input appears. Continuous dictation is
excluded because it intentionally delivers while recording remains active.

Pause and Resume is shipped on `main`. The pause shortcut flushes
speech already captured, excludes all new callback audio, and resets VAD on resume
without closing the recovery session. Live phrases skip per-piece History writes;
stop waits for the final VAD segment, then saves one aggregate History item with an
active duration that excludes paused time.

Scoped Undo and Redo is shipped on `main`. Each successful Flow
State insertion remembers its exact payload, target window, and keyboard activity
marker. Tray actions are enabled only while that same window is active and no later
typing occurred; Redo restores the stored payload directly without retranscription.
Delivery Queue retries also become the latest scoped insertion. It is available
from tray commands, configurable Ctrl+Win+Z / Ctrl+Win+Shift+Z hotkeys, and the
voice command hotkey when no text is selected. Flow State's own synthetic keys
are excluded from Typing Collision without ignoring real user takeover.

Reprocess Lab is shipped on `main` and was visually reviewed before merge.
History entries with saved audio open a five-output comparison for Verbatim, Light,
Notes, Email, and Coding. It reuses the saved raw transcript, changes no global
settings or History records, and each result can be copied independently. The
review prototype was an external review artifact, not a runtime dependency.

Local Reliability Dashboard is shipped on `main` and was visually audited.
New History records store a separate exact stop-to-insert value at the keyboard
paste/type moment. Statistics calculates median and nearest-rank p95 only from
those truthful samples, plus current held deliveries, completed recoveries, and
hard-cap warnings from existing local stores. The external review prototype
passed light/dark, narrow/full-width, state-recovery, zero-overflow, and
clean-console checks; it is not required by the shipped native page.

Accuracy Learning is release-ready. The Accuracy page shows every visible
pending correction, approved memory, and the Personal Accuracy Lab readiness
gate. Automatic observations always stay pending until Kariim approves them.
Approved pairs are applied once after Moonshine recognition and are also sent to
Whisper as hotwords. History keeps original, delivered final, and corrected
labels separate. The read-only watcher is limited to the exact inserted range in
standard Windows Edit/RichEdit controls, excludes password fields, stops on
focus/control change, and never writes into the target app. Privacy can clear
learned corrections independently of History.

## Do Next

Collect corrected labels for 12 History entries that have saved audio. Only
after those labels exist should the private engine benchmark download or rank
any candidate.

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
- Automatic correction watching supports standard Windows Edit/RichEdit fields
  only, never password controls; use History's Corrected label everywhere else.
- Every observed correction remains pending until explicit approval. Review
  after 2 matches changes visibility, not approval.
- Candidate-engine ranking is blocked until 12 corrected saved-audio labels
  exist; no candidate download or winner is current.
- Native Tk 8.6.12 now initializes in the desktop runtime. The all-pages test
  needs roughly 75 seconds on its first layout pass, so poll the running test
  process instead of treating a short command-window timeout as a failure.
- `benchmark_flow.py` is the repeatable baseline command. Its 2026-07-11 quick
  run: import median 604.8 ms/p95 790.4 ms, text finish median 0.2 ms/p95
  0.6 ms, text history median 2.3 ms, 10-second audio history median 3.8 ms.
- The guarded live Notepad run now passes exact-text checks. Keep recognition
  and Windows delivery timed separately: delivery measured 24.7 ms median /
  57.9 ms max while Base recognition was load-sensitive.

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
- 2026-07-12 - Wrote one contained recovery WAV after recording stops and before transcription because callback-time disk writes could drop microphone audio; the measured p95 stayed under 50 ms even at the 45-second cap.
- 2026-07-12 - Bound queued retries to a validated saved process/window because retrying into whichever app is currently focused would reproduce the original data-loss risk.
- 2026-07-12 - Rechecked the saved process and compatible document title immediately before insertion because focus can change while transcription runs; mismatches are held without sending any keystroke.
- 2026-07-12 - Used a generation counter instead of timing heuristics for keyboard takeover because one post-stop keypress is enough to make delayed insertion unsafe; the hook costs 0.0003 ms p95.
- 2026-07-12 - Kept continuous mode true through VAD flush and deferred History until session end so pause/resume cannot lose the final phrase or split one session into many History items.
- 2026-07-12 - Scoped Undo/Redo to the exact latest Flow State insertion, HWND, and keyboard generation because a broad Ctrl+Z can undo unrelated user work; Redo reuses stored text and never retranscribes.
- 2026-07-12 - Built Reprocess Lab from the immutable saved raw transcript because five style comparisons should be instant and must never rewrite audio, History, or live app settings.
- 2026-07-12 - Added a separate `delivery_latency` field measured at the real paste/type moment because legacy processing time must not be mislabeled as stop-to-insert; percentile samples exclude older untimed records.
- 2026-07-12 - Kept the Reliability Dashboard factual and local: no decorative trend chart is shown because the current records prove aggregates, not a trustworthy time series.
- 2026-07-12 - Exposed Scoped Undo/Redo through tray, keyboard, and voice; ignored modifier-only and Flow-generated key events so the safety counter catches user takeover without invalidating its own controls.
- 2026-07-12 - Counted completed recovery History records in Reliability rather than pending Recovery Inbox items because "recovered" and "recoverable" are different facts.
- 2026-07-12 - Made the brand F follow the selected accent and use a heavier Bodoni face; compact nav badges are absolutely positioned so every icon keeps one centerline.
- 2026-07-12 - Adopted `#4a4a73` as the light brand accent with `#aaa7d4` for dark-mode contrast, while retaining warm paper neutrals, green success, and red only for danger. The icon generator and waveform pill use the same accent.
- 2026-07-12 - Refined prototype review pins into compact 28px precision markers with concentric rings, alignment pips, dedicated light/dark colors, and controlled depth. Dedicated `--review-pin*` tokens avoid the review overlay's self-referencing `--brand` variable.
- 2026-07-12 - Reused shipped icons/cues instead of redrawing them on every launch; measured normal asset preparation at 0.0609 ms median/0.0868 ms p95 versus roughly 530 ms for icon rendering.
- 2026-07-12 - Measured Moonshine at 1/2/4/6/8 CPU threads and chose four; six and eight regressed. Combined with a 3.5-second VAD cap, the freshest 50 real-audio runs measured 185.2 ms median, 390.6 ms p95, and 453.1 ms max stop-to-text.
- 2026-07-12 - Created the overlay/Hub before background model warm-up and retained the microphone stream globally. Engine-only Hub actions are guarded until Ready, and startup exceptions now show visibly and close any opened stream.
- 2026-07-12 - Audited every Hub command path. Added runtime readiness to Test Microphone; fixed its delayed exception callback losing the cleared Python exception variable; guarded clipboard, Dictionary writes, settings, clear/delete/play actions; and dropped worker callbacks safely after the Hub closes.
- 2026-07-12 - Moved Clipboard Shield's 1.2-second restore wait off the busy dictation lock. A generation/sequence guard preserves the original value across rapid Flow pastes, adopts newer external clipboard data, and reduces caller-side application overhead to 0.0050 ms median/0.0055 ms p95 in 500 rounds.
- 2026-07-12 - Wrapped VAD, transcription, normal finish, and continuous-finish daemon boundaries so one unexpected segment error cannot silently kill dictation. A failed VAD flush releases its waiter immediately, VAD startup falls back to full-buffer capture, and recovery notices stay visible.
- 2026-07-12 - Ran all 14 native Tk tests after the runtime recovered. Fixed the saved-audio Recovery Inbox test to enter the required Ready state explicitly; the production startup guard remained intact. The complete 96-test suite then passed in one 77.149-second process.
- 2026-07-12 - Added a guarded native Notepad benchmark that uses a unique temporary document, verifies every exact saved payload, restores the mouse and clipboard, and closes only its own window. Real delivery measured 24.7 ms median / 57.9 ms max; recognition dominated at 973.3 ms median under load, reproduced by a 929.8 ms engine-only control.
- 2026-07-13 - Kept Moonshine Base as the default after the official Tiny int8 comparison. Tiny cut median recognition from 145.6 ms to 81.3 ms but was exact on only 2/5 complete reference clips versus Base's 5/5, so the speed gain does not justify the measured accuracy loss.
- 2026-07-13 - Applied the approved muted-indigo palette narrowly to the live Hub and overlay after the restart exposed that it had only existed in prototypes. The real dark-mode Hub was visually verified, and the live branch passed 31 tests plus compile and whitespace checks.
- 2026-07-13 - Integrated the exact verified eleven-file reliability bundle without rewriting it. Protected launcher and user-data hashes stayed identical; candidate and live 96-test suites passed; the integrated Hub reached Ready; and guarded Notepad insertion was exact.
- 2026-07-13 - Revalidated the ten differentiators against current official competitor documentation. Wispr, Aqua, and Superwhisper now ship adjacent retry, recent-audio rerun, reprocess, and clipboard features, so the evidence names that overlap and scopes each gap to Flow State's complete guarded behavior. None of the three competitor apps is installed locally; an honest responsiveness ranking still requires a same-machine competitor run rather than vendor WPM claims.
- 2026-07-14 - Merged the complete reliability branch to `main` only after Kariim's fresh approval. Replaced character-count overlay truncation with measured Segoe UI pixel fitting and removed Tk wrapping; the exact merge passed 97 tests, compile, and native Tk bounds verification.
- 2026-07-14 - Added private Accuracy Learning around explicit approval: observed
  edits never alter output until approved, History labels stay separate from
  delivered text, and candidate benchmarking waits for 12 corrected audio
  records. Standard Edit/RichEdit watching is bounded, read-only, and excludes
  password fields; unsupported apps use manual History correction.
- 2026-07-14 - Audited every tracked project document against the merged modules, Hub navigation, icons, feature status, and 97-test suite. Replaced active-branch and isolated-build wording with shipped state, labeled research/wargames as historical artifacts, corrected migration/runtime-data guidance, and verified every local Markdown file reference.
