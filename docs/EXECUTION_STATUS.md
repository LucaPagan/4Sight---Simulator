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
- L'utente ha configurato Gemini e avviato una run reale120×2 con Gemini3.5Flash-Lite. La run è **completa240/240**, con120profili,duepredizioni,12righeperetà e240eventi. Verificati totali per età ed export aggregate/age/report con HTTP200; la latenza HTTP mediana osservata è circa1,26s contro circa26s di Qwen9B sul Mac. Misure operative su richieste differenti, escludono pacing/quote e non dimostrano superiorità scientifica. Lo stato vivo e la copertura esatta sono nell'app.
- La lunga run locale1200policy e quella Gemini sono riprese dalle policy salvate dopo l'aggiornamento API. Nessuna policy di provider diversi viene mescolata.
- Cloudflare: integrazione HTTP e sicurezza verificate con trasporto controllato; token/AccountID non ancora configurati al momento della consegna. Inferenza reale e latenza da provare nel pannello.10.000Neurons/giorno rinnovabili sul piano Workers Free; nessuna promessa illimitata o permanente. Qwen3-30B escluso perché in dismissione20/11; modelli finali Gemma4-26B-A4B eGLM4.7Flash.
- Benchmark96casi/candidato, rubrica umana cieca, ablation reale, studi di convergenza del panel e validazione con persone/label per età restano da eseguire. Il precedente avvio del benchmark completo era stato rifiutato dall'utente; non è stato aggirato. Il codice del runner è disponibile e riprendibile.
- Browser integrato127.0.0.1:3000:autorizzazione rifiutata in questa sessione, nessun nuovo accesso tentato. Un test mobile precedente era passato; l'UI cloud e la correzione desktop sono compilate ma non riverificate visivamente. Il video demo non è stato registrato; la scaletta è nel README.

## Copertura del piano

T01–T08:dati/baseline/API/età implementati e verificati. T09:runtime e benchmark implementati, qualifica empirica aperta. T10–T16:profili,policy,behavior,brief,report e scenari budget implementati; test automatici e simulazione reale120×2completa. T17:runner ablation/validationUI implementati, esperimento reale aperto. T18:storico/dettaglio agente implementati, browser non riverificato. T19:journeys/browser parzialmente verificati secondo autorizzazione. T20:security/retention/recovery testati. T21:CI/build/Compose e smoke servizi verificati. T22:README/schema/export completati, video aperto.

## Aggiornamento: audit generale del motore e dati reali

La verifica corrente del backend conta **92 test Python passati**, Ruff e mypy25moduli senza errori; resta il warning TestClient già noto. Revisione indipendente finale senza problemi alti o medi aperti. Nessun frontend modificato o verificato da questo lavoro: l'altro agente sta lavorando su UI/UX e dimensione del panel.

Corretto il riuso accidentale dello storico per collisioni di ID creatività/adset, anche nei dataset importati. Il forecast del nuovo brief e il nuovo backtest usano lo stesso isolamento, conservando gli ID pubblici. Risolte collisioni di metadati asset nel test cold start. Separati prezzo mancante e scoperte qualitative; aggiunte diagnostiche generali della ripetitività e distinzione fra intenzione dichiarata LLM e clic campionato dai gate.

Dodici contrasti reali Gemini sui tre settori mostrano sensibilità agli input: chiarezza informativo-vago +4/+3/+3 e interesse alto-basso bisogno/affinità +2/+2/+2. Non sono una verifica contro persone. Nella precedente run completa120×2, reazioni normalizzate distinte107/109, intenzioni differenti e nessun superamento della soglia euristica di ripetizione. Nessuna varietà artificiale aggiunta ai testi.

Backtest senza storico dell'intero adset:12fold,444righe sintetiche, CTRMAEponderato0,959pp. Controllo GLM fisso con ID conosciuti:0,424pp. Non è una validazione predittiva su campagne reali e non equivale alla vecchia baseline scelta sulla validation. Il caso reale Meta GWWC è ripetibile con esiti esclusi dai prompt, hash dello snapshot e verifica della fonte prima dello scoring.

Dettagli, comandi, limiti e condizioni di promozione: [MVP_VALIDATION.md](MVP_VALIDATION.md). Il completamento delle chiamate non certifica realismo umano, accuratezza dei KPI o validità generale. Il server API non è stato riavviato durante la run locale lunga; le nuove informazioni del report saranno servite dopo il caricamento del backend aggiornato.

Il replay pubblico GWWC è concluso240/240 su Gemini3.5Flash-Lite, con97policy riprese dalla cache e143nuove valide. Ordine puntuale del panel opposto al CTR osservato; preferenza ordinale quasi nulla (2,1667 contro2,1750). CTR osservati1,0664% e0,7960%, differenza0,2705pp con intervallo descrittivo95%[-0,1014;0,6463]. Conclusione: confronto inconclusivo, nessuna evidenza di capacità predittiva generale o certificazione. Nessuna modifica del modello per adeguarlo a questi esiti.
