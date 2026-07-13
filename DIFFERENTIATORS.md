# Flow State Differentiators

Validated 2026-07-13 against the public feature documentation for Wispr Flow,
Aqua Voice, and Superwhisper. "Gap" means none of those three documents the
complete behavior below. It is not a claim about every private or unpublished
dictation tool. Several competitors now ship adjacent retry, history,
reprocessing, or clipboard features; those are called out below instead of
being presented as absent.

## Release Gate

Reliability, speed, and accuracy remain release gates. A feature does not ship
if it raises stop-to-insert p95, loses captured speech, overwrites newer user
input, or weakens offline operation.

## The Ten

| # | Feature | Community need | Top-three gap | Acceptance proof |
|---|---|---|---|---|
| 1 | Crash Journal | Users request a live transcript file so a crash cannot erase a long session. | High | Every completed speech segment is durably appended within 100 ms; killing the app leaves a readable orphan session. |
| 2 | Recovery Inbox | Users report cut-short and deleted recordings with no recovery path. | High | Restart lists orphan journals/audio, supports retry, and never touches files outside Flow State recovery storage. |
| 3 | Pause and Resume | Superwhisper's public board lists pause recording among its highest-voted pending requests. | High | Pause excludes new audio without ending the session; resume continues the same history item and timer. |
| 4 | Focus Lock | Users complain delayed dictation can land after they switch apps or resume typing. | High | If the destination changes after recording starts, Flow State holds the exact text in Delivery Queue instead of pasting into the wrong app. |
| 5 | Clipboard Shield | Wispr Flow and Superwhisper users report stale or overwritten clipboard content. | High | Flow State restores the prior clipboard only when no person or app changed it after Flow State's paste. |
| 6 | Delivery Retry Queue | Users report successful transcription with nothing inserted or an older transcript pasted. | High | A failed/held delivery remains one click away, records its intended app, and can retry without retranscription. |
| 7 | Reprocess Lab | Superwhisper users request reprocessing old audio with different modes and settings. | High | One recording can preview Verbatim, Light, Notes, Email, and Coding outputs side by side without altering the original. |
| 8 | Scoped Undo and Redo | Aqua's launch community asked for undo/redo through voice, GUI, and keyboard. | Medium | Undo is offered only for the same target and latest Flow State insertion; redo restores the exact text without retranscription. |
| 9 | Typing Collision Guard | Aqua users explicitly asked the app not to interfere once they take over with the keyboard. | High | Keyboard input after dictation stops causes delivery to hold instead of pasting over newer work. |
| 10 | Local Reliability Dashboard | Communities consistently rank reliability and latency ahead of advanced modes. | High | Statistics reports median/p95 stop-to-insert, held/failed deliveries, recovered sessions, and cut-off warnings entirely from local records. |

## Evidence

- Superwhisper's public board documents sustained demand for a true recording
  pause that can resume the same session:
  <https://feedback.superwhisper.com/board/p/pause-recording>
- Superwhisper already supports processing a History item again with the
  currently active mode. Flow State's gap is the complete Reprocess Lab
  behavior: five outputs shown together without changing the original or live
  settings:
  <https://superwhisper.com/docs/get-started/transcribe-history>
- Aqua keeps recent audio for three days and can rerun transcription. Flow
  State's gap is the complete durable crash-journal, orphan-inbox, and guarded
  recovery behavior rather than basic History replay:
  <https://aquavoice.com/guide/history>
- Wispr Flow now preserves audio for many failed transcriptions and supports
  retry from History, but its own documentation says a force-quit or crash
  during dictation cannot be recovered. Flow State journals completed speech
  segments before that failure boundary:
  <https://docs.wisprflow.ai/articles/2503460374-retry-failed-transcriptions>
- Superwhisper users request a live transcript streamed into a file specifically
  for crash recovery:
  <https://feedback.superwhisper.com/board/p/live-transcript-into-a-text-file>
- A current Superwhisper report describes intermittently cut-short recordings:
  <https://feedback.superwhisper.com/board/p/recordings-getting-cut-short>
- A current Superwhisper request describes 2-3 seconds of post-stop delay and
  switching focus before paste:
  <https://feedback.superwhisper.com/board/p/server-side-transcription-polish-chaining-for-hosted-batch>
- Superwhisper users request an option that does not overwrite their clipboard:
  <https://feedback.superwhisper.com/board/p/allow-disable-save-to-clipboard>
- Superwhisper supports restoring the clipboard on macOS but documents that it
  is not supported on Windows. Wispr Flow likewise documents automatic restore
  on Mac but not Windows. Flow State's Windows Clipboard Shield additionally
  refuses to overwrite clipboard data changed after its paste:
  <https://superwhisper.com/docs/get-started/windows>
  and
  <https://docs.wisprflow.ai/articles/7971211038-fix-text-not-pasting-after-dictation>
- Aqua's launch discussion asks for proper undo/redo, cursor-correct insertion,
  pause/resume, and no interference after keyboard takeover:
  <https://news.ycombinator.com/item?id=39828686>
- Aqua's later launch discussion asks for a separate hotkey that sends output to
  a specific app:
  <https://news.ycombinator.com/item?id=43634005>
- Wispr Flow users report stale/previous transcripts and clipboard content being
  pasted instead of current dictation:
  <https://www.reddit.com/r/WisprFlow/comments/1turxe0/what_is_going_on_with_wisprflow_recently/>
  and
  <https://www.reddit.com/r/WisprFlow/comments/1sp2qb8/wisprflow_clipboard_bug_on_windows_desktop/>
- Wispr Flow users also value recoverable transcript history when insertion
  misses the target:
  <https://www.reddit.com/r/WisprFlow/comments/1tb04ty/wisprflow_best_product_ive_ever_used/>

## Competitor Boundary

Do not count these as differentiators: offline processing, real-time text,
history, dictionary, snippets, app-aware styles, raw-versus-polished text,
file transcription, meeting notes, custom modes, language support, syntax
awareness, or usage statistics. At least one major competitor already ships
each of them.

## Build Order

1. Data safety: Crash Journal, Recovery Inbox, Delivery Retry Queue.
2. Safe insertion: Clipboard Shield, Focus Lock, Typing Collision Guard.
3. Session control: Pause/Resume, Scoped Undo/Redo.
4. Recovery quality: Reprocess Lab.
5. Trust: Local Reliability Dashboard and the final performance audit.

## Implementation Status

- [x] #1 Crash Journal - fsynced partial segments wired into normal, command,
  and continuous dictation; 20-write p95 4.7 ms; containment bite proof and
  full suite verified 2026-07-13.
- [x] #2 Recovery Inbox - orphan text and stopped-session audio have a native
  Hub inbox, copy, guarded retry delivery/re-transcription, confirmed contained
  removal, native visual verification, and p95 recovery-WAV writes under 50 ms.
- [x] #3 Pause and Resume - excludes paused audio, flushes/resets VAD, preserves
  one recovery session, one paused-adjusted timer, and one aggregate History item.
- [x] #4 Focus Lock - captures process/window/title before recording UI, holds
  mismatches in Delivery Queue without injection, and adds only 0.036 ms p95.
- [x] #5 Clipboard Shield - sequence-aware restore plus direct-typing fallback;
  temporary Windows locks retry three times, persistent failure is visible,
  and sequence/restore/fallback bite proofs pass in the full suite.
- [x] #6 Delivery Retry Queue - fsynced exact text plus intended process/window,
  guarded same-target retry, copy/removal UI, unavailable-target blocking, and
  0.8 ms median/1.3 ms p95 queue persistence.
- [x] #7 Reprocess Lab - saved-audio History items preview Verbatim, Light,
  Notes, Email, and Coding together without changing the original or settings.
- [x] #8 Scoped Undo and Redo - tray actions, configurable hotkeys, and spoken
  undo/redo require the exact active target and unchanged keyboard generation;
  Redo reinserts the exact stored payload.
- [x] #9 Typing Collision Guard - post-stop key-down generation mismatch holds
  delivery before injection; bite proof and 0.0003 ms p95 hook overhead.
- [x] #10 Local Reliability Dashboard - local exact paste-time median/p95,
  current held counts, completed recoveries, cutoff warnings, and audited UI.

## Verification Matrix

| # | Direct evidence |
|---|---|
| 1 | `RecoveryJournalTests`, runtime journal wiring tests, and 100 fsynced appends at 2.651 ms p95 / 3.212 ms max. |
| 2 | Recovery text/audio lifecycle and containment tests plus native copy, retry, retain-on-failure, and confirmed-remove tests. |
| 3 | Paused callback exclusion, same-session resume, paused-adjusted timer, final VAD flush, and one aggregate History test. |
| 4 | Changed-target and compatible-target runtime tests prove injection is blocked only for mismatches. |
| 5 | Clipboard sequence-change, unchanged restore, temporary-lock retry, persistent-lock notice, rapid-paste, external-takeover, and direct-typing fallback tests. |
| 6 | Fsynced queue round-trip, target focus, unavailable-target, retention, copy, retry, and removal tests. |
| 7 | Five-mode immutable preview test, review prototype, and native Copy/Back button test. |
| 8 | Exact-target/generation Undo/Redo test, retry-as-latest test, hotkey registration, synthetic-key exclusion, and voice-routing tests. |
| 9 | Post-stop key generation hold test plus ordinary-key 0.002661 ms p95 and hotkey-branch 0.029984 ms p95. |
| 10 | Exact paste-time, nearest-rank median/p95, completed recovery, cutoff tests, plus responsive light/dark loading and ready-state prototypes. |

The complete 96-test suite passes in one process, including all 14 native Tk
page/button tests. Eight Python, test, and benchmark files compile. Real
Notepad verification proved exact insertion and isolated Windows delivery at
24.7 ms median / 57.9 ms max. Official Tiny testing cut recognition latency but
was word-exact on only 2/5 complete clips versus Base's 5/5, so Base remains the
quality-safe default. Unconditional competitor-speed claims remain gated on an
apples-to-apples competitor run rather than a vendor marketing number.
