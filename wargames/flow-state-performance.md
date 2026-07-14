# Flow State Performance and Differentiation Wargame

Mission: make Flow State measurably faster and more dependable, then ship ten
evidence-backed differentiators without weakening its local-first core.

Status: completed and merged to `main` in `f13ab0a`. This file is the preserved
pre-build plan; current evidence is in `DIFFERENTIATORS.md` and `PROGRESS.md`.

## Moves

1. Capture a repeatable baseline for import, engine load, warm inference,
   key-to-overlay dispatch, stop-to-insert, history writes, Hub page changes,
   and memory. Expected: each metric has raw timings. Failure: synthetic timing
   misses real waits; counter: pair microbenchmarks with a live Notepad run.
2. Build control-path tests before changing runtime behavior. Expected: every
   Hub command and dictation state transition has a success, cancel, and error
   result. Failure: Tk tests require a visible desktop; counter: test callbacks
   with stubs, then run a separate GUI smoke pass. Abort on text or history loss.
3. Remove measured latency in small commits. Expected: lower median and p95
   timings without higher idle CPU or memory. Failure: faster polling burns CPU;
   counter: prefer removing blocking work from the delivery path.
4. Refresh Wispr Flow, Aqua Voice, and Superwhisper capabilities from official
   sources and community requests from dated public discussions. Expected: each
   proposed differentiator maps to demand and a competitor gap. Failure: a
   feature is merely uncommon, not unique; counter: label it honestly and never
   claim exclusivity without proof.
5. Ship the ten features in independent, reversible slices. Expected: each has
   tests, working UI, docs, and a measurable user outcome. Failure: feature
   count outruns core quality; trigger: reliability, speed, or accuracy gate
   regresses, then pause feature work and repair the gate.
6. Run a requirement-by-requirement audit. Expected: fresh full-suite output,
   benchmark comparison, control matrix, UI screenshots, live dictation, clean
   diff, and no secrets. Failure: any claim lacks direct evidence; counter:
   downgrade the claim or keep the goal open.

## Recon Needed

- Obtain reproducible real-speech samples before comparing recognition delay.
- Verify competitor features that sit behind account-only screens.
- Measure idle CPU with the live tray process, not an import-only process.

## Abort Conditions

- Any change risks losing dictated text, selected text, or saved history.
- A benchmark improves only by disabling privacy, cleanup, or persistence.
- A competitor-exclusive claim relies on search snippets or one secondary post.
- Existing user settings or recordings would be overwritten.

## Verification

- New tests prove red on old behavior and green on the fix.
- Full unit suite and compile checks pass after every runtime slice.
- Benchmarks report median and p95 across repeated runs.
- GUI smoke activates every visible button and control without uncaught errors.
- Final live Notepad run proves hold, tap, continuous, command, and cancel paths.

## Red Team

Attack: chasing ten novelty features can make the core slower and less reliable,
which current users explicitly rank above advanced features.

Patch: performance and control reliability are release gates; feature work stops
whenever either regresses. Each feature must remove a documented user pain, not
merely increase the count.

Self-grade: 8/8. Every move has an expected observation, failure, counter-move,
explicit triggers, recon, aborts, verification, and a recorded red-team patch.
