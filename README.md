# Audience Simulator

Un laboratorio locale per confrontare creatività di campagne Meta prima di spendere budget: descrivi prodotto, annunci, pubblico, periodo e budget; un pubblico di consumatori sintetici li valuta uno per uno e il report indica quale creatività sembra funzionare meglio, con CTR e CPM attesi.

**Non è una validazione su persone reali.** I numeri di mercato sono stimati da dati storici simulati e dalle reazioni di un modello linguistico: servono a confrontare idee, non a prevedere i risultati di una campagna. Nessuna campagna viene pubblicata e nessuna spesa viene eseguita su Meta.

## Avvio rapido

Servono **Python 3.12+** e **Node.js 20.9+**. Poi, da terminale:

```sh
git clone <url-del-repository> audience-simulator
cd audience-simulator
./start.sh
```

Lo script fa tutto da solo: installa le dipendenze (solo la prima volta, qualche minuto), prepara i dati, avvia backend e interfaccia e apre il browser su [http://127.0.0.1:3000](http://127.0.0.1:3000). `Ctrl+C` ferma tutto. Non servono Docker, database o account.

### Il motore AI

I consumatori simulati ragionano con un modello linguistico. Hai tre strade, tutte dall'app (**Impostazioni → Motore AI**):

| Strada | Cosa fare | Costo |
|---|---|---|
| **Sul tuo computer (consigliata)** | Installa [Ollama](https://ollama.com/download). `./start.sh` scarica da solo il modello `qwen3.5:4b` (circa 3 GB, una volta). Se preferisci, lo scarichi con un clic dall'app. | gratis |
| **Cloud, Google Gemini** | Incolla una chiave gratuita di [Google AI Studio](https://aistudio.google.com/apikey). | piano gratuito |
| **Cloud, Cloudflare Workers AI** | Incolla Account ID e token di un account Workers Free. | piano gratuito |

**Anche senza nessun motore l'app funziona**: la simulazione restituisce una stima statistica dai dati storici e, appena prepari il motore, puoi riprenderla per aggiungere le reazioni dei consumatori simulati.

Un modello sul tuo computer è lento: con `qwen3.5:4b` una simulazione «Standard» (120 consumatori) richiede decine di minuti su un portatile, «Veloce» (60) la metà; durante l'attesa vedi subito la stima statistica, che si aggiorna da sola. I modelli cloud gratuiti sono molto più rapidi. Un modello più piccolo è più veloce ma meno accurato. Per un risultato migliore su un computer potente: `AUDIENCE_OLLAMA_MODEL=qwen3.5:9b ./start.sh` (poi `ollama pull qwen3.5:9b`). Se il modello scelto non è installato, l'app usa il migliore tra quelli presenti.

### Dati

L'app include un **dataset storico dimostrativo**, generato in locale e interamente sintetico: serve a provarla subito, i suoi numeri non descrivono un mercato reale. Se hai il kit originale dell'hackathon (13 CSV), copialo in `data/` (i tre asset in `data/asset_creativi/`) e riavvia: verrà usato al posto di quello dimostrativo.

## Come si usa

**Nuova** → racconta la campagna e scrivi due o più creatività → (facoltativo) descrivi il pubblico → **Avvia simulazione** → leggi il risultato. Le simulazioni restano salvate in **Simulazioni**. Se qualcosa si interrompe (modello spento, quota finita) si riprende da dove si era fermata; le valutazioni già fatte non si ripetono.

Due modi di simulare:

- **Stima dai dati storici** (predefinito): il CTR parte dai dati storici e i consumatori simulati ne spiegano il perché.
- **Persone simulate** (sperimentale, richiede di descrivere il pubblico): il CTR nasce dalle decisioni di ogni persona simulata. Più lenta.

## Impostazioni tecniche

Variabili d'ambiente (o file `.env`, vedi `.env.example`):

| Variabile | Significato |
|---|---|
| `AUDIENCE_OLLAMA_MODEL` | modello locale preferito (predefinito `qwen3.5:4b`) |
| `AUDIENCE_API_PORT`, `AUDIENCE_WEB_PORT` | porte iniziali (se occupate si usano le successive) |
| `AUDIENCE_NO_BROWSER=1` | non aprire il browser |
| `SKIP_MODEL_DOWNLOAD=1` | non scaricare il modello all'avvio |

I segreti cloud restano in file privati sotto `artifacts/`, mai nel database o nei report. Nelle modalità cloud il brief e i profili sintetici sono inviati al provider scelto. Tutti i dati dell'app (database SQLite, cache, risultati) sono in `artifacts/`.

## Per sviluppatori

```sh
.venv/bin/pytest -q
.venv/bin/ruff check backend tests
.venv/bin/mypy backend/audience_simulator
npm --prefix frontend run typecheck
npm --prefix frontend run test:unit
cd frontend && npx playwright install chromium && npm run test:e2e
```

Riferimenti: [OpenAPI](docs/openapi.json) (rigenerabile con `audience schemas`), [specifica degli agenti](docs/AGENT_SYSTEM_SPEC.md), [piano](docs/IMPLEMENTATION_PLAN.md), [calibrazione](docs/CALIBRATION.md), [incertezza](docs/UNCERTAINTY.md). Comandi CLI (audit, benchmark, ablation, ecc.): `.venv/bin/python -m audience_simulator.cli --help`.
