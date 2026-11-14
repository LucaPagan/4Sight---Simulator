# Verifica del nucleo MVP

## Esito dell'analisi

Il percorso operativo esiste: il brief produce profili sintetici, richieste reali al modello selezionato, risposte validate, cache, eventi simulati e rapporto esportabile. Questo non dimostra che i numeri previsti corrispondano ai risultati di una nuova campagna.

**La promessa «prevedere in modo affidabile e certificato CTR, CPM, clic e spesa tramite agenti» non è ancora verificata.** Il prodotto attuale è un laboratorio di scenari e pretest qualitativo, con baseline quantitativa sul kit simulato. Nessuna certificazione indipendente è stata effettuata.

### Perché i KPI compaiono prima del panel

`SimulationService._execute_run` calcola una previsione preliminare e la salva prima delle richieste LLM. Il forecast aggregato usa storico, settore, leva, formato, calendario, budget e disponibilità dello storico dell'annuncio. Non usa direttamente il significato di testo, brand o descrizione prodotto. Il successivo passaggio con `policy_signals` modifica la ripartizione per età riconciliandola allo stesso totale aggregato.

Gli eventi simulati sono quindi condizionati a quel totale: non sono una misura indipendente che conferma il CTR. Le probabilità grezze dei gate hanno coefficienti ipotetici, non una calibrazione su persone osservate. Non è corretto leggerle come un secondo CTR validato.

Le due creatività sono alternative inserite nel brief. Il confronto quantitativo attuale riflette le feature della baseline e la sua incertezza; non dimostra che il modello comprenda quale testo venderà di più. Per due testi con le stesse feature aggregate, non è dimostrata sensibilità semantica dei KPI.

## Modifiche effettuate nel motore

- Il rapporto include `measurement_status`: origine storica dei KPI, nessun effetto degli agenti sui totali, zero osservazioni umane, nessuna certificazione, significato dello stato completo. Sono campi aggiuntivi; il frontend non è stato modificato da questo lavoro.
- Il prezzo mancante è indicato in `input_gaps`, come mancanza del brief. `price_unknown` non è più presentato come scoperta del panel nelle diagnosi aggregate o per età. Le policy originali e le tracce restano disponibili per audit.
- Corretto un errore di isolamento: una nuova creatività con ID uguale a un annuncio storico poteva ereditarne performance e allocazione, e risultare conosciuta. Ora il forecast usa un identificatore interno assente dallo storico e restituisce all'app l'ID originale. Cambiare soltanto l'etichetta della nuova creatività non può cambiarne i KPI.
- Aggiunto un backtest che esclude un intero adset prima di addestrare la baseline, poi valuta il periodo successivo senza lo storico di quell'adset. ID adset e asset e metadati di lancio riproducono lo scenario nuovo, anziché sfruttare la familiarità con gli stessi annunci.
- Aggiunto un caso Meta reale, scaricabile e verificato tramite checksum, con esiti separati dagli input del modello. Valutazioni incomplete non producono un confronto finale. Cache, snapshot e verifica della fonte permettono di riprendere e controllare il test.

Il benchmark pubblico resta separato dalla produzione: il settore charity e l'obiettivo acquisizione lead non sono supportati dal forecast ecommerce. Non sono stati forzati in una categoria skincare, pet o abbigliamento per ottenere numeri apparentemente confrontabili.

## Funzionamento generale, diversità e decisioni degli agenti

Superare un caso storico non basta. Il criterio generale richiesto dall'utente comprende campagne differenti, profili differenti e risposte che dipendano effettivamente dagli input. Sono state aggiunte due verifiche distinte, senza modificare prompt o temperatura per generare varietà artificiale:

1. **Diagnostica su qualunque panel completo.** `behavior.policy_quality`, riportata anche come `report.panel_quality`, conta reazioni normalizzate distinte, frazione della frase più ripetuta, vettori di valutazione distinti e intenzioni dichiarate per creatività. Segnala risposte molto ripetitive e voti uniformi come punti da revisionare, non come prova automatica di errore. Un consenso può essere sensato; frasi diverse possono esprimere lo stesso contenuto. Le soglie sono dichiarate e non certificano realismo umano.
2. **Contrasti controllati sui tre settori MVP.** `scripts/check_consumer_behavior.py` esegue fino a dodici valutazioni reali: skincare, pet e abbigliamento; messaggio originale/informativo contro messaggio vago; profili con forte bisogno/interesse contro scarso bisogno/interesse, mantenendo la stessa età e gli altri tratti principali. Bisogno, affinità e descrizione del contesto variano insieme: non è un esperimento che identifica l'effetto isolato di un singolo tratto. Misura differenze di chiarezza e interesse, senza assegnare CTR alle risposte. Due profili per settore sono controlli funzionali, non un campione rappresentativo. Le risposte sono salvate e riusate per la ripresa.

```sh
.venv/bin/python scripts/check_consumer_behavior.py --provider gemini
```

La verifica offline della run Gemini già conclusa (`fa40f012-0843-45e4-a42f-1c48474fe244`) ha trovato:

| Risposte reali del modello | Creatività A | Creatività B |
|---|---:|---:|
| Policy valide | 120 | 120 |
| Reazioni testuali normalizzate distinte | 107 | 109 |
| Ripetizione massima di una frase | 2,5% | 3,33% |
| Vettori di valutazione distinti | 14 | 13 |
| Intenzione: considerare il clic | 11 | 30 |
| Intenzione: rimandare | 91 | 84 |
| Intenzione: non interessato | 18 | 6 |

Non sono dunque 120 copie della stessa frase, ma queste misure non dimostrano equivalenza con il pensiero umano. Il file di verifica è `artifacts/validation/existing-gemini-policy-quality.json`; non è stato alterato il risultato originale della run.

La lettura del contenuto evidenzia però una concentrazione che la sola diversità lessicale non rivela: 112 reazioni su120 per A e89 su120 per B contengono un riferimento esplicito al prezzo (`prezz*`). Molte frasi diverse esprimono quindi la stessa riserva sul prezzo assente. Per A emergono inoltre diversi codici simili relativi alla scarsità; il conteggio letterale dei codici non equivale a una tassonomia semantica. È un limite reale di utilità del panel, non risolto contando sinonimi o cambiando temperatura. I metadati `input_gaps` distinguono la carenza del brief dalle evidenze qualitative; un pretest su brief completo e una revisione semantica delle motivazioni restano necessari.

### Limite strutturale ancora aperto

`AgentEvaluation.conditional_action` è un'intenzione condizionale generata dal modello. Attualmente **non entra nei gate numerici**: questi usano i voti ordinali e i tratti, poi vengono riconciliati alla baseline. Le tracce ora espongono `stated_action` e `stated_action_used_in_gates=false`, e il rapporto riporta lo stesso limite. Un evento `clicked=true` è un'estrazione del simulatore, non l'azione autonoma dichiarata dal modello e non un clic umano osservato.

Non è stato aggiunto un coefficiente arbitrario all'intenzione per far sembrare i risultati più sensibili. Per interpretare il tasso di intenzione come comportamento occorre una funzione di calibrazione con esiti umani indipendenti; per modificare i KPI aggregati occorre dimostrare un miglioramento su campagne escluse. Omettere questa distinzione renderebbe il prodotto meno affidabile.

Anche la memoria va interpretata correttamente: familiarità, esposizioni e fatica modificano i gate nel tempo. La valutazione LLM è una policy per profilo, creatività e regime di calendario, riusata dalla cache; non è un nuovo pensiero del modello per ogni impression o giorno. Le reazioni sono possibili risposte sintetiche, non testimonianze, pensieri reali o spiegazioni causali certificate di persone.

La logica è quindi verificata su più classi di input per gli aspetti operativi e di sensibilità. La validità comportamentale generale e l'accuratezza su nuove campagne reali restano obiettivi da misurare, non risultati già acquisiti.

I dodici controlli reali su Gemini 3.5 Flash-Lite sono terminati senza errori. Differenza media di chiarezza tra messaggio informativo e vago: +4 su skincare, +3 su pet, +3 su abbigliamento, sulla scala 0–4. Differenza media di interesse tra profili con bisogno alto e basso: +2 in tutti e tre i settori. Nei messaggi informativi il profilo con bisogno alto ha dichiarato `consider_click`, quello con bisogno basso `not_interested`; nei messaggi vaghi entrambi hanno dichiarato `not_interested`. Sono contrasti costruiti per essere netti: verificano la sensibilità agli input, non la capacità di distinguere due annunci commerciali realisticamente simili o di prevederne il rendimento.

## Campagna reale trovata

**Giving What We Can — Effective Giving Guide, Facebook, novembre 2021–gennaio 2022.** Il gruppo di ricerca pubblica contesto, testi e un export con impression, link click e spesa USD. Fonti primarie:

- [Rapporto degli autori e limiti metodologici](https://daaronr.github.io/eamt_data_analysis/chapters/gwwc_gg.html).
- [Export pubblico, revisione fissata](https://github.com/daaronr/eamt_data_analysis/blob/5c97d539590e08cc5d3a8f3e10a270eb7f00e611/gwwc/gg_raw_data_shareable/gg_campaign_by_ad_by_text.csv).

Il file contiene 257 righe e sette testi distinti. Il caso selezionato usa due testi nello stesso annuncio `Animal Welfare (Emotional)` della campagna iniziale, 30 novembre–20 dicembre 2021. L'ordine dei testi è determinato dal loro SHA-256, senza scegliere quelli con CTR migliore. Le celle duplicate ambigue vengono rifiutate. Un conteggio di clic mancante rimane sconosciuto, non diventa automaticamente zero.

Il CSV resta negli artifact locali; non è stato aggiunto al repository. La licenza di redistribuzione non è specificata nella fonte. Il checksum fissato è `9d4df9370cf144fcc4b010b93b60440d712ca9de20969c7ae799fe1a016fa296`.

### Che cosa misura il test

120 profili ipotetici, sei fasce d'età equiponderate, ognuno esposto ai due testi: 240 policy valide richieste. Il modello riceve copy originale e una descrizione del video ricavata dal rapporto degli autori. Il video non viene visionato. Non riceve clic, impression, CTR, spesa, risultati lead o etichette di vincitore.

Endpoint dichiarato prima del test: **interesse medio ordinale, scala 0–4**, ponderato per i pesi del panel. La preferenza risultante viene confrontata con l'ordine dei CTR osservati. La quota di `consider_click` è un'intenzione condizionale espressa dal modello: non una previsione di CTR.

Lo snapshot delle risposte viene salvato e ne viene registrato l'hash prima che lo scorer legga gli esiti. Lo scorer verifica nuovamente il checksum del CSV originale e ricostruisce input e osservazioni: modificare soltanto `observations.json` non può cambiare il risultato attribuito alla fonte. Questo dimostra integrità locale e separazione degli input; non è una firma o una certificazione esterna.

Il rapporto contiene CTR e CPM **osservati** (spesa in USD), differenza fra CTR e intervallo binomiale descrittivo. Non calcola un errore di previsione CTR o CPM degli agenti, perché questi non producono probabilità calibrate o una previsione di asta.

### Limiti che impediscono una certificazione

1. La distribuzione delle creatività era ottimizzata dall'algoritmo Facebook. Gli utenti raggiunti possono differire: la differenza osservata non identifica il solo effetto causale del testo.
2. I tratti e le quote per età dei profili sono ipotesi, non una ricostruzione della vera audience. Aumentare il numero di agenti non produce altrettanti utenti reali indipendenti.
3. La campagna è pubblica e potrebbe essere presente nell'addestramento del modello. Escludere i risultati dal prompt non garantisce che il modello non li abbia mai visti.
4. Un solo confronto non stima l'accuratezza su nuove campagne. Un eventuale accordo è un risultato esplorativo; un disaccordo deve essere conservato.
5. Il video, la distribuzione effettiva per placement, il targeting completo, ripetizioni e frequenza individuale non sono interamente osservati. L'intervallo binomiale è descrittivo, condizionato a ipotesi di indipendenza che non sono verificate.
6. Charity/lead generation, periodo 2021 e audience non specificata non validano il forecast ecommerce europeo del prodotto.

### Risultato effettivo del caso pubblico

Gemini 3.5 Flash-Lite: **240/240 policy valide**, 120 profili su due testi, completate dopo una ripresa da 97 policy già in cache. Nessun cambio di modello o provider. Esiti letti dallo scorer dopo il commitment delle valutazioni.

| Misura | Testo `54f2a2799530` | Testo `63db35b4aa84` |
|---|---:|---:|
| Interesse medio del modello, 0–4 | 2,1667 | 2,1750 |
| Intenzione condizionale `consider_click` | 43,33% | 45,00% |
| Impression osservate | 5.345 | 5.151 |
| Link click osservati | 57 | 41 |
| CTR osservato | 1,0664% | 0,7960% |
| CPM osservato, USD | 33,6213 | 33,5115 |

L'ordine puntuale di interesse del panel è opposto a quello dei CTR osservati (`ranking_agrees=false`). La preferenza del panel è minuscola: differenza 0,0083 sulla scala 0–4. La differenza osservata di CTR è +0,2705 punti percentuali a favore del primo testo, con intervallo binomiale descrittivo 95% da −0,1014 a +0,6463: include zero. Il rapporto conclude `inconclusive_observed_difference`, non dichiara un vincitore o una validazione predittiva. Non è corretto trasformare questo caso né in una dimostrazione di accuratezza né in una stima generalizzata del tasso di errore.

Rapporto ripetibile: `artifacts/validation/public-meta/evaluations/2d3d705f8c7dcd14cf2c4f583711697e74f0da58efe61be9549e15c77b5b3b6e/report.json`. Il secondo testo non viene promosso e il criterio non viene cambiato dopo aver visto i risultati. Il confronto non modifica i parametri del motore di produzione.

## Ripetere il test

Eseguire dalla directory del progetto, con ambiente Python già installato. La chiave rimane nella configurazione privata già presente, non nei comandi né nei report.

```sh
.venv/bin/python -m audience_simulator.cli public-campaign prepare
.venv/bin/python -m audience_simulator.cli public-campaign run 691d70482fe6beb18d999b350bf3d97517cf53446d2ed4f197814a10f80b8c75 --provider gemini --model gemini-3.5-flash-lite
.venv/bin/python -m audience_simulator.cli public-campaign score 2d3d705f8c7dcd14cf2c4f583711697e74f0da58efe61be9549e15c77b5b3b6e
```

`prepare` scarica e prepara soltanto, senza chiamate AI. `run` restituisce `evaluation_id` e stato. Il comando `score` richiede quell'ID: cambiare modello o prompt cambia anche l'ID. Gli ID sopra valgono per il caso e la configurazione indicati. `--max-new 10` limita un avvio a dieci tentativi; rilanciando si riutilizzano le policy già valide. Nessun cambio automatico di provider o passaggio a pagamento. Limiti e disponibilità del piano gratuito rimangono quelli del provider.

I file si trovano sotto `artifacts/validation/public-meta/`: `cases/<case_id>/case.json` contiene gli input, `observations.json` gli esiti, `provenance.json` la fonte e `source.csv` il dato originale. `evaluations/<evaluation_id>/` contiene manifest, avanzamento, snapshot, commitment, stato e rapporto. Se la quota interrompe la prova, ripetere lo stesso `run`; non eseguire `score` su un panel parziale.

Per il test senza storico dell'adset:

```sh
.venv/bin/python -m audience_simulator.cli validate-cold-start
```

L'output è `artifacts/validation/cold-start.json`. La baseline GLM è fissata prima di vedere le etichette escluse; non sceglie il candidato migliore usando quel confronto. La verifica lascia comunque altri adset dello stesso brand nello storico e usa risultati sintetici: non equivale a tenere fuori un'intera azienda reale.

### Risultati quantitativi del controllo sul kit

Esecuzione del 14 novembre 2026, 444 righe del 2–15 novembre, 100 draw, seed 42:

| Controllo | Errore medio CTR ponderato | Interpretazione |
|---|---:|---|
| GLM fisso, annunci/adset già conosciuti | 0,424 punti percentuali | Controllo sullo stesso periodo con identità note |
| GLM fisso, intero adset escluso, scenario nuovo | 0,959 punti percentuali | Dodici fold, nessuno storico dell'adset valutato |

File: `artifacts/validation/fixed-glm-known.json` e `artifacts/validation/cold-start.json`. Il secondo controllo cambia anche lo scenario di lancio e la disponibilità dello storico: non identifica causalmente il contributo di una singola feature. Entrambi riguardano risultati sintetici. Il vecchio numero di validation della baseline selezionata (circa 0,245 punti percentuali) appartiene a un'altra ricetta, scelta su quella stessa validation: non va usato come prova di accuratezza sul nuovo brief o su campagne reali.

## Condizioni per promuovere il prodotto a previsore affidabile

Il criterio di successo va stabilito prima di guardare gli esiti. Servono più campagne indipendenti e confrontabili per settore, paese, obiettivo e periodo, con copy/visual e risultati correttamente definiti; un gruppo di test escluso anche dalla selezione di modelli e prompt; confronto con una baseline semplice; errori e copertura degli intervalli dichiarati per metrica. Le soglie operative vanno scelte in base all'errore tollerabile nelle decisioni di budget.

Il contributo del panel deve battere la stessa baseline su campagne escluse, senza aumentare falsi vincitori o peggiorare la calibrazione. Un'eventuale funzione che traduca le risposte in CTR deve essere appresa su dati di training e verificata su campagne distinte. L'attuale runner ablation non ha ancora dimostrato questo risultato e non promuove automaticamente il modello.

La ripartizione per età richiede dati reali per età; le conversioni e il ROAS richiedono un modello e dati diversi. Fino a queste verifiche, i risultati vanno presentati come ipotesi da testare, non come rendimento futuro garantito.

## Coordinamento con UI/UX

Questo lavoro non modifica frontend, layout o flussi visivi. I campi aggiuntivi del rapporto sono disponibili al successivo caricamento del backend aggiornato. Non è stato riavviato il server durante la lunga run locale dell'utente per non interromperla. Il benchmark usa 120 profili fissi, indipendentemente dal selettore della dimensione del panel aggiunto in parallelo nell'app.

## Verifica finale

92 test Python passati; Ruff e mypy25moduli senza errori; `git diff --check` pulito. Un warning di deprecazione Starlette TestClient già presente. Revisione indipendente conclusa senza problemi alti o medi aperti. Dodici probe reali sui tre settori e replay pubblico240/240 conclusi; nessuna rubrica umana cieca o certificazione indipendente eseguita. Evidenza operativa: `artifacts/validation/mvp-verification.json`.
