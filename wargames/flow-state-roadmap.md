# Flow State Roadmap Wargame

Mission: ship the approved Hub redesign and the locally feasible competitor
roadmap without regressing the existing offline dictation path.

Status: completed and merged to `main`. This file preserves the original plan
and its old baseline commit; current architecture and verification live in
`HANDOFF.md` and `PROGRESS.md`.

## Moves

1. Preserve the baseline.
   - Action: record git status, current commit, launcher metadata, runtime paths,
     and a copy of the current application file.
   - Expected: clean tracked tree at `fbed4df`; runtime failure points to the
     migrated Python home; shortcut points to the old sandbox user.
   - Likely failure: hidden user changes appear. Cause: stale status or ignored
     runtime files. Counter: never overwrite ignored user history/settings and
     stop if tracked changes appear.

2. Repair the runtime and launcher before feature work.
   - Action: repoint the existing venv to the available Python 3.12 runtime,
     verify imports, and rewrite only the Flow State shortcut target/icon.
   - Expected: `.venv\Scripts\python.exe` imports all eight requirements and
     the shortcut resolves to files under `C:\Users\Kariim\flow-state`.
   - Likely failure: ABI mismatch. Cause: bundled Python patch-level or missing
     DLL. Counter: create a fresh `.venv-new`, install locked requirements,
     verify, then swap only after success.
   - Fork trigger: if import verification fails, take fresh-venv route.

3. Fix the floating pill and icon parity.
   - Action: keep pill coordinates and dimensions fixed; reduce the microphone
     badge/glyph footprint; derive tray states from `models\flow.ico`.
   - Expected: microphone art remains inside y=3..23 with even padding; tray and
     desktop share the waveform icon silhouette while state tint changes.
   - Likely failure: Windows tray caches the old icon. Cause: shell cache.
     Counter: verify generated pixel data and restart only the app process
     started by this session; do not kill Explorer.

4. Add durable data and pure processing primitives.
   - Action: JSONL history metadata + WAV recording storage, retention,
     statistics, profiles, deterministic Polish/self-correction, command
     transforms, file WAV transcription, and migration from history.txt.
   - Expected: old history remains readable; new entries include id, time,
     original/final text, duration, latency, engine, profile, and audio path.
   - Likely failure: partial write corrupts history. Cause: interrupted direct
     write. Counter: append JSONL records and use atomic temp/replace for
     rewrites.
   - Fork trigger: malformed JSONL lines are skipped and surfaced, never allowed
     to block startup.

5. Wire the recording pipeline.
   - Action: save each completed recording, publish live partial text to the
     overlay/Hub, apply active-app profile and Polish, add retry/reprocess, and
     add selected-text command hotkey.
   - Expected: existing hold/tap/continuous paths still inject text; recovery
     retains audio; command mode restores the clipboard and replaces only the
     selected text.
   - Likely failure: command mode destroys clipboard or selection. Cause:
     timing/focus race. Counter: capture/restore clipboard with bounded waits,
     preserve original selection on failure, and never delete source text until
     a transformed result exists.
   - Abort: any test demonstrates text loss or unbounded waits.

6. Replace the Hub with the approved settings workspace.
   - Action: Tkinter left navigation, graph-paper content, light/night drafting
     themes, visible red-knob toggles, grouped controls, history details,
     dictionary vocabulary/replacements, profiles, audio, appearance, privacy,
     files, meetings capability state, and statistics.
   - Expected: every visible control either changes real behavior or clearly
     states why it is unavailable.
   - Likely failure: Tkinter layout clips at DPI scaling. Cause: fixed geometry.
     Counter: scrollable content, minimum sizes, and screenshot checks at 100%
     and scaled desktop DPI.

7. Verify in layers.
   - Action: pure unit tests, syntax/import check, runtime import check, generated
     SAPI WAV transcription, settings/history round trips, screenshot pixel
     bounds for mic/Hub, shortcut metadata, and real Notepad injection.
   - Expected: all checks pass and screenshots show no overlap.
   - Likely failure: GUI/audio test steals focus or conflicts with an existing
     instance. Cause: live app state. Counter: use isolated component tests
     first; launch one session-owned process only for final end-to-end.

8. Ship and hand off.
   - Action: review diff for secrets/personal history, update README/PROGRESS,
     commit project changes, update Relay, and push both.
   - Expected: clean tracked trees and pushed commits.
   - Likely failure: remote/CI rejection. Cause: network or gate. Counter: fix
     the failure and retry; never bypass a gate.

## Recon Needed

- Verify whether the repointed venv imports compiled packages before editing it.
- Query actual microphone devices after runtime repair.
- Verify whether Windows selected-text replacement works in Notepad with the
  chosen clipboard timing.
- Confirm generated tray icons retain visible detail at 16x16.

## Abort Conditions

- Tracked user changes appear after baseline capture.
- Runtime repair would require deleting the only working environment before a
  replacement verifies.
- Any recovery/history operation can overwrite or delete existing history.
- Selected-text command mode can lose the original text.
- A required dependency would need an unreviewed network install.

## Verification Checklist

- `python -m unittest -v` passes.
- Removing each storage/deletion guard makes its bite test fail, then restoring
  returns green.
- `python -m py_compile flow.py` passes.
- All runtime imports pass inside `.venv`.
- SAPI-generated WAV transcribes through the selected engine.
- Hub and overlay screenshots have non-background pixels within expected bounds.
- Shortcut target, working directory, and icon all exist.
- Notepad receives dictated text in the final live run.
- `git diff --check` and secret scan are clean.

## Red Team

Attack: bundling all roadmap work into the existing 1,400-line file can make a
GUI change destabilize the hotkey/audio path and makes rollback too coarse.

Patch: build pure data/processing behavior in one small `flow_features.py`
module with isolated tests, leave capture/hotkey logic in `flow.py`, and land
small commits in this order: runtime/overlay/icon, data/features, Hub, live
wiring, docs. Existing runtime data files remain ignored and untouched.

Self-grade: 8/8. Every move has an observation and counter; forks, recon,
abort conditions, verification, red-team attack, and patch are explicit.
