# Native efficiency verification — 15 November 2026

Implemented: isolated/resumable native benchmarks, explicit persona constraints, bounded field repairs,
validated versioned cache/provenance, persistent performance counters, informative progress, and bounded
local reaction concurrency (default 1; cloud remains sequential).

## Regression verification

- Backend: 331 tests passed, including a full 120-person / 720-reaction native simulation paused after
  five reactions and resumed with exactly the 715 missing calls.
- Cancellation: the original code continued all four persona batches after cancellation; the new code
  stops after the current batch and preserves valid cards. Concurrent metrics checkpoints cannot undo cancellation. An immediate cancel/resume sequence retains a cancellation identifier so the old execution stops even after the status returns to queued.
- Frontend: typecheck, production build (webpack), six unit tests and 12 browser journeys passed.
- Independent review: retry costs were missing from ETA denominators; fixed with RED/GREEN regression tests.
  Incomplete cached metadata is also rejected before constructing reactions.

## Live measurements and limits

A common frozen fixture was used for Qwen 2.5 0.5B and Gemini 3.5 Flash Lite.
Qwen completed the 20-person card phase with 16 template fallbacks. It saved 16 of 120 reactions before
exhausting retries on a response whose per-100 frequencies did not sum to approximately 100.
The validity constraint was retained. This model is not qualified for this workload by these results.

Gemini generated all 20 benchmark cards without template fallback and saved 28 reactions. That benchmark
was stopped at its checkpoint to reserve the configured provider quota for the user's resumed application run.
Its command can resume without repeating completed cases; see README.md in this directory.

The application API was restarted and the queued native run resumed using its existing Gemini selection,
120 people and all three exposure slots. Persona counts and rejection counters are now observable while it runs.
The upgraded writer invalidates old incompatible cards; historical completed results are preserved.

The full provider/concurrency comparison (including Qwen 4B) and human blind rubric remain pending.
No 20% speed improvement or equivalent predictive quality is claimed. Application concurrency remains 1.
The benchmark's common reference cards, isolated SQLite databases, checkpoints and rubric artifacts are
in artifacts/benchmarks/native-fixtures/ and artifacts/benchmarks/native/ (not committed).
