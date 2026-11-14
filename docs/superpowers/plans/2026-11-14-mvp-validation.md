# Verifica del motore MVP su dati reali

Obiettivo autorizzato: analizzare e correggere il motore, cercare campagne reali e renderle testabili. UI/UX appartiene all'altro agente. Questa fase non può promettere una certificazione predittiva senza misure esterne.

## Decisioni e confini

- Conservare contratti e flusso dell'app; aggiungere strumenti CLI e metadati del rapporto.
- Riutilizzare profili, client reali, schema delle valutazioni, cache e limitazione delle chiamate. Nessuna dipendenza nuova, nessun fallback a pagamento.
- Fonte Meta: Giving What We Can / Effective Altruism Market Testing, export pubblico nel repository di David Reinstein, commit `5c97d539590e08cc5d3a8f3e10a270eb7f00e611`. Salvare URL, SHA-256 e righe selezionate. Non redistribuire il CSV senza licenza esplicita.
- Selezionare prima degli esiti due testi mediante hash, nello stesso annuncio Animal Welfare della campagna iniziale. Non selezionare i vincitori osservati. Il video è descritto dalla documentazione, non visionato dal modello. Escludere gruppi aggregati ambigui e righe duplicate.
- Il benchmark valuta l'ordinamento qualitativo dei testi da parte del panel contro il CTR osservato. Non trasforma voti ordinali o intenzioni in CTR e non usa la spesa osservata come budget. Nessuna previsione CPM inventata. Non è una validazione dell'intero modello Meta di produzione: obiettivo, settore, audience e periodo differiscono.
- Profili ipotetici, età equiponderate: non campione rappresentativo della campagna. Esiti esclusi dai payload, ma possibile contaminazione nei pesi del modello perché la fonte è pubblica.

## Task eseguibili

1. **Preparazione e isolamento degli esiti** — `backend/audience_simulator/retrospective.py`, `tests/test_retrospective.py`: scrivere test RED su parser, valori nulli/negativi/frazionari, esiti aggiunti agli input, duplicati, selezione invariata al cambiare dei clic. Implementare import da URL fissato e checksum verificato, input e osservazioni in file distinti. Preparazione eseguibile senza chiamate AI.
2. **Panel reale riprendibile** — stesso modulo, `audience.py`, `cli.py`: estrarre il generatore dei 120 profili mantenendo gli output esistenti; costruire payload con vero contesto charity senza forzarlo nelle tre categorie ecommerce. Congelare manifest e valutazioni prima di leggere gli esiti. Riutilizzare cache per input/modello/prompt; salvare avanzamento ad ogni policy, fermarsi su quota o errore senza completamento fittizio. CLI `public-campaign prepare|run|score`. Test RED su ripresa, assenza di esiti nei payload e incompletezza.
3. **Confronto e audit del flusso di produzione** — `reporting.py`, `forecasting.py`, test relativi: rapporto pubblico con CTR/CPM osservati, differenza con intervallo descrittivo, ranking del panel separato, nessuna certificazione o accuratezza aggregata dichiarata. Aggiungere backtest con ID annuncio/adset nuovi, distinto da annunci conosciuti e sempre etichettato come kit simulato. Separare prezzo mancante dalle frizioni attribuite al panel; rendere esplicito che i KPI aggregati non derivano dalle risposte LLM. Verificare con test le identità e il comportamento.
4. **Esecuzione e consegna** — preparare il caso reale, eseguire fino a 240 policy su Gemini gratuito già configurato, registrare confronto o limite effettivo e comandi per riprendere. Eseguire suite Python, lint e typecheck backend. Revisione indipendente secondo Superpowers. Aggiornare `docs/MVP_VALIDATION.md` con esiti, limiti, soglie per promuovere il prodotto e istruzioni ripetibili. Non cambiare frontend né riavviare run dell'utente.

## Criteri di verifica

- Manifest input e risposte verificabili tramite hash prima dello scoring; file incompleti o modificati rifiutati.
- 120 profili distinti e 240 valutazioni valide per il caso a due testi; conteggi di cache e nuove chiamate separati. Quota esaurita produce risultato parziale riprendibile.
- Nessun risultato osservato negli input AI; nessun segnale prezzo mancante presentato come 120 scoperte indipendenti.
- Una corrispondenza di ranking su un solo caso non costituisce accuratezza stimata, lift causale o certificazione. Un insuccesso resta nel rapporto.
- Kit sintetico, campagne pubbliche retrospettive e verifica futura su campagne confrontabili restano evidenze distinte.

## Rischi da esercitare nei test

Esiti nulli non equivalgono automaticamente a zero; celle duplicate non si sommano senza identificazione; mismatch creatività/esiti fallisce; policy incomplete non producono ranking finale; fonte modificata o checksum errato fallisce prima delle chiamate.

Estensione emersa nell'audit: correggere in `SimulationService.predict_brief` il riuso accidentale dello storico quando un ID creatività utente coincide con un ID storico. Test RED riprodotto in `test_new_brief_cannot_borrow_history_by_reusing_an_old_ad_id`: deve restare cold start e produrre gli stessi KPI rinominando soltanto l'ID. Preservare gli ID esterni nei risultati e nelle policy.
