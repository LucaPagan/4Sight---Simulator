# Native efficiency implementation ledger

Approved specification: the five-part implementation plan in this chat (15 November 2026).

Goal: more valid native results per minute without reducing 120 personas, creatives or exposure slots.
Constraints: existing providers, manual selection, no new dependencies, validation and resumability retained.

## Incremental tasks
- [ ] Instrumentation and isolated resumable native benchmark (20 profiles, two creatives, three slots).
- [ ] Explicit persona constraints, bounded partial repair and validated cache/provenance.
- [ ] Persistent performance contracts and UI progress, compatible materialized cards.
- [ ] Bounded local reaction concurrency with coordinator-owned persistence and cancellation.
- [ ] Full tests, frontend verification, benchmark/rubric artifacts and independent review.

Each increment uses regression tests before implementation and is committed after verification.
Implementation uses Superpowers executing-plans and test-driven-development, then a fresh whole-branch review.
Default local concurrency stays 1 unless measured speed and quality justify increasing it.

## Acceptance
Compare cold and cached paths; include failed calls, retry and pacing costs. Retain historical run compatibility.
Exercise malformed output, partial repairs, cache invalidation, out-of-order completion, cancellation, quota and recovery.
Benchmark targets >=20% improvement with no increased fallback or quality regression; do not assert equivalence without evidence.
