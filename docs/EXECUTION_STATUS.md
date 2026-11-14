# Stato verificato — 14 novembre 2026

## Software disponibile

Percorso completo: brief e creatività → pubblico sintetico120profili/6fasce → preflight → valutazioni individuali → gate/memoria → KPI calibrati/dettaglio età → confronto/diagnosi/export. Modalità Ollama locale, Gemini e Cloudflare Workers AI selezionabili per nuova run. Il provider/modello è fissato nella run e le cache rimangono separate. Chiavi private0600, mai in report/SQLite/S3. Code/executor locale e cloud separati; limiter condiviso fra prove e panel anche tra processi.

Import dataset transazionale con copie immutabili e hash; feature in-time, model registry, backtest, forecast699+4194fasce; riconciliazione numerica di CTR/impression/clic/spesa; ripresa da cache, annullamento protetto da pubblicazione atomica; API/OpenAPI e tipiTS generati; UI brief/libreria/pubblico/risultati/storico/fonti/validation/modelli; Docker/PostgreSQL/RQ/S3 e CI; runner ablation, retention e README.

## Verifiche concluse

- **63test Python passati**,2test Node passati; Ruff e mypy24moduli senza errori; typecheck e build Next passati. Un warning di deprecazione nel TestClient FastAPI non impedisce la suite.
- Test di panel completo120×2 sui tre vertical con trasporto HTTP controllato, copertura/ripresa/cache/snapshot, frazione incompleta, quota cloud e provider isolati. Non sono una validazione comportamentale dei modelli reali.
- Integrazione reale Docker: import PostgreSQL, Redis/RQ, scrittura/lettura S3, API health; code default/cloud sottoposte a smoke con job aritmetici. Migrazione Alembic iniziale verificata. Ollama raggiungibile dal container.
- Esportazioni reali:699righe aggregate e4194fasce in artifacts/official, tutte **preliminary** rispetto al panel LLM.
- Revisione indipendente originale e revisioni delle estensioni cloud; corretti dataset attivo/snapshot, race annullamento, pesi esposizioni, calibrazione CPM, diagnosi dal panel, selezione creatività nello storico, calendario multiennale, resume terminale, versione prompt; cloud separato dal worker locale, limiter condiviso, thinking Cloudflare disabilitato per evitare troncamenti e spreco di quota.

## Risultati statistici effettivi

Modello aggregate-v4.1435righe training al01/11,444validation02–15/11. CTR weightedMAE0,2447punti percentuali contro0,2844della baseline di confronto; CPMMAE0,888€. Coverage degli intervalli90%:CTR97,52%,CPM95,95%. Residui fuori campione interni al training, con variabilità sia fra giorni sia entro giorno. Lo stato automatico è validated_on_validation, con limite esplicito: la validation è usata anche per la selezione e non è un test futuro indipendente. Nessuno score sul futuro o accuratezza per età.

## Modelli reali e verifiche aperte

- Qwen3.5-9B,4B e Ministral3-8B installati e provati. Alcuni prompt iniziali fallivano; il contratto corrente consumer-policy-v6 valida riferimenti e forma JSON. Nessuna qualifica artificiale dei candidati.
- L'utente ha configurato Gemini e avviato una run reale120×2 con Gemini3.5Flash-Lite. Risposte autenticate valide sono state persistite; la latenza HTTP mediana osservata è circa1,26s contro circa26s di Qwen9B sul Mac. Misure operative su richieste differenti, escludono pacing/quote e non dimostrano superiorità scientifica. Lo stato vivo e la copertura esatta sono nell'app.
- La lunga run locale1200policy e quella Gemini sono riprese dalle policy salvate dopo l'aggiornamento API. Nessuna policy di provider diversi viene mescolata.
- Cloudflare: integrazione HTTP e sicurezza verificate con trasporto controllato; token/AccountID non ancora configurati al momento della consegna. Inferenza reale e latenza da provare nel pannello.10.000Neurons/giorno rinnovabili sul piano Workers Free; nessuna promessa illimitata o permanente. Qwen3-30B escluso perché in dismissione20/11; modelli finali Gemma4-26B-A4B eGLM4.7Flash.
- Benchmark96casi/candidato, rubrica umana cieca, ablation reale, studi di convergenza del panel e validazione con persone/label per età restano da eseguire. Il precedente avvio del benchmark completo era stato rifiutato dall'utente; non è stato aggirato. Il codice del runner è disponibile e riprendibile.
- Browser integrato127.0.0.1:3000:autorizzazione rifiutata in questa sessione, nessun nuovo accesso tentato. Un test mobile precedente era passato; l'UI cloud e la correzione desktop sono compilate ma non riverificate visivamente. Il video demo non è stato registrato; la scaletta è nel README.

## Copertura del piano

T01–T08:dati/baseline/API/età implementati e verificati. T09:runtime e benchmark implementati, qualifica empirica aperta. T10–T16:profili,policy,behavior,brief,report e scenari budget implementati; test automatici e simulazione reale avviata. T17:runner ablation/validationUI implementati, esperimento reale aperto. T18:storico/dettaglio agente implementati, browser non riverificato. T19:journeys/browser parzialmente verificati secondo autorizzazione. T20:security/retention/recovery testati. T21:CI/build/Compose e smoke servizi verificati. T22:README/schema/export completati, video aperto.
