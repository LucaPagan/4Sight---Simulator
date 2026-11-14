# Calibrazione e distribuzione separata (fase 4)

Stato: 14 novembre 2026. Il codice e i test sono pronti. **Nessuna calibrazione è stata ancora appresa**: servono le valutazioni del panel sulle campagne di sviluppo, cioè chiamate LLM (vedi «Costo»). Finché non esiste una calibrazione che supera la verifica e un dominio verificato, il panel **non** modifica nessun KPI aggregato.

## 5 · Dal panel ai KPI (`calibration.py`)

- **Feature per creatività**: media pesata sui profili di interesse, chiarezza, credibilità, frizione (scala −1…+1) e quota di `consider_click` e `not_interested`. `conditional_action` entra **solo** qui, attraverso una funzione appresa; i gate ipotetici di `behavior.py` restano usati solo per ripartire il totale fra età e gate.
- **Modello relativo**: regressione ridge senza intercetta della differenza di log-odds di CTR osservata tra due creatività della stessa campagna sulla differenza delle loro feature, con pesi di varianza inversa. Non conosce il livello assoluto del CTR: può cambiare la posizione relativa delle creatività, mai il CTR medio della campagna.
- **Verifica**: validazione incrociata a gruppi (per campagna) su sviluppo; `alpha` scelto per perdita fuori campione; scala `s*` stimata fuori campione e limitata a [0, 1]. **Gate**: l'estremo inferiore al 95% (bootstrap per campagna) del miglioramento di perdita contro «nessuna differenza» deve essere > 0 e `s*` > 0. Se non passa, `beta = 0` e lo spostamento è esattamente zero.
- **Applicazione** (`service.panel_calibration`): lo spostamento si applica solo se esiste `validation/calibration.json`, il gate è passato **e** il dominio del brief è verificato per (prompt, modello) in `domain.VERIFIED_DOMAINS` (oggi vuoto). Altrimenti il risultato riporta `panel_calibration.applied = false` con il motivo, e `measurement_status.agents_change_aggregate_kpis = false`. Con spostamento applicato cambiano CTR e clic; impression, CPM e spesa no, e le stime per età si riconciliano al nuovo totale.
- **Benchmark non pubblicitario**: la calibrazione appresa su titoli di news USA non si applica a un brief ecommerce italiano, perché `VERIFIED_DOMAINS` non lo contiene. È voluto.

## 6 · Distribuzione (`delivery.py`)

L'allocazione della spesa (budget, utilizzo storico, allocazione storica tra annunci) è stata estratta da `forecasting.forecast` senza cambiare l'ordine dei numeri casuali (i risultati dei test di previsione non cambiano). Il modulo non legge nessuna valutazione del panel. Impression = spesa / CPM; clic = impression × CTR. Il rapporto dichiara `delivery.mode = history_allocation_independent_of_panel`. L'ottimizzazione della piattaforma verso la creatività migliore **non è modellata** e non viene simulata con parametri inventati.

## Strumenti per ottenere i dati (nessuna chiamata finora)

```sh
# 1. punteggi del panel (B2) e dell'LLM senza profili (B1) su un campione di sviluppo, riprendibile
.venv/bin/python -m audience_simulator.cli panel --system B2 --split dev --campaigns 100 --panel-size 30 --max-new 500
.venv/bin/python -m audience_simulator.cli panel --system B1 --split dev --campaigns 100 --max-new 500
# 2. apprendere la calibrazione e confrontare B0/B1/B2 su sviluppo
.venv/bin/python -m audience_simulator.cli calibrate fit --system B2
.venv/bin/python -m audience_simulator.cli verify run --split dev
```

Sul test, `panel --split test` richiede la configurazione congelata ed esegue solo input; `calibrate score --system B2 --split test` produce i punteggi usando i pesi appresi su sviluppo; gli esiti si leggono soltanto con `verify run --split test --final`.

**Costo**: 100 campagne di sviluppo × ~3,6 varianti × 30 profili ≈ 10.800 chiamate per B2 (≈ 18 ore a 10 richieste al minuto) più ≈ 360 per B1. Il pannello del test (60 campagne) ne richiede altre ≈ 6.500. La quota giornaliera del piano gratuito può imporre più sessioni: lo strumento riprende dalla cache.

**Limite**: sul corpus il pannello usa profili `profiles-v1` con mix d'età uniforme (non esiste una marginale Eurostat per i lettori USA). La verifica del benchmark riguarda quindi la meccanica del panel, non l'audience osservata del pannello v2.
