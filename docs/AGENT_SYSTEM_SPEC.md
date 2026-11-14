# Audience Simulator — Specifica operativa degli agenti (v2.0 — simulazione demografica evidence-informed)

> **Uso:** consegnare questo file all'AI incaricata di progettare/implementare l'applicazione. È un *contratto architetturale*, non un prompt che possa da solo rendere scientificamente accurate le previsioni.
>
> **Obiettivo:** generare dinamicamente un pubblico sintetico contestualizzato per campagne Meta, confrontare creatività e produrre CTR/CPM con intervalli, ranking e diagnosi, distinguendo sempre **dato osservato**, **stima calibrata** e **ipotesi sintetica**.

## 1. Regole non negoziabili

1. **Context-first:** ogni agente riceve soltanto il contesto pertinente: campagna, mercato, ad set, creatività, ambiente di esposizione, stato individuale e memoria. Ricalcolare il contesto a ogni nuova simulazione/esposizione.
2. **No forced attention:** un'impression non implica che l'annuncio sia stato notato o letto. Un agente può ignorarlo senza motivazione verbale.
3. **No LLM-as-calculator:** l'LLM estrae attributi, suggerisce ipotesi e verbalizza frizioni; probabilità, campionamenti e metriche derivano da modelli/statistica e regole esplicite. Mai estrarre un CTR affidabile dalla sola opinione di una persona AI.
4. **Dati, ricerca e ipotesi esplicite:** le distribuzioni degli agenti dipendono da dati osservati autorizzati > dati statistici esterni comparabili > input utente > prior scientifici > ipotesi documentate. **La mancanza di etichette demografiche NON blocca la simulazione per età**: genera ipotesi probabilistiche con tracciabilità, sensitivity analysis e intervalli, senza spacciarle per osservazioni.
5. **Età e diversità obbligatorie:** il sistema DEVE generare, differenziare e confrontare agenti per fasce d'età anche in cold-start. I risultati per età sono sempre prodotti ma etichettati `theory_based`/`hypothesis_only` finché non sono validati su dati segmentati. Ogni fascia contiene diversità interna, non stereotipi.
6. **Peso del campione:** ogni agente rappresenta un peso di popolazione; segmentazione e correlazioni devono essere esplicite. Età e interessi non implicano comportamenti deterministici.
7. **CTR e CPM separati:** CTR = click / impression × 100; CPM = spesa / impression × 1.000. Il CPM richiede modello di asta/mercato distinto; non è una semplice media delle preferenze degli agenti.
8. **Confronti equi:** A/B confrontati nello stesso scenario con distribuzione agenti, seed, calendario e budget comparabili; controllare le variazioni casuali (common random numbers dove utile).
9. **Incertezza e verificabilità:** ogni previsione espone intervallo, calibrazione, modello/versione, dataset/training cutoff e livello di evidenza. In assenza di dati sufficienti: `unvalidated`, non precisione inventata.
10. **Privacy e fair use:** agenti sintetici, dati minimizzati, nessuna identificazione di persone; evitare discriminazione o targeting basato su categorie sensibili; rispettare GDPR e policy della piattaforma.
11. **Riproducibilità:** `run_id`, `seed`, versioni prompt/modelli/dati, feature snapshot e log degli input/output strutturati.

## 2. Base dati obbligatoria (Drive del progetto)

Cartella: <https://drive.google.com/drive/folders/1MBv5s345DA9tjy0jwLPTo4sedJO3BMtq>.

| File | Evidenza e utilizzo |
|---|---|
| `storico_giornaliero.csv` | **1.879 righe**, 2026-08-17..2026-11-15; `data,piattaforma,vertical,campaign_id,adset_id,ad_id,asset_id,leva,formato,budget_giornaliero_adset,spesa,impression,copertura,frequenza,click,ctr,cpc,cpm` e altri campi. Target storici per CTR, CPM e delivery. |
| `da_prevedere.csv` | **699 righe**, 2026-11-16..2026-11-30; stessi identificativi di contesto e budget, **senza** spesa/impression/click/CTR/CPM. Output primario da prevedere. |
| `calendario.csv` | 106 giorni con `evento`, `weekend`, `periodo`: **addestramento 77 giorni (17/08–01/11), validazione 14 (02/11–15/11), test 15 (16/11–30/11)**. Seguire la partizione dichiarata, senza mescolare label di periodi futuri. |
| `annunci.csv` | 69 annunci; join `ad_id → adset_id, campaign_id, asset_id`, date lancio/fine. |
| `asset_creativi/*.csv` | 36 asset totali (12 per settore), campi `asset_id,vertical,leva,formato,durata_video_s,headline,testo_principale,call_to_action,descrizione_visual,data_lancio,data_fine`. Sono **descrizioni testuali** dei visual, non necessariamente pixel/video originali. |
| `adset.csv` | 12 ad set: ottimizzazione, strategia di offerta, budget iniziale; `pubblico = da definire (lo proponete voi)`; **non contiene audience demografiche reali**. |
| `campagne.csv`, `inserzionisti.csv` | 3 campagne/3 inserzionisti nei vertical `beauty_skincare`, `pet_ecommerce`, `abbigliamento`; piattaforma storica `meta`, obiettivo `vendite`. |
| `budget_giornaliero.csv` | 1.272 righe; budget per (`data`, `adset_id`), non per singolo annuncio. |
| `cpm_storici.csv` | 704 righe di benchmark `piattaforma,paese,mese,obiettivo,cpm_mediano,cpm_q1,cpm_q3,n_campagne`: prior per CPM, filtrando contesto compatibile. I quartili NON sono intervalli predittivi già calibrati. |
| `benchmark_mercato_settimanale_2025.csv` | 66 indici settimanali di mercato, per settore/piattaforma/paese; indici relativi, NON CTR/CPM assoluti. |

**Unione dei dati:** `campaign_id`, `adset_id`, `ad_id`, `asset_id`; tempo giornaliero `data`; asset per `asset_id`, budget per (`data`,`adset_id`), calendario per `data`, benchmark con allineamento di settore/piattaforma/paese/periodo. Validare cardinalità e disponibilità temporale delle feature. Nella cartella non compaiono user log individuali, informazioni osservate su sesso/età/interessi o clic attribuiti a segmenti; NON dedurli dai totali aggregati. `paese=IT` è un'ipotesi iniziale da confermare, non un campo delle righe di storico.

**Attenzione ai budget:** `budget_giornaliero_adset` ricorre su più annunci dello stesso ad set; non sommarlo per riga come se fosse budget aggiuntivo. Il modello di delivery deve ripartire una sola spesa condivisa tra gli annunci (vincoli di budget).

**Attenzione temporale:** parte dei file è etichettata come “storico” fino al 15 novembre 2026, data successiva al giorno di preparazione (14 novembre 2026). Trattare i CSV come **dataset di esercizio fornito**, senza attribuirgli automaticamente origine da campagne reali già concluse. Il test 16–30 novembre ha target sconosciuti.

## 3. Agenti e servizi: responsabilità separate

Gli **agenti operativi** sono moduli orchestrati; soltanto gli **agenti consumatori sintetici** rappresentano membri del pubblico.

| Modulo | Responsabilità | Output | Tecnologia preferita |
|---|---|---|---|
| `CreativeAnalyzer` | Estrarre hook, leva, prova sociale, valore, prezzo se disponibile, CTA, complessità, formato, segnali di credibilità da testo/descrizione visuale. | `CreativeFeatures` con provenance/unknown. | LLM + regole, output JSON validato |
| `CampaignContextBuilder` | Unire CSV, calendario, mercato, obiettivo, budget, storico disponibile e vincoli. | `CampaignContext` versionato. | ETL deterministico |
| `AudienceBuilder` | **Generare obbligatoriamente segmenti per età anche senza label**, definendo margini di mercato, prior documentati, interazioni con settore/contesto e pesi; generare popolazione sintetica coerente. | `AgentPopulation` + `assumptions`. | Campionamento statistico + opzionale LLM |
| `ConsumerAgent` | Custodire attributi e stato dinamico; restituire reazioni *campionate*, non “verità umana”. | `ExposureResponse`. | State machine + scoring calibrato; LLM solo per campioni esplicativi |
| `BehaviorEngine` | Simulare attenzione → rilevanza → frizione → clic/non-clic → memoria, sotto contesto di delivery. | Eventi e probabilità. | Modelli probabilistici riproducibili |
| `CTRForecaster` | Calibrare e confrontare modelli storici; aggregare per creatività, giorno e segmento. | `ctr_pred`, intervalli, ranking. | Baseline GLM / boosting / modello gerarchico |
| `CPMDeliveryForecaster` | Prevedere CPM e delivery/spesa/impression con stagione, obiettivo, budget e benchmark. | `cpm_pred`, range, `impressions_pred`. | Modello statistico distinto |
| `InsightAnalyst` | Descrivere criticità e interventi possibili, collegandoli alle evidenze. | Report con `evidence_level`. | LLM + feature attribution + test controllati |
| `PredictionAuditor` | Bloccare leakage, incoerenze, fake precision, target assenti e previsioni non calibrate. | `quality_flags`, report di affidabilità. | Test/validator deterministici |

**Riutilizzo mirato da** <https://github.com/msitarzewski/agency-agents>: la struttura ruolo/missione/workflow/output; `design/design-persona-walkthrough.md` per friction e distinzione voce utente/analista; `paid-media/paid-media-creative-strategist.md`, `paid-media/paid-media-paid-social-strategist.md`, `paid-media/paid-media-auditor.md`, `research/research-synthesist.md` per analisi creativa, contesto e audit. Questi file **non sostituiscono** calibrazione statistica o validazione comportamentale. Verificare licenze/commit prima del riuso.

## 4. Contratti di contesto (immutabili per singola esposizione)

Separare **dati osservati**, **ipotesi** e **stato individuale**. Schema logico minimo:

```json
{
  "run_context": {
    "run_id": "uuid", "seed": 42, "as_of_date": "2026-11-15",
    "dataset_version": "hash", "model_version": "semver", "scenario_id": "id"
  },
  "campaign_context": {
    "campaign_id": "NDL-C1", "adset_id": "NDL-AS1", "ad_id": "NDL-AD03",
    "asset_id": "NDL-S3", "vertical": "beauty_skincare", "platform": "meta",
    "objective": "vendite", "country": "IT", "country_source": "assumption",
    "date": "2026-11-20", "calendar_event": "Inizio Black Week (venerdi)",
    "budget_eur_adset_day": 150, "bid_strategy": "costo più basso (senza limite)"
  },
  "creative_context": {
    "format": "carosello", "lever": "scarcity", "headline": "...",
    "primary_text": "...", "cta": "Scopri di più", "visual_description": "...",
    "actual_media_available": false, "feature_provenance": "asset_csv"
  },
  "consumer_profile": {
    "agent_id": "synthetic-001", "population_weight": 0.0005,
    "segment_id": "hypothetical-segment-A", "segment_evidence": "hypothesis",
    "age_band": "25-34", "budget_sensitivity": 0.7,
    "category_affinity": 0.6, "brand_familiarity": 0.1,
    "purchase_need": 0.4, "prior_exposures": 2
  },
  "exposure_context": {
    "placement": "instagram_feed", "placement_source": "scenario_assumption",
    "device": "mobile", "task": "casual_scrolling",
    "attention_availability": 0.25, "session_competing_content": "unknown"
  }
}
```

I valori dei profili/contesti non presenti nei CSV sono **esempi sintetici**, mai fatti osservati. Non attribuire implicitamente placement Instagram, prezzi, dati demografici o interessi agli annunci se mancanti. `ConsumerProfile` = tratti persistenti; `ConsumerState` = bisogno/budget/familiarità/fatica/memoria mutevoli; `ExposureContext` = condizioni di una singola impression (anche quando cambiano tra due annunci).

## 5. Generazione dinamica del pubblico

1. Risolvere `campaign_id` → inserzionista, settore, ad set, asset, periodo, budget, obiettivo e contesto stagionale.
2. Definire la popolazione obiettivo e un **manifest di ipotesi** (quale mercato/età/abitudine/affinità è noto, ipotizzato, sconosciuto). Non interpretare `pubblico="da definire"` come target noto.
3. Creare distribuzioni congiunte **obbligatorie** per età e contesto: esigenze di categoria, vincoli economici, propensione esplorativa, familiarità, probabilità di acquisto, preferenze di comunicazione; età/abitudini anche tramite prior esterni o ipotesi esplicitate. Segmenti condizionati al vertical (skincare: problemi e routine; pet: tipo di animale, necessità; abbigliamento: stile, stagione e taglia), mai fissati una volta per tutte.
4. Generare campione stratificato/ponderato; evitare duplicati e stereotipi; mantenere varianza intra-segmento, `population_weight`, `assumption_id`, `seed`, `profile_version`.
5. Istanziare la memoria iniziale *solo* da scenari/prior. Non dedurre cronologia di un individuo dal dato aggregato di `frequenza`.
6. Ricreare l'`ExposureContext` per ogni (`data`,`ad_id`,`agent_id`,`replicate`): calendario, visibilità stimata, task, device, placement, stanchezza e storia dell'agente.
7. Confrontare creatività sul medesimo panel *ponderato* e contesti equivalenti, poi ripetere su più seed/scenari.
8. Se dati futuri contengono elementi non visti in training (nuovi `ad_id`/asset), usare attributi creativi e prior gerarchici; segnalare maggiore incertezza.

**Agent lifecycle:** `created → sampled → exposed? → ignored|noticed → interpreted? → click|no_click → memory_updated`; i passaggi `?` non sono obbligatori. Lo stato è serializzato e versionato.

## 6. Modello comportamentale e output

Per ogni impression campionare, in modo condizionato al contesto:

```
P(click) = P(notice) × P(relevant | notice) × P(click | notice, relevant)
```

È una **fattorizzazione progettuale semplificata**: i parametri e le dipendenze vanno appresi/testati, non impostati come costanti psicologiche. Permettere percorsi di clic impulsivi e stadi saltati se i dati lo giustificano. Non richiedere un ragionamento LLM per ogni impression.

- `AttentionGate`: probabilità di ignorare; niente lettura obbligata del testo.
- `MeaningGate`: possibilità di elaborazione parziale; familiarità, visual, copy, contesto e chiarezza.
- `MotivationFrictionGate`: bisogno, vincolo di budget, credibilità/scarsità veritiera, valore, urgenza, fiducia, alternativa già posseduta.
- `ActionGate`: clic/non clic come esito stocastico. Un interesse alto **non** implica clic.
- `MemoryUpdate`: familiarità, impression recenti, possibili effetti di ripetizione/ad fatigue, senza soglie universali rigide.

Event schema minimo:

```json
{
  "run_id": "uuid", "agent_id": "synthetic-001", "ad_id": "NDL-AD03",
  "date": "2026-11-20", "exposure_id": "uuid", "replicate": 1,
  "attention_probability": 0.23, "click_probability": 0.014,
  "noticed": false, "clicked": false,
  "explanation": null,
  "explanation_evidence": "not_available_for_ignored_exposure",
  "weight": 0.0005, "source_type": "simulation",
  "model_version": "v1", "uncertainty_flag": "uncalibrated_segment"
}
```

Il sistema può generare **ipotesi qualitative** per un campione delle esposizioni elaborate, non “catene di pensiero” fittizie presentate come cause vere. Tenere due voci separate: **consumatore** (eventuale reazione colloquiale) e **analista** (diagnosi ancorata a caratteristiche/verifiche). Nessun monologo quando l'esposizione è ignorata.

## 7. Modelli quantitativi, ranking e reporting

- **Baseline obbligatoria senza agenti:** CTR aggregato con smoothing e trend di settore/adset/annuncio; poi GLM/binomiale, gradient boosting o gerarchico con feature pre-impression; confronto con panel AI. Le righe storiche sono aggregati di `click` su `impression`: usare loss binomiale/ponderazioni corrette, non etichettarle come singoli click individuali.
- **CTR:** `100 * Σ(click_previsti) / Σ(impression_previste)`; metriche per `ad_id`, `data`, `campaign`, `adset`, vertical e **fascia d'età obbligatoria**. Anche senza etichette per segmento, `segment_ctr` **DEVE** essere calcolato da scenari evidence-informed, con prior gerarchici e vincoli di riconciliazione all'aggregato; etichetta *theory_based/unvalidated*, nessuna falsa precisione.
- **CPM:** modello separato condizionato a piattaforma, mercato, mese, obiettivo, stagionalità, adset/budget, benchmark e delivery. `cpm_q1/q3` dei dati di benchmark sono quartili storici, non intervalli al 90%. Per una simulazione Monte Carlo generare scenari congiunti CPM/spesa/impression/CTR.
- **Delivery:** prevedere spesa effettiva (≤ budget adset), CPM, impression (`spesa/CPM*1000`) e clic coerenti. Vincolo: totale spesa degli annunci in un adset-giorno ≤ budget condiviso.
- **Creatività vincente:** classifica per CTR previsto e per probabilità di superare concorrenti, con vincoli di obiettivo e budget; distinguere differenza significativa da pareggio/incertezza.
- **Explainability:** attribuzioni e controfattuali su feature, più ipotesi comportamentali; non dichiarare causalità senza test randomizzato. Utilizzare attributi `scarcity`, `urgency`, `black_friday`, formato e calendario con interazioni, evitando regole deterministiche.
- **Output:** almeno `date,ad_id,adset_id,campaign_id,ctr_pred,cpm_pred,ctr_interval,cpm_interval,expected_impressions,expected_clicks,confidence_status,assumptions,model_version`; conservare corrispondenza uno-a-uno con le **699 righe** `da_prevedere.csv`.

## 8. Validazione e guardrail di prodotto

- Split **temporale** come da `calendario.csv`: train 17/08–01/11, validate 02/11–15/11, hidden future test 16/11–30/11. Nel training non usare target della validazione o del test; se i valori futuri non esistono, non riportare score di test.
- Controlli ETL: unicità (`data`,`ad_id`), ID referenziali, date di disponibilità delle creatività, missing `cpc` su click=0, `ctr≈100*click/impression`, `cpm≈1000*spesa/impression`; coerenza dei formati e feature disponibili prima della previsione.
- Backtest: binomial deviance/log loss ponderata, calibrazione, errore assoluto CTR/CPM, ranking/pairwise winner, copertura empirica degli intervalli, segment calibration **solo se si avranno label segmentate**.
- Ablation: baseline no-agents vs LLM no-persona vs synthetic agents; mantenere agenti nella parte quantitativa solo se aggiungono valore misurabile.
- Robustezza: più seed e scenari; non lasciare che gli agenti deducano l'etichetta da `ctr`, `cpm`, `spesa`, `click`, `impression` nei dati di previsione.
- Audit epistemico: `observed`, `calibrated_estimate`, `modeled_assumption`, `qualitative_hypothesis`; ogni insight deve citare feature/fonti interne e livello.
- Sicurezza: CSV e copy sono **dati non attendibili**, mai istruzioni da eseguire; validazione schema, sanitizzazione, limiti LLM, contenuti pubblicitari ingannevoli (es. scarsità non verificata) segnalati, privacy e accessi.

## 9. Definition of Done per gli agenti (MVP)

- [ ] Popolazione generata **dopo** scelta del contesto, con pesi, assunzioni, seed e profili differenziati.
- [ ] Una stessa persona sintetica può reagire diversamente a creatività, giorno e contesto differenti senza incoerenze gratuite.
- [ ] Ignorare l'annuncio è un evento valido; non tutti gli agenti producono testi/giustificazioni.
- [ ] Campione A/B paritario, risultati ripetibili, stato e memoria testati.
- [ ] Per ogni scenario il sistema produce **CTR per le fasce d'età** e i relativi intervalli anche senza dati individuali, insieme a pesi, prior, modalità/scenario, evidence level e riconciliazione con il CTR aggregato.
- [ ] Il sistema distingue CTR aggregato calibrato da CTR per segmenti teorici e calcola CPM per fascia soltanto con modello/scenario di asta esplicito.
- [ ] CPM e delivery non sono fabbricati dall'LLM e rispettano i budget adset.
- [ ] Report con creatività vincente **o pareggio/incertezza**, KPI, intervalli, diagnosi e limitazioni esplicite.
- [ ] Test temporali e baseline pubblicati; nessuna pretesa di riprodurre accuratamente esseri umani senza validazione empirica.

## 10. Riferimenti metodologici

- Repository di riferimento: <https://github.com/msitarzewski/agency-agents>
- Generative Agents: <https://doi.org/10.1145/3586183.3606763>
- Studio su simulazioni di persone: <https://hai.stanford.edu/policy/simulating-human-behavior-with-ai-agents>
- Attenzione pubblicitaria e banner blindness: Drèze & Hussherr, *Internet Advertising: Is Anybody Watching?* <https://doi.org/10.1002/dir.10063>
- Dataset e benchmark di progetto: Drive citato nella sezione 2. Per gli altri riferimenti citati nella ricerca preliminare, verificarne testo integrale e status scientifico prima di trasformarli in regole normative.


## 11. REQUISITO PRIORITARIO — simulare l'età anche senza ground truth demografico

**Non negoziabile:** la funzionalità di simulazione per età **DEVE ESISTERE FIN DAL MVP**. La mancanza nei CSV di impression/click per fascia d'età è un **problema di identificabilità da gestire ingegneristicamente**, non un motivo per rimuovere la funzionalità. L'app deve produrre per ogni segmento `expected_impressions`, `ctr_estimate`, `ctr_range`, `clicks_estimate`, `evidence_level`, `assumptions`, `age_sensitivity`, `scenario_id` e una motivazione contestuale. Il motore statistico predice, l'LLM può spiegare. **Nessun fallback a “non supportato, impossibile” per età; fallback obbligatorio a simulazione dichiaratamente teorica.**

### 11.1 Modalità e gerarchia di evidenza

- `observed_segment`: dati reali individuali/aggregati per età, se un giorno arriveranno; applica calibrazione e verifica.
- `external_informed`: dati di popolazione/uso del digitale/attività e-commerce per fasce comparabili (p.es. ISTAT/Eurostat) + evidenza sperimentale trasferibile; **nessun tasso e-commerce può essere usato direttamente come CTR**.
- `theory_based`: prior comportamentali e probabilistici con varianza esplicita, ancorati al baseline CTR delle campagne, utilizzabili immediatamente sul dataset attuale.
- `user_scenario`: prior e quote modificate dall'utente; risultati etichettati come scenario, mai osservati.

Se mancano tutte le fonti esterne usa prior debolmente informativi e **tre scenari** (`conservative`, `central`, `exploratory`), mantenendo l'app utilizzabile. Traccia `source_url`, `publication_year`, `population`, `geography`, `outcome_measured`, `transferability_warning`, `prior_strength` e `assumption_version` per ogni regola. Non trasformare un'associazione statistica in un effetto causale.

### 11.2 Fasce demografiche obbligatorie e comportamento

Fasce predefinite per la simulazione pubblicitaria ad adulti: `18-24`, `25-34`, `35-44`, `45-54`, `55-64`, `65+` (adattabili a supporto delle fonti disponibili; evitare minori nell'MVP). Per ogni fascia campionare **distribuzioni**, non valori deterministici, di: esposizione/uso della piattaforma, attenzione, familiarità di categoria/brand, motivazione, budget e sensibilità al prezzo, preferenza formato, propensione allo shopping digitale, advertising literacy/persuasion knowledge, tolleranza alla ripetizione, fiducia e frizione. Condizionare sempre anche su **settore, prodotto, messaggio, placement, stagione, scopo della sessione, evento calendario, esperienze pregresse**; dare spazio a variazioni individuali nella stessa fascia. Nessuna regola universale «giovani cliccano di più».

L'età può influenzare **più stadi distinti**: (i) probabilità di essere raggiunti e vedere impression; (ii) distribuzione del contesto d'uso; (iii) attenzione, percezione e memoria; (iv) interesse e click dato impression. Non confondere probabilità di accesso alla piattaforma con CTR condizionato a impression.

### 11.3 Modello quantitativo identificabile *solo* sotto assunzioni dichiarate

1. Prevedere e calibrare la **baseline osservabile** `p_base(ad, date, adset)` sulle righe aggregate (`click / impression`) tramite GLM binomiale/gerarchico, con calendari, formato, leva, storia disponibile e cold-start.
2. Per ogni età `s`, costruire un **effetto latente** `delta_s` da prior distribuzionali (possibilmente normali gerarchici centrati su zero) e interazioni con settore, prodotto, contenuto e contesto. Campionare `delta_s` su più seed e prior strength. Non apprenderlo falsamente dai conteggi aggregati come se ci fossero etichette di età.
3. Stimare quote di impression per fascia `q_s` dai margini esterni / ipotesi di reach/targeting, con `q_s >= 0` e `sum(q_s)=1`. Distinguere quote di **popolazione**, **utenti della piattaforma**, **raggiungibili** e **impression effettive**: non sono uguali.
4. Calcolare `p_s = sigmoid(b + delta_s)`, risolvendo numericamente l'intercetta `b` per imporre `sum_s(q_s * p_s) = p_base` in ogni replica. Questa **riconciliazione** impedisce di ottenere CTR segmentati incompatibili con la baseline aggregata. Nessuna affermazione che i veri `delta_s` siano stati identificati dai CSV.
5. Simulare impression/click per età usando stessa popolazione e `common random numbers` nei confronti A/B; aggregare per età e creatività. Campionare anche l'incertezza di `p_base`, `q_s`, `delta_s` e parametri del contesto: **non basta il rumore Bernoulli**.
6. Prevedere `CPM_s` **solo** tramite modello/caso d'uso di mercato/asta per segmento con parametri motivati; senza dati sulle aste demografiche mostrare `CPM_s` come *scenario range unvalidated* oppure `null` se non è formulabile un'ipotesi plausibile. Mantenere spesa e impression coerenti con il budget condiviso di (`data`,`adset_id`); riconciliare anche le somme di segmento.

Esempio di input strutturato (valori *illustrativi*, non parametri empirici):

```json
{
  "scenario_id":"age-demo-v1", "country":"IT", "vertical":"beauty_skincare",
  "platform":"meta", "age_bands":["18-24","25-34","35-44","45-54","55-64","65+"],
  "audience_source":"theory_based", "cohort_distribution_source":"external_or_assumed",
  "behavioral_prior_version":"age-priors-v1", "prior_strength":"medium",
  "sensitivity_profiles":["conservative","central","exploratory"],
  "common_seed":42, "reconciliation":"weighted_ctr_to_aggregate"
}
```

**Identificabilità:** molte combinazioni di CTR per età producono lo stesso CTR aggregato; l'app offre distribuzioni plausibili *condizionate alle assunzioni*, non una verità demografica ricavata dai CSV. La UI non deve nascondere questo limite, ma **deve mostrare comunque le simulazioni dettagliate**.

## 12. Agenti contestuali e motore di conoscenza

**Offline:** pipeline versionata ingestione → validazione ETL → feature store (solo feature disponibili al momento della previsione) → modelli baseline CTR/CPM/delivery → prior esterni documentati → prove di coerenza e validazione (train, validation, test). Non addestrare a ogni run. Scegliere il modello su validation e riservare il futuro test; evitare pseudocodice che selezioni il modello “sull'holdout”.

**Runtime:** `brief → ScenarioParser(LLM, output JSON) → Pydantic → ContextBuilder → age-aware AudienceBuilder → Attention/Meaning/Action/Memory → probabilità aggregate riconciliate → Monte Carlo → validator → analista LLM → report`. In caso di job costoso usare worker/queue e stato asincrono. I profili esistono come **record tipizzati**; ogni agente non richiede un'istanza LLM autonoma. SDV, Bayesian Network e pgvector sono **opzionali** e vanno introdotti quando verificabilmente utili: SDV genera dati sintetici, reti bayesiane strutturano ipotesi condizionali, pgvector recupera campagne simili; nessuno di questi strumenti crea evidenza individuale dal nulla.

`ConsumerProfile` mantiene l'identità plausibile (classe d'età e preferenze stabili); `ConsumerState` conserva memoria e stato correnti; `ExposureContext` viene **rigenerato per ogni impression** con data, campagna, adset, creatività, leva, placement, task di browsing, device e contesto competitivo. Lo stato cambia con transizioni controllate, mai arbitrariamente tramite riscrittura LLM. Il parser LLM è trattato come input non attendibile: output tipizzato, whitelist e limiti sui campi; comunicazione in JSON/oggetti, non istruzioni eseguibili.

**Vincolo di sviluppo:** il sistema non va considerato concluso se sa prevedere soltanto CTR complessivo e rifiuta di calcolare CTR per età. Al contempo non può pubblicare accuratezze per età inesistenti: deve saper operare in modalità `theory_based` con confidence ed evidenza esplicite.

## 13. Benchmark, falsificabilità e test obbligatori dell'età

- Test di riconciliazione `abs(sum_s(q_s*p_s) - p_base) <= tolerance` per ogni seed/annuncio/giorno; normalizzazione di quote e probabilità 0..1.
- Test di aggregazione: `sum_s(impressions_s) = impressions_total`, `sum_s(clicks_s) ≈ clicks_total` nei valori attesi e `sum_s(spend_s) <= adset_budget`; CTR espressi con unità coerenti (% vs proporzione).
- Stessa creatività, stesso seed e stesse ipotesi → risultati identici; variazioni di contesto/memoria → reazioni distribuzionali potenzialmente differenti.
- Test cold-start: asset in `da_prevedere.csv` non presenti nello storico continuano a funzionare con prior più incerti.
- Test trasparenza: almeno una simulazione 18–24 vs 55–64 mostra *ipotesi differenti per contesto plausibile*, ma il motore **non deve imporre un ordine monotono per età**; test sensitivity per invertire o annullare differenze plausibili.
- Test di non-identificabilità: eseguire scenari con prior differenti e stesso baseline; dimostrare che il ranking demografico può cambiare senza nuove etichette. Report chiaro sul livello di evidenza.
- Test della correttezza dei pesi di esposizione e della ricalibrazione; non usare quote di utilizzo delle piattaforme come CTR.
- Prevedere un percorso di miglioramento futuro con mini-survey, panel volontari o campagne A/B stratificate per fasce d'età nel rispetto di normative e policy; importare tali risultati per aggiornare prior e validare il ranking demografico.

## 14. Fonti scientifiche e statistiche per i prior (non per inventare CTR)

1. **ISTAT, Cittadini e ICT — Anno 2025**: riferimento per Italia, utilizzo di Internet, competenze digitali e acquisti online per età; non è un dataset di CTR. <https://www.istat.it/comunicato-stampa/cittadini-e-ict-anno-2025/>
2. **Eurostat, Digitalisation in Europe — 2026 edition**: profili e-commerce per età e paese, come ancoraggio di comportamento digitale, non tassi pubblicitari. <https://ec.europa.eu/eurostat/web/interactive-publications/digitalisation-2026>
3. **Pew Research Center, Social Media Use by Age — 2026**: quote piattaforme per età in rilevazioni multinazionali/USA; trasferibilità in Italia da valutare. <https://www.pewresearch.org/chart/social-media-use-by-age-2/>
4. **Older and younger adults: visual attention to advertising and credibility (2023)**: esperimento eye-tracking per guidare l'ipotesi su attenzione, credibilità e differenze di elaborazione; non fornisce un effetto universale sull'CTR Meta. <https://academic.oup.com/innovateage/article/7/5/igad051/7192745>
5. **Differences in advertising's effectiveness across age groups (2024)**: evidenza sulle differenze di misure cognitive/associative tra età, senza conversione diretta in probabilità di clic. <https://www.tandfonline.com/doi/full/10.1080/02650487.2024.2370678>
6. **Friestad & Wright (1994), Persuasion Knowledge Model**: basi teoriche per il modo in cui si riconoscono e affrontano le tecniche persuasive. <https://doi.org/10.1086/209380>
7. **Generative Agents (2023)**: memoria e interazioni emergenti; non validazione CTR. <https://doi.org/10.1145/3586183.3606763>

Per ogni studio salvare `study_id`, tipo fonte, anno, contesto, popolazione, outcome misurato, effetto qualitativo/quantitativo, limiti, variabile del modello, scelta del prior, intervallo/forza, e avvertenza di trasferibilità. **Evitare falsi coefficienti causali**: quando la fonte non stima una dimensione d'effetto applicabile, scegliere una famiglia di prior ampia e dichiararla, testandone la sensibilità.
