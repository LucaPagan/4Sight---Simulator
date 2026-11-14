# Audience Simulator — Piano implementativo aggiornato

Approvato per esecuzione dall'utente il 14 novembre 2026. Metodo: Ponytail full e Superpowers executing-plans/TDD. Fonti vincolanti: AGENT_SYSTEM_SPEC.md e IMPLEMENTATION_REQUIREMENTS.md nella stessa directory.

## 1. Executive brief e decision log
L'utente inserisce brand, prodotto, settore, mercato, date, budget, audience e da una a quattro creatività. Il sistema genera 120 consumatori sintetici (20 per sei fasce adulte); ogni agente valuta ogni creatività tramite un LLM locale. Il comportamento viene simulato e aggregato in CTR, CPM, impression, clic e spesa attesi, confronti e diagnosi. Distinguere reazioni del panel, forecast calibrato e ipotesi. Nessuna previsione vendite/CPA/ROAS nel MVP.

Decisioni dell'utente: applicazione locale completa; Mac Apple M4/24GB; solo modelli locali senza API pagate; LLM per ogni agente; panel iniziale 120. Un solo modello condiviso, chiamate isolate per profilo. Qualità tecnica LLM, coerenza matematica, accuratezza aggregata e plausibilità demografica sono verifiche diverse.

Stack: Next.js/React/TypeScript/Recharts; Python3.12/FastAPI/Pydantic/SQLAlchemy/Alembic; PostgreSQL; Redis/RQ; S3 locale; Pandas/NumPy/SciPy/statsmodels/scikit-learn. Ollama nativo sul Mac. Nessun framework multiagente o pgvector/SDV/MLflow iniziale. Modello candidato Qwen3.5-9B quantizzato; confrontare Qwen3.5-4B e Ministral3-8B Instruct (Apache2.0), scegliere solo dopo benchmark reale.

## 2. Dataset audit & feature plan
Il kit Drive contiene dati simulati. Materializzare in data/ i 13 CSV originali e un manifest URL/hash. Non distribuire il kit nel repository. Storico:1879 righe (1435 training,444 validation); futuro:699; calendario:106; budget:1272; annunci:69; adset:12; campagne/inserzionisti:3 ciascuno; asset:36 in tre CSV; benchmark CPM:704; indici settimanali2025:66. Chiave storico/futuro (data,ad_id), budget(data,adset_id), asset_id per creatività.

Audit verificato:9 CPC null corretti con zero clic;168 disaccordi periodo budget (calendario autoritativo); FGR-AS1 21/10 spend397.55 vs budget100 (raw preservato, esclusione fitting delivery); CDF-AS3 10/11 spend50.01 vs50 (warning arrotondamento storico).12 annunci e6 asset nuovi nel futuro. Nessuna leva black_friday nel training; extrapolazione esplicita. CTR/CPM originali coerenti entro arrotondamento; nessun duplicato o riferimento mancante nei controlli iniziali.

Split vincolante: train17/08–01/11;validation02–15/11; futuro16–30/11 senza label. Nessun refit ufficiale su validation. Feature solo pre-impression; vietati risultati contemporanei (spesa,impression,click,ctr,cpm,cpc,copertura,frequenza). Lag e statistiche congelati al cutoff per tutto l'orizzonte. Benchmark CPM compatibili per paese/piattaforma/obiettivo; quartili non sono intervalli predittivi. Indici2025 relativi, allineati alla distanza dal Black Friday; disponibilità temporale non documentata dichiarata come assunzione. PaeseIT e audience non sono osservati.

## 3. User journeys e UX blueprint
Percorso: nuovo brief → creatività → pubblico → simulazione → confronto → diagnosi → export. Form richiede prodotto/brand/vertical/meta/mercato/date/budget; prezzo e disponibilità sconosciuti non inventati. Sei fasce18-24,25-34,35-44,45-54,55-64,65+. Pagine: brief, libreria, pubblico, job, risultati, confronto, agente, storico, validation, import. Ogni pagina deve gestire empty/loading/error/preliminary/partial/complete. Tabelle alternative ai grafici, tastiera, focus, contrasto e responsive. Mostrare copertura reale delle policy, badge theory_based, raw panel e KPI calibrati separati. Campagne nuove non alterano le699 righe ufficiali.

## 4. Architettura e data flow
Monolite modulare: datasets,campaigns,forecasting,evidence,audience,agents,behavior,simulations,reporting,llm. Brief→Pydantic→ContextBuilder→120profili→piano policy→Ollama→JSON validato→gate/memoria→panel→calibrazione/age reconciliation→MonteCarlo→auditor→report. CLI e API condividono servizi scientifici. PostgreSQL stato autorevole; RQ orchestration; object storage artefatti. Snapshot input immutabile e pubblicazione atomica. Consumer LLM obbligatorio; parser/analista possono avere fallback deterministico.

Ollama un modello/concorrenza1, contesto8192 e output512 come impostazioni iniziali da misurare. Verificare worker Docker→host senza esporre runtime alla LAN. Copy/CSV come dati non attendibili; JSON extra vietati; nessun codice eseguibile dai prompt. Segreti backend, origini consentite, limiti upload, SQL parametrizzato e formule CSV neutralizzate.

## 5. Modello dati
Tabelle richieste: datasets,advertisers,campaigns,campaign_briefs,adsets,ads,assets,daily_observations,forecast_rows,budgets,calendar,market_benchmarks,assumptions,behavioral_evidence,scenarios,populations,consumer_profiles,consumer_states,agent_evaluations,exposure_events,simulation_runs,model_versions,predictions,age_predictions,prediction_explanations,validation_runs,llm_benchmark_runs,job_events. UUID applicativi, chiavi importate scoped dataset; ID originali mantenuti. Date giornaliere, timestampUTC, euro decimal, probabilità0..1, conteggi nonnegativi; indici FK/run/date/adset. Foreign key e unicità; gli outlier storici restano registrabili.

Evidence:observed/calibrated_estimate/modeled_assumption/qualitative_hypothesis. Audience:observed_segment/external_informed/theory_based/user_scenario. Completion:preliminary/partial/complete. Confidence:validated_on_validation/unvalidated/extrapolation/failed_quality_checks. Snapshot policy necessari al replay conservati con la run; log e cache non referenziata30giorni. Cancellazione esplicita bloccata per job attivi.

## 6. Contratti e API
Prefisso/api/v1. Schemi Pydantic strict-extra, OpenAPI/JSON Schema generati e tipiTS derivati. Contratti:CampaignBrief,Scenario,RunContext,CreativeFeatures,ConsumerProfile,ConsumerState,AgentEvaluation,ExposureContext,ExposureResponse,Prediction,AgePrediction,SimulationReport. Campi run/seed/dataset/model/prompt/prior/hash/cutoff obbligatori. Valutazioni agenti ordinali con riferimenti e unknown, mai KPI numerici inventati. Ignorato→spiegazione null.

Endpoint: POST datasets/import;GET datasets/{id};GET/POST campaigns;GET/POST assets;POST scenarios;POST populations/generate;GET populations/{id};POST simulations/preflight;POST simulations;GET simulations/{id}/status;POST simulations/{id}/resume,cancel;GET predictions;POST comparisons,backtests,exports;GET backtests/{id},exports/{id},runtime/status;GET simulations/{id}/agents/{agent_id}. Job queued→running→succeeded/failed/canceled con waiting_for_runtime/waiting_for_capacity riprendibili. Stato completamento distinto. Modello cambiato in resume→409. Nessun completo con policy mancanti.

## 7. Agenti dinamici e modelli gratuiti
Ogni profilo ha tratti persistenti e stato/memoria separati. Generazione dopo contesto, pesiq_s/n_s, diversità interna. Nessuna storia personale dedotta da frequenza aggregata. Lifecycle created→sampled→exposed→ignored/noticed→interpreted?→click/no_click→memory_updated. Contesto rigenerato a ogni esposizione.

Unità LLM:agente×creatività×regime calendario.120×2=240valutazioni per un regime. Policy condizionale a notare, non testimonianza umana reale. Cambi entro contratto (stato/memoria/data nel regime) gestiti dal motore; cambi di prodotto/copy/placement o fuori contratto richiedono nuova policy. Cache su input+profilo+creativa+regime+modello+prompt; retry mirato. Replay esatto solo dallo snapshot delle risposte, non promessa di token identici su nuove inferenze.

Benchmark96risposte per candidato:60casi(3vertical×2creative×10profili)+12critici+24rigenerazioni. Gate:>=95%JSON primo tentativo,tutti validi dopo max1retry,zero fallimenti12critici,>=90%rubrica grounding/italiano/profilo/unknown/frizioni. Revisione cieca umana; registrare conteggi, rubriche, latenza/memoria. Fra candidati idonei migliore qualità; entro2punti percentuali scegliere più rapido. Se nessuno passa correggere prompt/schema, non inventare idoneità.

Registry evidenze:study_id,URL,anno pubblicazione/periodo dati,popolazione,geografia,outcome,metodo,qualità,stato revisione,variabile,prior,forza,warning trasferibilità e versione. ISTAT2025,Eurostat2026,Pew2026 per abitudini non CTR; Fung2023 attenzione/credibilità non MetaCTR; Mecredy pending_review; Friestad/Wright teoria; GenerativeAgents memoria non validazioneCTR. Niente tasso shopping→CTR. Fonti non lette integralmente senza coefficienti empirici.

Esempi obbligatori NDL-AD03 routineautunno, CDF-S3 cucce/taglie, FGR-S3 capsule:18-24 vs55-64 con bisogni contestuali, e scenari invertiti/neutri. Nessun ordinamento monotono imposto. Agency-agents solo pattern ruolo/workflow/voce consumatore-analista; riferimento8ae6164602c95ca78828b148b9052460ee426885, verificare attribuzione prima del riuso testuale.

## 8. Modeling & forecasting
Baseline smoothing CTR gerarchico e GLM binomiale su successi/insuccessi aggregati. CPM distinto log-regressione con prior compatibili. Delivery unico budget adset-giorno:spesa=B×utilizzo×quotaad;I=1000×spesa/CPM;click=I×p. Budgetzero→deliveryzero; centesimi riconciliati maggioriresti. Niente training validation/test; CV temporale interna e selection esterna dichiarata.

Raw panel segnali LLM entrano realmente nei gate. Candidato augmentation usa descrittori aggregati senza pseudolabelindividuali. Se non migliora val, forecast ufficiale baseline e report esplicito, agenti comunque richiesti per laboratorio completo. Gate:Pclick=Pnotice×Prelevant|notice×Paction|notice,relevant. Interesse non forza click.

Age:q~Dirichlet(10×6) quando nessun margine trasferibile, fasce escluseq0; delta normale gerarchico con interazioni settore/messaggio/placement/calendario/memoria e segnali agenti, non stimato da false label età. Sigma conservative.15/central.35/exploratory.70 progettuali; forza0..2. ps=sigmoid(b+delta_s), trovareb con sum(qps)=pbase (tol1e-10); estremi pbase0/1 diretti; bracket logit(pbase)-maxdelta..logit(pbase)-mindelta. Is=Iqs,Cs=Isps. Spesa_s=qsspesa con assunzioneage_neutral_cost_v1;CPMs null salvo scenarioasta esplicito.

Gate individuali riconciliati tramite shift comune t sui trelogit, risolvendo media ponderata prodotto=ps. Registrare aggiustamento.1000replicheMonteCarlo,quantili5-95%,baseline/CPM/delivery/q/delta/context uncertainty. Intervalli condizionati alle policy LLM, sensitivity rigenerazioni separata. CTR riassunto=100Eclick/Eimpression; quote e tassi segmenti da conteggi medi. Same-panel/stato iniziale clonato e common random numbers A/B, memoria separata. Ranking vincente P(delta>.10pp)>=.95;pareggioP(absdelta<=.10pp)>=.80;altrimentiincertezza.

## 9. Validation & test strategy
Metriche deviance/logloss binomiale,CTR weightedMAE,CPMMAE,calibrazione,ranking,coverage/ampiezza; breakdownvertical/formato/leva/coldstart. Nessuno score futuro/demografico senza label. Ablation baseline/LLMsenzaPersona/panel;promozione se deviance migliora>=2%,CTRMAE non peggiora>2%. Soglie fissate prima; assenza miglioramento lecita.

Test ETL,cutoffsentinella,binomiale,budget/zero/rounding,agequote/reconcile/0/1/q0,inversione/neutralità,eterogeneità,policycoverage/ripresa,ignore/memoria/A-B,replaysnapshot vsstabilitàregen,coldstart,injection/export,jobcrash,E2Enuovobrief3vertical,699ordine. Given239/240policy→partial e resume1sola; Ollamaoffline→baselinepreliminary noncomplete. Scenari raw e calibrated distinti.

## 10. Task eseguibili
Ogni task: test RED→implementazione minima→GREEN→verifica→commit. Durategiorni indicative0.5–2 per task.

|ID|Deliverable|Dipendenze|Verifica|
|---|---|---|---|
|T01|Audit offline|CSV|test_dataset_audit|
|T02|Import/API persistente|T01|test_dataset_import_api|
|T03|Feature in-time|T01|test_features_asof|
|T04|CTR baseline/GLM|T03|test_ctr_models|
|T05|CPM/delivery699|T04|test_delivery_forecast|
|T06|MC/validation/registry|T04,T05|test_model_validation|
|T07|Job/export API|T02,T06|test_prediction_jobs|
|T08|P0età/prior/reconcile|T06,T07|test_age_reconciliation|
|T09|Runtime/benchmarkLLM|T01|test_llm_runtime + benchmark reale|
|T10|120profili/policyindividuali|T08,T09|test_agent_evaluations|
|T11|Brief/dashboard età|T07,T08,T10|age-lab E2E|
|T12|Behavior/memoria|T10|test_behavior_engine|
|T13|Runcomplete/ripresa|T11,T12|test_simulation_coverage|
|T14|Creative/parserbrief|T02,T09,T11|test_campaign_brief|
|T15|Ranking/diagnosi|T13,T14|test_report_provenance|
|T16|Budgetsandbox|T05,T15|test_budget_scenarios|
|T17|Ablation/validationUI|T06,T13|test_ablation|
|T18|Storico/agenti|T13,T15|agent-history E2E|
|T19|Percorso3vertical/accessibilità|T14–T18|journeys E2E|
|T20|Sicurezza/retention|T13,T19|test_security_and_recovery|
|T21|CI/Compose/performance|T17,T20|suite + smoke locale|
|T22|README/export/demo|T21|artefatti e smoke|

Moduli sotto backend/audience_simulator/{datasets,forecasting,evidence,audience,agents,behavior,simulations,reporting,llm}; frontend/app e components; tests per i contratti. SQLAlchemy contratti condivisi, API Pydantic e OpenAPI unica fonte dei tipi frontend.

## 11. Backlog e milestone
M0dati/feature;M1baseline699;M2P0modelloqualificato+120agenti+6età;M3P0brief→agenti→report;M4memoria/ranking/diagnosi/budget;M5validation3vertical/consegna. Baseline sola non completa prodotto. P1label demografiche autorizzate/nuove fonti/boosting utile/immagini reali;P2BayesianNetwork/media generation/multiutentehosting. Stima30–42giornatepersona, non promessa di durata locale o scadenza hackathon.

## 12. Rischi e mitigazioni
Realismo!=accuratezza: gate separati; bias condivisi:sensitivity/challenger;panel120stabilità:offline120/240/600;tempi:cache/preflight/ripresa;runtimeoffline:waiting;policymancanti:partial;noagegroundtruth:theory_based;intervalli condizionati:LLMsensitivity;BFcoldstart:extrapolazione;leakage:cutoff;budgetripetuti:group;outlier:rawpreservato;claimnonverificati:flag;privacy:noPII;no conversioni:nessunROAS. Futura validazione panel volontari/test controllati età con disegno prestabilito, non prerequisitoMVP.

## 13. Primi dieci ticket pronti
T01 audit_dataset(Path)→DatasetAudit:offline13CSV,assert1879/699/1272/106,split1435/444,9CPCnull,168periodmismatch,2overspendseverity,immutable. Test pytest tests/test_dataset_audit.py -q.
T02 import_dataset(Path)→DatasetVersion:transazione,FK/hash/idempotenza,row_indexoriginale,rollback;tests/test_dataset_import_api.py.
T03 build_features(dataset,rows,as_of_date)→FeatureSnapshot:targetallowlist,asofaggregates,sentinelvalmutation;tests/test_features_asof.py.
T04 fit_ctr/predict_ctr→CTRModel/CTRPrediction:binomialcounts,zero-click,smoothing/coldstart,serializable;tests/test_ctr_models.py.
T05 forecast_delivery→ForecastFrame:699,identity,budgetunique,zero,centesimi;tests/test_delivery_forecast.py.
T06 run_validation/register_model→ValidationReport/ModelVersion:CVtrain,coverage,cutoff,notestscore,selectionlimit;tests/test_model_validation.py.
T07 execute_forecast(run_id):async,idempotency,atomic,crash/exportblocked,699keysorder;tests/test_prediction_jobs.py.
T08 reconcile_age_ctr/simulate_age:6fasce,tol1e-10,pbase0/1,q0,differenziato/inverso/neutro,nofalseobserved;tests/test_age_reconciliation.py.
T09 evaluate_json/benchmark_models:Ollamahealth,digest,schema,thinking,memory/latency,96risposte/candidato,nodownloadunit;tests/test_llm_runtime.py+CLIbenchmarkreale.
T10 generate_population/plan_evaluations/evaluate_agent:120profili20/fascia,pesi,varianza,240policy2creative1regime,persistretrymirato,nonumericLLMKPI;tests/test_agent_evaluations.py.

## 14. Checklist e stop/go
LLM:benchmarkpass,digest/prompt/snapshot,100%policy,gateinput,replay. Aggregati:traincutoff,baselinecomparison,calibration,coverage85–98%per90%nominaleconampiezza,augmentationthreshold,pubblicarescoreanchefailure,notestscore. Età:6fasce,mathbudget,sensitivity/inversione/neutro,diversità,provenance,nofalseaccuracy,CPMsnull/scenario. Prodotto:nuovobrief,120LLMagenti,reportdual,NDL/CDF/FGR,699export+age,README+video3min,CI/tests.

Stop reportcompleto per leakage/budget/math/policy missing. Go teorico per età senza label con theory_based, mai accuratezza inventata. Primo passo eseguibile T01 dopo materializzazione CSV. Validazione umana non ottenibile dal solo realismo LLM.
