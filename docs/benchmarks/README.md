# Manifest dei benchmark

Un dominio entra in `VERIFIED_DOMAINS` (`backend/audience_simulator/domain.py`) solo con un manifest qui: `docs/benchmarks/<benchmark_id>.json`.

```json
{
  "benchmark_id": "...",
  "prompt_version": "consumer-policy-v7",
  "model": "gemini-3.5-flash-lite",
  "config_hash": "hash della configurazione congelata",
  "test_report": "validation/test-report-<hash12>.json",
  "promise_sha256": "hash di docs/PROMISE.md al congelamento",
  "criteria_met": true
}
```

`registry_problems()` (verificato da `tests/test_domain.py`) fallisce se una voce del registro non ha un manifest con lo stesso prompt e modello. Cambiare prompt o modello riporta lo stato a «non verificato per questa configurazione» finché non si ripete il benchmark.

Nessun manifest esiste ancora: il registro è vuoto.
