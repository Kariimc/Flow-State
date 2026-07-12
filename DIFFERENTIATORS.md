# Flow State Differentiators

Validated 2026-07-11 against the public feature documentation for Wispr Flow,
Aqua Voice, and Superwhisper. "Gap" means none of those three documents the
complete behavior below. It is not a claim about every private or unpublished
dictation tool.

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
| 4 | Focus Lock | Users complain delayed dictation can land after they switch apps or resume typing. | High | If the destination changes after recording starts, Flow State holds the text in Recovery instead of pasting into the wrong app. |
| 5 | Clipboard Shield | Wispr Flow and Superwhisper users report stale or overwritten clipboard content. | High | Flow State restores the prior clipboard only when no person or app changed it after Flow State's paste. |
| 6 | Delivery Retry Queue | Users report successful transcription with nothing inserted or an older transcript pasted. | High | A failed/held delivery remains one click away, records its intended app, and can retry without retranscription. |
| 7 | Reprocess Lab | Superwhisper users request reprocessing old audio with different modes and settings. | High | One recording can preview Verbatim, Light, Notes, Email, and Coding outputs side by side without altering the original. |
| 8 | Scoped Undo and Redo | Aqua's launch community asked for undo/redo through voice, GUI, and keyboard. | Medium | Undo is offered only for the same target and latest Flow State insertion; redo restores the exact text without retranscription. |
| 9 | Typing Collision Guard | Aqua users explicitly asked the app not to interfere once they take over with the keyboard. | High | Keyboard input after dictation stops causes delivery to hold instead of pasting over newer work. |
| 10 | Local Reliability Dashboard | Communities consistently rank reliability and latency ahead of advanced modes. | High | Statistics reports median/p95 stop-to-insert, held/failed deliveries, recovered sessions, and cut-off warnings entirely from local records. |

## Evidence

- Superwhisper's top feature board lists **Pause Recording** as reviewing with
  substantial votes and **Re-process with different settings** as pending:
  <https://feedback.superwhisper.com/board/features?cursor=1&limit=10&order=top>
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
  full suite verified 2026-07-11.
- [ ] #2 Recovery Inbox
- [ ] #3 Pause and Resume
- [ ] #4 Focus Lock
- [x] #5 Clipboard Shield - sequence-aware restore plus direct-typing fallback;
  bite proof and full suite verified 2026-07-11.
- [ ] #6 Delivery Retry Queue
- [ ] #7 Reprocess Lab
- [ ] #8 Scoped Undo and Redo
- [ ] #9 Typing Collision Guard
- [ ] #10 Local Reliability Dashboard
