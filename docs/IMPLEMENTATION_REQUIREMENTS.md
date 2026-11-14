# Prompt master v2.0 — piano implementativo completo di Audience Simulator

> **Istruzione d'uso:** copia il contenuto da **PROMPT DA INVIARE** a **FINE PROMPT** in un'AI di sviluppo (Codex/Claude Code/altro) insieme a `AGENT_SYSTEM_SPEC.md`. Questo prompt chiede un **piano eseguibile e verificabile**, non ancora di scrivere l'intera app.

---

## PROMPT DA INVIARE

Agisci come **Principal Software Architect + ML Engineer + Behavioral Scientist + Product Designer + Tech Lead**. Il tuo compito è produrre un **piano di implementazione completo, concreto, sequenziale e verificabile** di una web application chiamata **Audience Simulator**, dedicata alla previsione di performance pubblicitarie prima del lancio.

### A. Contesto e fonti da leggere prima di pianificare

1. Leggi integralmente l'allegato **`AGENT_SYSTEM_SPEC.md`**, che è il contratto **vincolante** per creazione dinamica degli agenti, gestione del contesto, modellazione comportamentale, simulazione e limiti epistemici.
2. Dataset consegnato (Drive): <https://drive.google.com/drive/folders/1MBv5s345DA9tjy0jwLPTo4sedJO3BMtq>. Se accessibile, ispeziona tutti i CSV e la sottocartella `asset_creativi`, poi costruisci schema, join, qualità e feature dictionary. Se non accessibile **non inventare file o colonne**: utilizza l'inventario qui sotto e indica l'accesso ai file come prerequisito della fase di ingestione.
3. Repository ispirazionale: <https://github.com/msitarzewski/agency-agents>. Adatta solo i pattern utili (ruolo/missione/workflow/output), `design/design-persona-walkthrough.md`, strategist paid social/creative, auditor e research synthesist; **non** presumere che la repo contenga un predittore CTR scientificamente validato.
4. Traccia: costruire un pubblico AI con persone diverse per età, abitudini e bisogni; testare più creatività; identificare il pubblico giusto, motivi di insuccesso, creatività vincente, **CTR per segmento d'età (OBBLIGATORIO anche senza dati demografici osservati)**, **fascia CPM** e motivazioni.
5. Se sono disponibili le skill **Superpowers**, applica il loro metodo per brainstorming guidato, `writing-plans`, scomposizione in task, TDD, debugging sistematico e verifica prima della consegna. Se non sono disponibili, applica rigorosamente gli stessi principi senza dichiarare di aver invocato strumenti non disponibili.

**Inventario verificato dei dataset**:

- `storico_giornaliero.csv`: **1.879 righe**, colonne `data,giorno_settimana,piattaforma,inserzionista_id,vertical,campaign_id,campaign_name,adset_id,ad_id,asset_id,leva,formato,budget_giornaliero_adset,spesa,impression,copertura,frequenza,click,ctr,cpc,cpm`.
- `da_prevedere.csv`: **699 righe**, colonne `data,giorno_settimana,piattaforma,vertical,campaign_id,adset_id,ad_id,asset_id,leva,formato,budget_giornaliero_adset`; target non disponibili.
- `calendario.csv`: **106 giorni**; `periodo`: 17/08–01/11/2026 addestramento (77 giorni), 02/11–15/11 validazione (14), 16/11–30/11 test (15); festività e promo Black Week/Black Friday/Cyber Monday.
- `annunci.csv`: 69 annunci; `adset.csv`: 12 ad set (`pubblico` indicato *da definire*); `campagne.csv`: 3 campagne; `inserzionisti.csv`: 3 brand.
- `asset_creativi/asset_beauty_skincare.csv`, `asset_pet_ecommerce.csv`, `asset_abbigliamento.csv`: **36 asset**, con `headline`, `testo_principale`, `call_to_action`, `descrizione_visual`, `leva`, `formato`, `durata_video_s`, date. Non assumere disponibilità dei file multimediali effettivi.
- `budget_giornaliero.csv`: 1.272 righe, budget **per adset/giorno**; `cpm_storici.csv`: 704 righe, mediana/quartili CPM per piattaforma-paese-mese-obiettivo; `benchmark_mercato_settimanale_2025.csv`: 66 righe di **indici**, non valori assoluti.
- Vertical: `beauty_skincare`, `pet_ecommerce`, `abbigliamento`; storico Meta, obiettivo vendite. Le audience demografiche **non sono osservate**: ciò **NON autorizza a eliminare o rinviare la simulazione per fascia d'età**. Essa è un requisito dell'MVP: produrre CTR e reazioni per età tramite prior scientifici, modelli gerarchici, ipotesi controllate e riconciliazione con l'aggregato, chiarendo che i risultati sono teorici e non misurati.
- I CSV sono dataset forniti per l'esercizio; alcune righe etichettate storiche arrivano al 15/11/2026, mentre oggi è 14/11/2026. Non affermare che siano osservazioni reali già concluse.

### B. Obiettivo funzionale

Un utente deve poter:

1. Importare/validare un dataset, selezionare brand, campagna, adset, periodo e ipotesi di targeting.
2. Sfogliare le creatività esistenti o caricare nuove creatività (in MVP testo + descrizione visuale; immagini/video quando effettivamente presenti).
3. Generare dinamicamente una popolazione sintetica **dipendente dal contesto**; ispezionare segmenti, profili, pesi, memoria e **assunzioni**.
4. Simulare più creatività in scenari equivalenti; osservare impression → attenzione/ignorato → rilevanza → clic/non clic, memoria e variabilità per seed.
5. **SIMULARE OBBLIGATORIAMENTE LE REAZIONI PER ETÀ**: produrre per ogni creatività e fascia adulta (`18-24`, `25-34`, `35-44`, `45-54`, `55-64`, `65+`) CTR, range, impression/click attesi, fattori comportamentali contestuali e livello di evidenza anche senza label demografiche. Prevedere inoltre CTR/CPM per annuncio, giorno e campagna; le stime per età usano modalità `theory_based` quando i dati osservati non esistono. Non limitare il prodotto alla sola baseline aggregata.
6. Confrontare creatività e target; ottenere diagnosi testabili del perché un annuncio possa non funzionare e proposte di variazione.
7. Esportare risultati per tutte le 699 righe di `da_prevedere.csv` mantenendo chiavi e ordine verificabili, con metriche predette, assunzioni, metodologie e qualità.
8. Eseguire backtest temporali e consultare il confronto baseline vs agenti; visualizzare stato del processo, errori e provenance.

### C. Decisioni tecniche predefinite (motiva eventuali alternative)

- **Architettura iniziale:** modular monolith, non microservizi prematuri.
- **Frontend:** Next.js + React + TypeScript, design accessibile, responsive; libreria grafici affidabile.
- **Backend:** Python + FastAPI, Pydantic per contratti, job asincroni con queue/worker (es. Redis + RQ/Celery), endpoint SSE/polling per progressi simulazione.
- **Persistenza:** PostgreSQL (eventuale pgvector solo se davvero utile), object storage per asset, migrazioni Alembic.
- **Dati/ML:** Pandas/Polars, scikit-learn + boosting, statistiche gerarchiche ove giustificate, Monte Carlo e MLflow o sistema minimale di model registry.
- **LLM:** provider astratto/configurabile; batch e cache, structured JSON outputs, limiti costo/token; niente chiamata LLM per ogni impression.
- **Testing/infra:** pytest, Playwright, type checking, lint/format, Docker Compose, CI, env config e secrets management.
- Tutti i numeri e costi non osservabili vanno dichiarati ipotetici; GDPR/security-by-design, nessun dato identificativo necessario per le personas.

### D. Vincoli scientifici e statistici NON negoziabili

- Il **baseline predittivo senza agenti** deve essere implementato prima della simulazione LLM: aggregati con smoothing, modello CTR sulle righe con `click/impression` e `impression` come esposizioni, baseline CPM su storico e benchmark.
- `CTR = click/impression*100` e `CPM = spesa/impression*1000`; nel training evita leakage da feature calcolate dai target quando prevedi i target futuri.
- Se prevedi `click`, devi prevedere coerentemente `impression`/delivery e `CTR`; la spesa per (`data`,`adset_id`) è condivisa da più annunci. Non moltiplicare il budget per il numero di annunci.
- Split temporale esattamente come `calendario.csv`: **train** 17/08–01/11, **validation** 02/11–15/11, **test** 16/11–30/11. Non riportare metriche test se il ground truth del test non è disponibile.
- Le prestazioni per **segmento demografico** non sono verificabili con questi CSV, **ma il motore DEVE produrle e visualizzarle comunque nel MVP**. Utilizza prior esterni, studi scientifici, scenari di sensibilità e un modello gerarchico che riconcilia CTR per età con la baseline aggregata. Etichetta `theory_based`/`hypothesis_only`, vieta claim di accuratezza per età non misurata. Non bloccare mai la funzionalità per assenza di ground truth.
- I modelli CPM usano paese/piattaforma/obiettivo/periodo/benchmark quando compatibili; non confondere quartili storici con prediction intervals calibrati.
- Calibrazione probabilistica e intervalli verificati sulla validation; metriche adeguate a conteggi aggregati (es. deviance/binomial likelihood, CTR weighted MAE, CPM error, ranking, coverage). Baseline, LLM generico e panel agenti devono poter essere confrontati in ablation.
- Memoria/performance del panel testate con multi-seed, same-panel A/B, e distinte dalle descrizioni qualitative. Gli agenti non conoscono i target della riga che devono prevedere.
- Nessuna causalità attribuita a copy/CTA/colore senza esperimento o modello causale appropriato. Se viene proposto un test, esplicitare ipotesi, metrica e design.

### E. Cosa devi produrre — formato del piano, obbligatorio

Genera in **italiano** un piano progettuale Markdown, con sezioni in questo ordine:

**1. Executive brief e decision log.** Scopo, utenti, 3 vertical, MVP/non-MVP, limitazioni con dati disponibili; assunzioni da verificare e motivazione dello stack.

**2. Dataset audit & feature plan.** Tabella con ogni file, colonne, chiavi, cardinalità, join, controlli, train/validation/test, mapping delle feature in-time; piano di ingestione anche per nuovi CSV; rischi di leakage, date lancio/fine, `cpc` mancante con zero clic, budget condiviso, benchmark relativi, country assumption.

**3. User journeys e UX blueprint.** Sitemap e pagine: onboarding dataset; libreria creatività; creazione scenari/pubblico; simulazione; confronto; dettagli segmento/agente; diagnosi; storico run e validation dashboard. Per ogni pagina: componenti, stato vuoto/errore/loading, KPI e interazioni.

**4. Architettura componenti e data flow.** Diagramma Mermaid, moduli, responsabilità, interfacce, gestione job asincroni e costi LLM, sicurezza, log/versioning. Specifica perché modulare-monolitico ora e quali interfacce permettono la scalabilità.

**5. Modello dati.** ERD concettuale e tabelle concrete per `advertisers,campaigns,adsets,ads,assets,daily_observations,budgets,calendar,market_benchmarks,populations,consumer_profiles,consumer_states,exposure_events,simulation_runs,model_versions,predictions,prediction_explanations,validation_runs,assumptions`; campi/PK/FK/indici/vincoli; tipizzazione `evidence_level`, `source_type`, `seed` e provenance; politiche di retention.

**6. Contratti e API.** Endpoint REST con payload esemplificativi e validazioni (`/datasets/import`, `/campaigns`, `/assets`, `/populations/generate`, `/scenarios`, `/simulations`, `/simulations/{id}/status`, `/predictions`, `/comparisons`, `/backtests`, `/exports`); JSON schemas di agenti, contesto, evento di esposizione, prediction e report; transizioni di job.

**7. Design degli agenti dinamici.** Riferimento obbligatorio a `AGENT_SYSTEM_SPEC.md` **§§11–14**; lifecycle, prompt template tipizzati per ogni ruolo, scenario parser LLM→Pydantic, input/output JSON, memoria e transizioni controllate; generazione e reazioni **age-aware fin dal MVP**, anche senza dati per età; contesto ricreato per impression (vertical, data, adset, leva, formato, brand, placement, task, eventi, memoria); possibilità di ignorare; peso del campione; cold-start; esempi per skincare/pet/abbigliamento e **due fasce d'età per ciascuno**; distinzione osservato/derivato/assunto; seed e scenario sensitivity.

**8. Modeling & forecasting.** Baseline CTR, CPM e delivery; feature engineering, calibrazione, Monte Carlo e agent augmentation; **algoritmo implementabile per CTR per età**: campionamento quote impression `q_s`, prior sugli effetti `delta_s` dipendenti da settore/contenuto/contesto, calcolo `p_s=sigmoid(b+delta_s)` e soluzione numerica di `b` tale che `Σ(q_s·p_s)=p_base`, più incertezza di `q_s`, `delta_s` e baseline; generare ranking creatività e intervalli con seed comuni, gestire ads/asset nuovi. Stima CPM per età solo come scenario d'asta etichettato o `null`; budget di adset condiviso e riconciliazione. Fornisci pseudocodice di scoring e aggregazione, anche per segmenti senza label.

**9. Validation & test strategy.** Split temporali, test unitari, integrazione, e2e, fixture CSV, test di budget, formati, leakage, riproducibilità, ablation e score; **test obbligatori** di `Σq_s=1`, `Σq_s·CTR_s=CTR_aggregato`, coerenza impression/click/spesa per segmenti, sensitività a prior alternativi, variazione del contesto, impossibilità di dichiarare calibrated il CTR per età senza ground truth e mantenimento di eterogeneità intra-età; esempi concreti **Given/When/Then** e criteri di accettazione relativi a baseline.

**10. Piano di implementazione in vertical slices.** Fasi ordinate con prerequisiti; scomponi in task eseguibili da 0,5–2 giornate, ciascuno con ID, dipendenze, cartelle/file toccati, comandi di test, Definition of Done, difficoltà e rischio. Ordinamento minimo: scaffolding/ETL → baseline/model registry → API previsione → **generatore age-aware e riconciliazione per età** → dashboard segmenti → behavioral engine → ranking/report → validation/operatività. **La prima demo che confronta due età è un milestone P0, non una futura estensione.** Ogni slice deve produrre software verificabile end-to-end, non solo documentazione.

**11. Backlog e milestone.** Priorizzazione P0/P1/P2, MVP demo sui 3 vertical **con CTR per età e confronti A/B tra fasce**, stime indicative come intervalli con assunzioni, percorso critico, decisioni architetturali da rimandare.

**12. Rischi e mitigazioni.** Almeno: mancanza dati demografici, future labels assenti, falsi livelli di precisione, LLM over-reasoning, bias, data drift, leakage, budget ripetuti, eventi Black Friday, gestione nuovi asset, costi API, performance, privacy, contenuti ingannevoli.

**13. Primi 10 ticket pronti per il coding.** Ciascuno con titolo, descrizione, input, file attesi, criteri verificabili e test. Il primo ticket deve funzionare anche offline con i CSV locali. **Almeno un ticket P0 deve implementare e testare la stima per età con prior senza ground truth e riconciliazione matematica.**

**14. Checklist finale di qualità e “stop/go”.** Controlli per decidere se una previsione è presentabile, quali parti sono validate e quali soltanto simulate. **Stop/Go doppio**: qualità delle previsioni aggregate verificata con holdout; qualità *teorica* della simulazione per età verificata tramite coerenza, robustezza ai prior e trasparenza epistemica. Non bloccare la modalità age-aware per impossibilità di misurare l'accuratezza per età sui CSV attuali.

### F. Standard di esecuzione del piano

- Non cominciare a implementare tutta l'applicazione ora: produci **prima il piano completo** e i ticket.
- Esprimi ciò che non si può sapere dai dati, **ma progetta e includi comunque la stima per età** mediante prior scientifici e simulazioni probabilistiche: non inventare etichette osservate, crea ipotesi ragionevoli e falsificabili. Non presentare la mancanza di label come impedimento funzionale.
- Specifica decisioni invece di elencare decine di alternative non valutate: scrivi una scelta di default e massimo una ragionevole alternativa, con trade-off.
- Piano adatto a esecuzione da agente di coding: **nomi moduli, contratti, test, ordine e criteri di completamento**. Dove manca un requisito non bloccante, fai un'assunzione tracciata e procedi.
- Inserisci esempi legati ai dati effettivi (`NDL`, `CDF`, `FGR`, `NDL-AD03`, `scarcity`, `urgency`, `black_friday`); non inserire previsioni numeriche fittizie come risultati misurati.
- Esplicita un *minimal viable prediction*: il sistema deve produrre una previsione baseline sulle 699 righe **prima** di aggiungere componenti LLM complessi.
- Chiudi con il **prossimo singolo passo eseguibile** per avviare lo sviluppo, indicando il relativo test di completamento.

### G. Obbligo progettuale aggiuntivo: innovazione scientifica e age-aware simulation

**Devi trovare una soluzione tecnica anche per caratteristiche che non esistono nei dataset.** Il progetto vuole realizzare un simulatore sperimentale che, sulla base di teorie del comportamento, evidenze esterne e modelli probabilistici, produca risultati per **ogni fascia d'età**, non solo riproduca dati storici. Non ridurlo a un tradizionale CTR forecaster. Progetta esplicitamente l'**Audience Behavior Lab** con simulazione controfattuale e contestuale. Includi obbligatoriamente:

1. **Behavioral Evidence Registry**: struttura delle evidenze scientifiche con fonte, popolazione, outcome, fattore del comportamento, prior utilizzato, trasferibilità al contesto italiano/Meta, versione e livello di qualità. L'LLM può suggerire collegamenti, non inventare coefficienti empirici.
2. **Evidence-informed age priors**: ricerca e integrazione di basi ISTAT 2025, Eurostat 2025, Pew 2026 (non direttamente applicabile all'Italia), studi su attenzione visiva, credibilità e advertising persuasion knowledge. Specifica come tradurre la fonte in *distribuzioni* di esposizione, abitudini o frizione, e perché **non è lecito tradurre un tasso di shopping online in CTR**. Se la fonte non ha effetto quantitativo direttamente trasferibile, usa prior deboli e scenario sensitivity.
3. **Modello gerarchico age-aware**: struttura completa di `q_s` (share di impression), `delta_s` (effect prior per età), interazioni età×vertical×message×placement×calendar×memory, shrinkage e calibrazione al CTR baseline; per la stima `p_s=sigmoid(b+delta_s)`, risolvi `b` tale che `Σ q_s p_s=p_base`. Descrivi edge-case con `p_base∈{0,1}` e segmenti con `q_s=0`.
4. **UI age simulator obbligatoria**: fasce `18-24`, `25-34`, `35-44`, `45-54`, `55-64`, `65+`; CTR e intervalli per fascia, distribuzione quote impression, spiegazioni contestuali, pannello di confronto A/B a parità di audience, slider della forza dei prior e tre scenari (`conservative`,`central`,`exploratory`), badge/testo `theory_based` (non accuratezza misurata). Permetti di cambiare mercato, categoria, contesto e visualizzare come cambiano le stime.
5. **Meccanismi umani senza stereotipi**: agenti non sempre attenti, spesso indifferenti, possono ignorare; età non determina un comportamento unico, consentire un high-CTR 55+ e low-CTR 18-24; stress test della diversità intra-gruppo, memoria ed esposizioni multiple e stagionalità.
6. **Integrazione dataset con aggregati**: esegui prima baseline CTR/CPM/delivery sugli 1.879 record e poi usa tali previsioni come *ancoraggio* delle simulazioni demografiche; prevedi 699 righe future, con vista per età aggiuntiva generata dalla decomposizione, senza violare budget condiviso né inventare righe osservate.
7. **Validazioni separabili**: backtest quantitativo dei dati aggregati, falsificabilità di scenari per età e futura validazione con dati stratificati; mostra cosa è già misurato, cosa è informato dalla letteratura e cosa è soltanto ipotetico. Disegna un percorso di raccolta dati futuri età-specifici (panel volontari, test controllati conformi alle policy), senza attendere questi dati per completare il MVP.
8. **Piano di ricerca e innovazione**: proponi 2–3 architetture sperimentali per la parte age-aware (es. mixture-of-personas gerarchico; behavioral state machine con context sampler; rete bayesiana con prior), scegli la migliore per MVP con trade-off e definisci quali esperimenti potrebbero falsificarla. Devi formulare scelte e ticket, non fermarti a elencare librerie.

Fonti iniziali da esaminare: <https://www.istat.it/comunicato-stampa/cittadini-e-ict-anno-2025/>; <https://ec.europa.eu/eurostat/web/interactive-publications/digitalisation-2026>; <https://www.pewresearch.org/chart/social-media-use-by-age-2/>; <https://academic.oup.com/innovateage/article/7/5/igad051/7192745>; <https://www.tandfonline.com/doi/full/10.1080/02650487.2024.2370678>; <https://doi.org/10.1086/209380>. Distingui popolazione, misura, pubblicazione e trasferibilità.

**Definition of Done minima**: dato `NDL-AD03` e uno scenario IT skincare con fasce d'età 18+, il sistema restituisce stime di CTR per età **non necessariamente identiche**, con intervalli, pesi, contesti, seed, versione del prior, spiegazioni e avvertenze; la somma ponderata combacia con il CTR totale e i budget tornano; un secondo scenario `CDF` produce agenti/contesti differenti; l'interfaccia permette di confrontare creatività e fasce senza affermare precisione età-specifica non verificata. Se l'app non lo fa, **il lavoro non è completo**.

## FINE PROMPT
