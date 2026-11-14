# Audience Simulator

Un laboratorio locale per progettare e testare campagne Meta: inserisci prodotto, creatività, pubblico, periodo e budget; 120 consumatori sintetici valutano individualmente gli annunci tramite un LLM locale. Il report distingue reazioni del panel, CTR/CPM calibrati sul kit e ipotesi demografiche.

**Non è una validazione di esseri umani reali.** I dati Wevion sono simulati, non contengono label per età e non permettono di misurare accuratezza demografica. Nessuna campagna o spesa viene eseguita su Meta.

## Avvio locale

Richiede Python 3.12, Node 22+ e Ollama. Il kit dell'hackathon non viene redistribuito: collocare i suoi 13 CSV in `data/` (i tre asset in `data/asset_creativi/`). Nel workspace di sviluppo i file sono già stati materializzati.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
npm --prefix frontend ci
.venv/bin/python -m audience_simulator.cli bootstrap
```

Terminale 1, runtime locale (modelli negli artefatti del progetto, cloud disabilitato):

```sh
bash scripts/models.sh
```

Terminale 2, scaricamento modello candidato:

```sh
ollama pull qwen3.5:9b
```

Terminale 3:

```sh
.venv/bin/python -m audience_simulator.cli serve
```

Terminale 4:

```sh
npm --prefix frontend run dev
```

Aprire [http://127.0.0.1:3000](http://127.0.0.1:3000). In alternativa `bash scripts/dev.sh` installa le dipendenze e avvia API/frontend, lasciando Ollama separato.

Il primo forecast addestra e salva il modello statistico. Il percorso normale è **Nuova simulazione → brief e creatività → pubblico e ipotesi → avvio → risultati**. Una run non diventa completa finché tutte le policy richieste non sono valide. Se Ollama si disconnette, riprendere le sole mancanti dal report.

## Modelli e gratuità

Candidati Apache 2.0: `qwen3.5:9b`, `qwen3.5:4b`, `ministral-3:8b`. Un unico modello serve i 120 agenti con profili e chiamate separati. Nessun costo API; rimangono memoria, energia e tempo locali.

```sh
.venv/bin/python -m audience_simulator.cli benchmark --model qwen3.5:9b
```

Il benchmark produce 96 casi, retry, latenza e risposte in `artifacts/benchmarks/`. La validità JSON non sostituisce la rubrica di grounding, italiano, profilo, unknown e frizioni. Il report non dichiara qualificato automaticamente un modello senza revisione dei contenuti. Cambiare il modello con `AUDIENCE_OLLAMA_MODEL`; il digest fa parte della cache e una run non mescola digest diversi.

Ogni agente valuta ogni creatività per ciascun regime rilevante, non ogni singola impression. Con 120 agenti e due creatività: 240 valutazioni per regime. Memoria e contesto cambiano a ogni esposizione nel motore probabilistico; le policy sono reazioni condizionali a notare l'annuncio. Un'esposizione ignorata non produce un monologo.

## Audit, previsione e validazione

```sh
.venv/bin/python -m audience_simulator.cli audit
.venv/bin/python -m audience_simulator.cli train
.venv/bin/python -m audience_simulator.cli validate
.venv/bin/python -m audience_simulator.cli predict
```

L'export tecnico genera `artifacts/official/predictions.csv` (699 righe nello stesso ordine) e `age_predictions.csv` (4.194 righe). È una baseline preliminare con decomposizione teorica, distinta dalla simulazione completa LLM. Un nuovo brief non modifica il file ufficiale.

Training 17/08–01/11/2026; validazione 02–15/11; futuro 16–30/11 senza target. Le finestre interne al training stimano gli errori fuori campione. La validazione sceglie fra GLM e smoothing e non è presentata come test futuro indipendente. Nessun refit sulle label di validazione.

CTR = 100 × clic/impression. CPM = 1000 × spesa/impression. Il budget è condiviso fra gli annunci dell'adset. Le sei probabilità per età sono riconciliate numericamente al totale; quote, effetti e meccanismi rimangono ipotesi. CPM per età nullo senza modello d'asta.

Anomalie conservate: 168 disaccordi nel periodo dei budget (calendario autoritativo); FGR-AS1 il21/10 spende397,55€ contro100€ (escluso dal fitting delivery); CDF-AS3 il10/11 eccede di un centesimo. Nove CPC null corrispondono a zero clic. Nessuna creatività Black Friday nel training: extrapolazione esplicita.

## Docker Compose

Avviare Ollama nativo sul Mac e verificare che Docker Desktop possa raggiungerlo tramite `host.docker.internal:11434`, mantenendo il runtime privato. Poi:

```sh
docker compose up --build
```

Compose usa PostgreSQL, Redis/RQ e MinIO. La Community Edition di MinIO è distribuita solo come sorgente e il repository è archiviato: Compose compila una release fissata dal [repository ufficiale](https://github.com/minio/minio), senza dipendere dall’immagine Docker Hub rimossa. Questo percorso è per lo sviluppo locale. Solo il frontend espone una porta, su127.0.0.1:3000. Le password predefinite sono esclusivamente per lo sviluppo locale; configurare `.env` se necessario. Il percorso senza servizi usa SQLite e filesystem con gli stessi contratti. Nessuna autenticazione multiutente: non pubblicare questa configurazione su Internet.

Migrazioni: `.venv/bin/alembic upgrade head`. API e worker condividono schema e codice. Tutti gli artefatti sono in `artifacts/`; originali, policy e snapshot necessari al replay devono essere conservati. Il replay esatto parte dalle risposte LLM salvate, non da nuove generazioni potenzialmente diverse.

## Test

```sh
.venv/bin/pytest -q
.venv/bin/ruff check backend tests
.venv/bin/mypy backend/audience_simulator
npm --prefix frontend run typecheck
npm --prefix frontend run build
cd frontend
npx playwright install chromium
npm run test:e2e
```

I test del provider utilizzano un trasporto HTTP controllato, non simulano una validazione del modello reale. Il benchmark locale è separato. In CI, il kit non redistribuito comporta skip espliciti dei test che lo richiedono; matematica, contratti e comportamento restano eseguibili.

## Documentazione

- [Piano](docs/IMPLEMENTATION_PLAN.md)
- [Specifica agenti](docs/AGENT_SYSTEM_SPEC.md)
- [Requisiti originali](docs/IMPLEMENTATION_REQUIREMENTS.md)
- [OpenAPI](docs/openapi.json), rigenerabile con `audience schemas`

I pattern dei ruoli si ispirano ad agency-agents; nessun suo predittore scientifico è stato riutilizzato. Le fonti esterne hanno stato di revisione e limiti nel Behavioral Evidence Registry dell'app.

## Video di tre minuti

0:00–0:35 brief e due creatività;0:35–1:05 pubblico/quote/prior;1:05–1:35 copertura delle valutazioni individuali;1:35–2:10 report CTR/CPM, fasce e reazioni;2:10–2:40 confronto e ipotesi da testare;2:40–3:00 validazione e limiti. Il file video non viene fabbricato dal codice: registrare una sessione reale dopo il benchmark e una run completa.
