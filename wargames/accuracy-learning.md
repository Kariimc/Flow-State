# Flow State Accuracy Learning Wargame

## Mission

Ship reviewed correction memory, bounded post-insertion edit detection, and a
personal accuracy baseline without changing existing transcript history or
claiming an unmeasured engine winner.

## Moves

1. Add pure correction extraction and an atomic local `CorrectionStore`.
   - Expected: repeated pairs deduplicate, approval gates application, corrupt
     files fail closed, and history corrections preserve `original`/`final`.
   - Failure: a malformed or concurrent write loses data. Cause: non-atomic
     persistence. Counter: lock, temporary file, fsync, `os.replace`, and tests.
2. Apply only approved pairs after recognition and pass approved replacement
   terms to Whisper's supported hotword prompt.
   - Expected: pending/rejected pairs never affect text; Moonshine still gains
     deterministic post-recognition correction.
   - Failure: corrections cascade. Cause: applying short rules before long
     phrases. Counter: longest spoken phrase first and one pass per rule.
3. Add a bounded Windows standard-edit watcher after successful insertion.
   - Expected: it reads only the same focused control for 12 seconds, records
     small replacement spans as pending, and stops on focus/control change.
   - Failure: SendMessage hangs on another process. Cause: unbounded Win32 IPC.
     Counter: `SendMessageTimeoutW`; unsupported controls return unavailable.
   - Fork: if a control cannot expose text and selection through standard Win32
     messages, skip automatic capture and rely on History's Save correction.
4. Add History correction editing and an Accuracy Hub page.
   - Expected: corrected labels remain separate from delivered text; pending
     pairs can be approved/rejected; baseline readiness uses real saved audio.
   - Failure: destructive mutation of history. Cause: replacing `final`.
     Counter: write only `corrected` and `corrected_at`; regression test.
5. Verify red-green bite, full tests, compile, native Hub render, docs, and git.
   - Expected: every gate is green on the exact merge tree.
   - Failure: native Tk or live startup diverges from mocks. Counter: run the
     existing all-page Hub test and a real local launch/IPC check.

## Recon Needed

- Candidate engine downloads and comparative scores remain gated until at
  least 12 corrected audio records exist. No download or winner claim now.

## Abort Conditions

- Any watcher path writes to or sends keys into the target application.
- Any correction changes `original`, `final`, audio, or an existing dictionary.
- Any candidate score is shown without corrected audio ground truth.
- Any test, compile, review, or repository gate remains red.

## Verification

- Focused correction-store tests, including corrupt input and atomic history.
- Bite proof: remove approval filtering, confirm pending correction test fails,
  restore, and confirm green.
- Runtime tests for bounded watcher start/stop and Whisper hints.
- Hub all-page command test plus Accuracy workflow test.
- Full `unittest`, isolated `py_compile`, `git diff --check`, and clean status.

## Red Team

Attack: a user rewrites unrelated text in the same document during the watch
window, creating a false learned pair.

Patch: accept only replacement spans that overlap Flow State's exact inserted
character range, cap each side at eight tokens, keep the result pending, and
show its source in review. Insertions/deletions alone are not learned.

## Self-grade

8/8: observations, failures, counters, fork trigger, recon, aborts,
verification, and red-team patch are explicit.