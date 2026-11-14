# Incertezza e condizioni d'uso (fase 5)

Stato: 14 novembre 2026. Il motore non emette più un «vincitore» senza dichiarare se il dominio è verificato. Il registro dei domini verificati è vuoto, quindi **oggi ogni confronto è `out_of_domain`**.

## Esiti del confronto (`reporting.compare_predictions`)

Per ogni coppia di creatività, `decision`:
- `out_of_domain`: settore, paese, obiettivo, placement o lingua non sono in un dominio verificato, oppure il prompt o il modello non coincidono con quelli verificati (`domain_assessment.status` distingue i due casi e dà il motivo). Il modello mostra comunque `model_leader` e la differenza stimata come ipotesi.
- `winner`: dominio e configurazione verificati e differenza oltre la soglia statistica del modello (≥ 95% di probabilità, banda di pareggio ±0,1 punti di CTR).
- `unresolvable_difference`: dominio verificato ma differenza dentro l'incertezza.

I campi precedenti (`winner`, `status`, probabilità) restano per audit.

## Intervalli (`calibration.py`, `validation.py`)

La calibrazione salva un intervallo conformal split al 90% sui residui fuori campione, in log-odds di CTR relativo. `verify run` riporta `interval_coverage` per B1/B2: la copertura osservata contro il livello nominale. Su sviluppo la copertura è vicina al 90% per costruzione; il controllo reale è quella misurata sul test, una sola volta. Le coppie della stessa campagna sono correlate: la copertura è approssimata.

Gli intervalli del forecast aggregato del kit (Monte Carlo sui residui storici) restano quelli già documentati: copertura 97,5% nominale 90%, quindi prudenti sul kit simulato. Non sono stati ricalibrati su campagne reali.

## Registro e ripetizione dei benchmark

`domain.assess_domain` verifica ogni run contro il registro. `registry_problems()` e `tests/test_domain.py` fanno fallire la suite se una voce del registro non ha un manifest in `docs/benchmarks/` con lo stesso prompt e modello. Il formato del manifest è in `docs/benchmarks/README.md`.

## Frontend (modifiche minime)

- `results-view.tsx`: per `out_of_domain` il verdetto è «Nessun vincitore verificato», con il leader del modello indicato come ipotesi.
- `new-simulation.tsx`: campi «Offerta», «Prezzo mostrato» e «Pagina dopo il clic» per ogni creatività (facoltativi).
- Verificati: `tsc`, test unitari, build di produzione e i 4 test e2e Playwright (Chromium installato il 14 novembre 2026). Due nuovi e2e in `frontend/e2e/journeys.spec.ts` coprono il verdetto `out_of_domain` (titolo «Nessun vincitore verificato», nessuna creatività «consigliata») e il passaggio di Offerta, Prezzo mostrato e Pagina dopo il clic fino alla richiesta di creazione dello scenario. Ora gli e2e sono 6 e passano; l'API è mockata, quindi non provano il backend.
