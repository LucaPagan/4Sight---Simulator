# Audience Simulator — contesto del lavoro svolto (da passare a un altro assistente)

Aggiornato al 15 novembre 2026. Riassume cosa è il progetto, cosa è stato costruito in questa sessione di lavoro, i risultati misurati e cosa resta aperto. Non contiene chiavi né dati personali.

## 1. Cos'è il progetto

Applicazione web che simula come un pubblico reagisce a creatività pubblicitarie per Instagram e Facebook, prima di spendere budget. L'utente scrive la campagna e due o più creatività; un pannello di consumatori sintetici le valuta; l'app indica quale è avanti e perché.

- **Backend:** Python, FastAPI, pydantic, SQLite, numpy/scipy/sklearn. Pacchetto `backend/audience_simulator`.
- **Frontend:** Next.js 16, componenti client, CSS proprio, test e2e Playwright con API finta.
- **Modelli linguistici:** Ollama in locale (`qwen3.5:9b`), Google Gemini (`gemini-3.5-flash-lite`, `gemini-3.8-flash`) e Cloudflare Workers AI, solo piani gratuiti, nessun ripiego a pagamento.
- **Avvio:** backend `.venv/bin/python -m audience_simulator.cli serve` (porta 8000), frontend `npm --prefix frontend run dev` (porta 3000).

## 2. Due modalità di simulazione

1. **Stima dai dati storici** (flusso precedente, prompt `consumer-policy-v7.1`): il CTR viene da un modello statistico sui dati storici; gli agenti spiegano solo il perché. Non è stato toccato.
2. **Persone simulate** (`mode: agent_native`, sperimentale): le decisioni degli agenti determinano attenzione, interazioni e click. Il forecast storico resta accanto come riferimento, con un segnale di divergenza. È sempre etichettata «non validata».

## 3. Come funziona «Persone simulate»

```
Brief + pubblico (stile Meta Ads + testo libero)
  → scheletro statistico della persona      persona_model.py
  → scheda-persona scritta dal modello      persona_cards.py   (persona-writer-v2)
  → reazione all'annuncio «come visto»      reactions.py       (agent-reaction-v8.1)
  → motore: CTR, segmenti, confronto        native_engine.py
  → controlli di qualità                    decision_quality.py, counterfactual.py, prompt_eval.py
```

- **Pubblico:** `TargetingSpec` copre le opzioni di Ads Manager (località, età, genere, interessi con includi/restringi/escludi, posizionamenti, dispositivo, orari, frequenza). Il testo libero («chi ha un cane e vive da solo») è tradotto in vincoli e in proxy realmente selezionabili su Meta, con un avviso quando l'attributo non è selezionabile. Il pannello riproduce chi l'annuncio raggiungerebbe davvero, non solo il pubblico ideale.
- **Scheletro:** attributi correlati tra loro (copula gaussiana), campionati in base al pubblico, con controllo della diversità del pannello.
- **Scheda:** nome, città, mestiere, routine, rapporto con la categoria, abitudini social, modo di reagire alle pubblicità. Un validatore deterministico confronta la scheda con lo scheletro; se fallisce tre volte, la persona riceve una «scheda essenziale» dichiarata.
- **Reazione:** il modello interpreta la persona in una situazione (momento, attività, umore) e vede l'annuncio in due tempi, primo sguardo e lettura. Risponde su 100 volte quante salta, guarda, interagisce, clicca.
- **Motore:** aggrega le decisioni pesate per copertura, con intervalli bootstrap, ripartizioni per segmento e confronto con il riferimento storico.

## 4. Vincoli dichiarati

- `docs/PROMISE.md` pre-registra la verifica: prompt, modello e parametri si scelgono solo sul gruppo di sviluppo o su dati sintetici; il gruppo di test congelato si valuta una volta sola e i suoi esiti non si leggono.
- Nessun dominio è verificato: «Persone simulate» non può dichiararsi accurata.
- Nessuna riconciliazione forzata del CTR degli agenti sul dato storico (scelta dell'utente: agenti decisori).
- Niente è stato committato su git: tutte le modifiche sono nell'albero di lavoro.

## 5. Risultati misurati

### Prova reale in locale (30 persone, 2 creatività, `qwen3.5:9b`)
- Schede: 21 scritte dal modello, 9 essenziali; 43 minuti.
- Reazioni: 60 in circa 40 minuti.
- CTR dalle persone: 3,95% (A) e 5,72% (B); riferimento storico circa 1,2% (intervallo 0,3–2,8%).
- Confronto A/B: B avanti di 1,7 punti, intervallo da −3,9 a +0,4: nessun vincitore verificato.
- Qualità: tutte le reazioni citano l'annuncio, incoerenze 3%, attenzione media 39%.
- Cosa muove le decisioni: routine di cura della pelle 23%, genere 17%, occupazione 11%.

### Prova reale in cloud (8 persone, Gemini Flash-Lite)
- 8 schede in 12 secondi con una sola chiamata, tutte accettate.
- 8 reazioni in 44 secondi.
- Click medio 10 su 100: più alto che in locale.

### Run completa dall'app in cloud (30 persone, 2 creatività, Gemini Flash-Lite)
- Durata totale circa 6 minuti e mezzo (in locale un'ora e mezza).
- Schede: 30 su 30 scritte dal modello in 41 secondi con 5 chiamate; un solo rifiuto, poi corretto; 3 omissioni accettate e riportate.
- CTR dalle persone: 7,36% (A) e 6,94% (B); riferimento storico circa 1,2%. La sovrastima è più forte che in locale.
- Confronto A/B: A avanti di 0,5 punti, intervallo da −0,9 a +1,7: nessun vincitore verificato. In locale era avanti B: i due modelli non concordano sull'ordine.
- Qualità: tutte le reazioni citano l'annuncio, incoerenze 5%, attenzione media 35%, click medio 8 su 100. 16 decisioni su 60 dichiarano 0 click, 17 ne dichiarano 15 o più.

### «Più dati migliorano l'affidabilità?» (curve di apprendimento sul gruppo di sviluppo)
- Il modello linguistico degli agenti non viene addestrato dal progetto: più dati di campagne non lo cambiano.
- Ciò che si può addestrare è un modello testuale a coppie. Baseline a sette caratteristiche: 57,3% → 60,1% al crescere dei dati. Modello testuale ricco: 58,1% → 67,3%, cioè +7,3 punti sulla baseline (p < 0,001).
- Nessun dataset pubblico adatto di campagne a pagamento è stato trovato; nulla è stato scaricato.

## 6. Diagnosi dei tre problemi aperti

1. **Schede rifiutate (30% in locale).** Il validatore trattava un'omissione come una contraddizione. Corretto: i campi di controllo li compila il codice; un fatto non nominato non blocca più la scheda (tranne l'animale nella categoria pet) e finisce nel report; la negazione è riconosciuta anche dopo la parola; al nuovo tentativo il modello riceve la frase rifiutata.
2. **Tempi.** In locale decine di secondi per chiamata. In cloud il problema sparisce (30 persone e 2 creatività: circa 64 chiamate, 6–7 minuti). Il limite diventa la quota: 500 richieste al giorno su Gemini gratuito, 10.000 neurons al giorno su Cloudflare.
3. **Livello del CTR.** L'ipotesi «la scala su 100 è troppo grossolana» è stata smentita dai dati: gli «1 su 100» pesano pochissimo, mentre da un terzo a metà delle persone dichiara 5 o più click su 100. La sovrastima c'è anche con Gemini, quindi è del metodo e non del modello piccolo. Non è ancora risolta.

## 7. Correzioni per il cloud fatte in questa sessione

- Un errore del provider durante le schede non produce più schede essenziali in silenzio: la run si ferma e mostra il messaggio del provider.
- Sovraccarichi passeggeri (HTTP 503, timeout) vengono ritentati due volte.
- Il messaggio di quota esaurita dice fra quanti minuti riprovare.
- Se un modello online è configurato, l'app parte da quello invece che dal locale.

## 8. Stato delle verifiche

- 302 test Python, lint (ruff) e tipi (mypy) passano; 10 test e2e passano.
- Una run da 30 persone su Gemini è stata avviata dall'app dopo queste correzioni («Prova persone simulate (30) · Gemini»).

## 9. Cosa resta da fare

- Ridisegnare la correzione del livello del CTR: provare varianti del prompt di reazione su dati sintetici (domanda in due passi, esempi con valori più bassi) e scegliere quella che abbassa il livello senza appiattire le differenze tra persone.
- Misurare in locale l'effetto del riordino del prompt (esempi e persona prima, annuncio in fondo) sul tempo per chiamata.
- Mostrare nel preventivo della run quante richieste servono rispetto alla quota giornaliera del provider.
- Pilota con esiti reali sul gruppo di sviluppo (coppie di titoli Upworthy): misura l'ordine delle preferenze, non il livello.
- Documentazione finale `docs/AGENT_PERSONAS.md`.
- Per validare il livello del CTR servono dati di campagne reali dell'utente.

## 10. File principali

- Backend: `persona_model.py`, `persona_cards.py`, `stimulus_view.py`, `reactions.py`, `native_engine.py`, `decision_quality.py`, `counterfactual.py`, `prompt_eval.py`, `learning_curve.py`, `cloud.py`, `cloudflare.py`, `agents.py`, `service.py`, `api.py`, `schemas.py`.
- Frontend: `components/new-simulation.tsx`, `targeting-form.tsx`, `results-view.tsx`, `native-panels.tsx`, `persona-gallery.tsx`, `app-provider.tsx`, `lib/types.ts`, `lib/copy.ts`.
- Script: `scripts/live_prompt_check.py` (prova reale di schede e varianti di prompt), `scripts/diagnose_native.py` (diagnosi di una run).
- Documenti: `docs/PROMISE.md`, `docs/AUDIENCE_AND_REACTIONS.md`, `docs/DEMO_VIDEO.md`.
