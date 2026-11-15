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

## Native: schede e reazioni

Il comando `benchmark-native` misura il flusso con persone simulate. Il vecchio `benchmark`
resta dedicato alle valutazioni legacy.

```sh
PYTHONPATH=backend .venv/bin/python -m audience_simulator.cli benchmark-native \
  --scenario-id ID --provider ollama --model qwen2.5:0.5b --concurrency 1
```

Ripetere con `qwen3.5:4b` e con il modello Gemini selezionato nelle impostazioni
(`--provider gemini --model MODELLO`). Cloudflare usa lo stesso comando.
I provider cloud mantengono credenziali, conferma del free tier e quote esistenti;
non c'è alcun passaggio automatico a un altro provider. Il cloud usa concorrenza 1.

Il benchmark legge lo scenario ma scrive esclusivamente in `artifacts/benchmarks/`:
20 profili scelti deterministicamente, le prime due creatività e tre esposizioni nel
regime del primo giorno (120 reazioni). Non cambia la durata dello scenario operativo.
Le schede di riferimento vengono congelate una volta per confrontare le reazioni sugli
stessi testi: se non esistono schede nel pannello sorgente, si usano template dichiarati.
La qualità delle schede generate è un esperimento separato e non cambia i riferimenti.

Ogni configurazione ha un database SQLite separato, un report aggiornato dopo ogni
batch/chiamata e una rubrica cieca `rubric.csv`. Rieseguire lo stesso comando riprende
solo il lavoro mancante. I report distinguono generazione iniziale e passaggio in cache,
contano anche chiamate non valide e attese del rate limiter e riportano i fallback.
Il file `rubric-key.json` contiene la corrispondenza per l'analista: non darlo ai valutatori.
Nessun risultato è qualificato automaticamente come simulazione attendibile.

Per testare il parallelismo locale, impostare `OLLAMA_NUM_PARALLEL=2` nell'ambiente del
**server Ollama** e riavviarlo, poi confrontare il benchmark con `--concurrency 1` e `2`;
provare `4` solo dopo aver verificato memoria e prestazioni. Per le simulazioni applicative
impostare `AUDIENCE_OLLAMA_REACTION_CONCURRENCY` allo stesso valore (intervallo 1–4).
Il default resta 1: i soli thread del backend non abilitano il parallelismo nel server.
Le schede restano sequenziali per preservare il controllo della diversità.

Attivare un valore superiore solo con almeno il 20% di riduzione del tempo sul confronto
completo, senza più fallback e senza regressioni nella rubrica di realismo, coerenza e
grounding. Le metriche automatiche non sostituiscono la valutazione umana.

Durante la creazione delle persone l'interfaccia mostra schede completate, tentativi,
scarti e riuso. Annullare ferma il lavoro dopo la chiamata in corso: le schede valide
rimangono in cache e le nuove richieste non attendono l'intero vecchio pannello.
Una chiamata HTTP già in corso termina normalmente o al timeout del provider.
