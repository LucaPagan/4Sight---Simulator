# Pannello, stimolo e qualità delle reazioni (fase 3)

Stato: 14 novembre 2026. Marginali Eurostat scaricate il 14 novembre 2026 per IT, ES, FR, DE (periodo 2025 per popolazione, social e acquisti online) in `backend/audience_simulator/specs/marginals.json`. Il pannello predefinito per questi paesi è ora `profiles-v2`; resta `profiles-v1` senza il file o per altri paesi.

## 4 · Stimolo strutturato (solo testo)

L'agente riceve ora, oltre a titolo, testo, CTA, formato e leva: `offer`, `price_text`, `landing_page_summary` per creatività e `device` per la campagna (`schemas.py`). I campi sono facoltativi; i contratti generati li espongono come opzionali (nessuna rottura del frontend). `PROMPT_VERSION` passa a `consumer-policy-v7`: **la cache delle policy precedenti non vale più** e gli ID di valutazione del caso pubblico GWWC cambiano.

Le lacune del brief sono riepilogate una volta in `report.input_gaps` (`reporting.input_gaps`): prezzo, descrizione del visual per ogni creatività e pagina di destinazione per gli obiettivi di vendita. Il prompt chiede di non fare del prezzo mancante il tema della reazione.

Non gestito: immagini e video reali (decisione: solo testo strutturato). Il form del frontend non espone ancora i nuovi campi: da fare nella fase 5 con le altre modifiche UI.

## 7 · Qualità delle reazioni (`reaction_quality.py`)

Controlli lessicali e a regole su ogni reazione, riportati in `behavior.reaction_quality` e `report.reaction_quality`:

- **Ripetizione concettuale**: gruppi di reazioni quasi identiche (similarità lessicale ≥ 0,8) e reazioni con la stessa combinazione di temi (prezzo, attesa, prove, scarsità, ingredienti, bisogno). Soglia di segnalazione: gruppo ≥ 50%.
- **Aderenza alla creatività**: la reazione riusa parole del contenuto dell'annuncio. Citare un campo come `evidence` non basta.
- **Numeri inventati**: cifre nella reazione assenti dal contenuto, dalla campagna e dalla fascia d'età. Non rileva numeri scritti a lettere.
- **Coerenza**: azione dichiarata e punteggi (es. `consider_click` con interesse ≤ 1) e, per un caso estremo, profilo.
- **Limite del brief**: quota di reazioni che citano il prezzo quando il prezzo manca. Segnalata come `brief_limit_dominates`, non come scoperta del panel.

Applicati offline alla run Gemini già conclusa (`fa40f012…`): 88% delle reazioni cita il prezzo, solo il 56% riusa contenuto dell'annuncio, nessun numero inventato, nessuna incoerenza di azione. Vengono segnalati `brief_limit_dominates` e `weak_grounding` per entrambe le creatività. Il secondo risultato è un limite del controllo lessicale (parafrasi non rilevate) oltre che un'indicazione sul panel: serve la valutazione umana per distinguere.

**Valutazione umana cieca**: `audience reactions export-rubric RUN_ID --n 60` scrive un CSV con ID anonimi, creatività, profilo e reazione (senza azione dichiarata né ID agente) e la chiave in `validation/rubric/RUN_ID/key.json`. I valutatori compilano `groundedness`, `coherence`, `usefulness` (0–2). `audience reactions score-rubric RUN_ID --ratings a.csv b.csv` calcola medie, kappa pesato lineare tra due valutatori e confronta la valutazione umana con il controllo automatico di aderenza. Nessuna valutazione umana è stata ancora raccolta: `human_validated` resta falso.

## 3 · Pannello rappresentativo (`audience_spec.py`)

Osservato (Eurostat, per paese e fascia d'età):
- mix d'età = popolazione residente 18+ (`demo_pjan`) × partecipazione ai social network (`isoc_ci_ac_i`, `I_IUSNET`);
- quota che ha acquistato online negli ultimi 12 mesi (`isoc_ec_ib20`, `I_BLT12`), campionata come attributo `online_shopper`.

Ipotesi dichiarate, etichettate `assumption` in `profile.provenance`: i sette tratti comportamentali (`Beta(2,2)`) e un effetto piccolo e fisso dell'acquisto online su `trust` e `purchase_need` (±0,08).

Quote d'età risultanti (18-24 … 65+): IT 13,2/18,2/18,0/20,2/15,5/14,8 %; ES 13,1/18,4/19,6/20,9/14,2/13,8 %; FR 14,7/19,3/19,5/17,0/13,3/16,2 %; DE 13,7/22,0/21,2/16,0/14,7/12,5 %. Il tasso di uso dei social per 65+ è quello dei 65-74 anni, applicato a tutti gli over 65: probabilmente sovrastima la fascia più anziana.

Limiti: il mix d'età è degli utenti social residenti, non del pubblico della campagna; Eurostat usa 16–24 per la fascia 18–24 e 65–74 per 65+; reddito, animale domestico, abitudini di cura della pelle e di abbigliamento **non sono osservati** e restano assenti.

Comportamento: con `specs/marginals.json` presente e paese supportato si usa `profiles-v2`; senza il file, o per un paese non coperto, resta `profiles-v1`. Le quote d'età indicate esplicitamente dall'utente nel brief prevalgono su quelle osservate. Il download è esplicito:

```sh
.venv/bin/python -m audience_simulator.cli marginals fetch --countries IT ES FR DE
```

## Pubblico mirato (`profiles-v3-targeted`)

Quando il brief contiene `targeting`, il pannello non è più il pannello generico per fascia d'età: è campionato su chi
l'annuncio raggiungerebbe, con `persona_model.py` (stadio 1 delle persone).

- **Popolazione di base**: 4.000 persone per fascia d'età. Mix per età e acquisto online da Eurostat; tutto il resto
  (nucleo, figli, stato civile, animale, occupazione, reddito, uso di Instagram/Facebook, dispositivo, minuti sui social)
  è un'ipotesi dichiarata (`persona-skeleton-v1`) con probabilità condizionate (età → zona → nucleo → figli → animale).
  I sette tratti restano `Beta(2,2)` ma sono correlati da una copula gaussiana dichiarata e spostati dagli attributi
  (chi ha un cane ha più affinità per il pet food, chi ha basso reddito è più sensibile al prezzo).
- **Consegna, non intento**: ogni persona riceve un peso di consegna da età, genere, zona, dispositivo, placement e
  termini dettagliati. Un termine agisce con `match[valore] / quota_di_base[valore]`, quindi l'interesse «Cani» raggiunge
  circa il 55% di proprietari di cani (ipotesi), non il 100%. Il target ideale (`audience_intent`, `constraints`) non
  filtra la consegna: serve a marcare `in_ideal_target` e a stimare quanta parte del pubblico raggiunto è davvero il bersaglio.
- **Pannello**: per fascia raggiunta, campionamento sistematico pesato su un ordine stratificato; `population_weight` è la
  quota di reach della fascia divisa per le persone scelte. Il forecast usa le quote d'età raggiunte.
- **Audit**: distanza di Gower (minima e media), duplicati, copertura dei valori frequenti, quota effettiva del pool.
  Gli avvisi compaiono nel `targeting_report` del scenario.
- **Non modellati** (registrati e dichiarati nel report): lingue, solo Wi-Fi, orari, giorni, cap di frequenza, pubblici
  personalizzati e lookalike, termini senza `match`, distribuzioni regionali (le regioni sono solo un'etichetta).
- Nessuna di queste probabilità è stata validata sulla consegna reale.

## Schede-persona (`persona-writer-v1`)

Stadio 2 delle persone (`persona_cards.py`): un LLM scrive la scheda di ogni persona del pannello mirato a partire dai
fatti dello scheletro, tradotti in italiano (età, genere, nucleo, figli, animale, occupazione, reddito, piattaforme,
dispositivo, e i tratti come tendenze, non come numeri).

- **Chiamata**: `POST /api/v1/scenarios/{id}/personas` (sincrona) o `SimulationService.write_personas`. Le schede stanno in
  `population.cards`; il report in `population.persona_report`. I tre provider hanno un metodo generico `generate`
  (schema JSON, temperatura 0,9, seed dove l'API lo accetta; Gemini non lo accetta).
- **Lotti**: 8 persone per chiamata, con l'elenco di nomi, mestieri e aperture già usati. Una scheda per riferimento P1…Pn.
- **Validatore deterministico** (`validate_card`): i campi `echo_*` devono ripetere i fatti; animale, figli, nucleo,
  piattaforme usate e occupazione non devono contraddire lo scheletro (con gestione della negazione: «non ha animali»
  non è un animale); niente attributi sensibili, marchi reali, prezzi nei testi, età diversa da quella dello scheletro;
  budget mensile entro un tetto per fascia di reddito.
- **Diversità**: stesso nome, stessa apertura della bio o biografia quasi identica (Jaccard > 0,55) fanno rigenerare.
- **Fallimento**: fino a 3 tentativi per persona; poi scheda `source: "template"` (nome «Persona N», nessun dettaglio
  inventato). Il report conta schede scritte, da cache, in fallback e i motivi di rifiuto.
- **Cache** per scheletro, verticale, paese, versione del writer, provider, modello e digest: la stessa persona vede ogni
  creatività e un errore di quota si riprende senza rifare le schede già scritte.
- Una scheda è un'ipotesi su come potrebbe essere quella persona, non un dato; il report la etichetta `hypothesis`.
  I controlli verificano coerenza con i fatti, non realismo.

## Reazione dell'agente (`agent-reaction-v8`)

Stadio 3 (`reactions.py`, `stimulus_view.py`). Convive con il flusso v7 (`agents.py`), che resta invariato e continua a
servire benchmark e simulazioni esistenti: i due prompt hanno versioni e chiavi di cache distinte.

- **Ruolo**: l'agente è la persona della scheda (nome, fatti non negoziabili, routine, modo di reagire alle pubblicità), non
  un valutatore. Niente JSON numerico di tratti: i tratti arrivano come tendenze in italiano.
- **Stimolo «come visto»** per placement: `al_primo_sguardo` (visual, primi caratteri del testo, titolo o pulsante a seconda
  del placement), `se_ti_fermi_e_leggi` (resto del testo, offerta, prezzo) e `dopo_il_click` (pagina di destinazione, ignota
  prima del click). I caratteri visibili del testo e i pesi dei placement sono ipotesi dichiarate in `stimulus_view.py`.
- **Situazione**: momento, attività, umore, scopo e periodo (Black Friday ecc.) derivati dal seed e dalla persona, uguali per
  tutte le creatività, così il confronto è appaiato. Tre slot di frequenza: `first`, `repeat`, `saturated`, con la memoria
  «l'hai già visto» nel testo, invece di una formula di fatica.
- **Output** (`AgentDecision`): prima impressione in prima persona, dettaglio citato, `read_beyond_glance`, reazione dopo essersi
  fermati, e quattro stime «su 100 volte» (`skip`, `stop`, `engage`, `click`) normalizzate a 100 (si rifiuta chi è lontano più
  di 10 punti), azione se coinvolto, intenzione dopo il click, frizioni, evidence da una enum, incognite. Da qui derivano i
  gate `notice`, `engage` e `click`.
- **Anti-compiacenza**: regole contro il linguaggio da marketing e contro l'invenzione di prezzi o prove; quattro esempi di
  forma da settori diversi (rifiuto, irritazione, interesse, curiosità tiepida) in ordine diverso per ogni persona; nessun
  CTR o valore bersaglio nel prompt.
- **Esecuzione**: `POST /api/v1/scenarios/{id}/reactions` (sincrona, con `slots` e `limit` per una prova ridotta) o
  `SimulationService.run_reactions`. Temperatura 0,7 con seed derivato dall'input; cache per esposizione; una risposta non
  valida si ripete una volta e poi si conta come fallita, mai sostituita.
- **Stato**: ipotesi del modello, non validata (`validated: false`). Non alimenta ancora il motore di simulazione né i risultati:
  è la Fase 5. Il prompt non è stato confrontato con v7 su un modello reale: serve il confronto sullo split dev (Fase 6).

## Motore `agent_native`

`native_engine.py`, richiesto con `mode: "agent_native"` in `POST /api/v1/simulations` (e nel preflight). Richiede un brief con
`targeting`; la modalità storica (`history_forecast`) resta quella di default e non cambia.

Flusso della run: forecast storico come riferimento → schede-persona (scritte e messe in cache se mancano) → una reazione per
persona × creatività × periodo × slot di frequenza → motore.

- **Gate dalle decisioni**: `notice = 1 − skip`, `engage = engage + click`, `click = click`, tutti da `*_per_100`. Nessuna
  riconciliazione sul CTR storico (`reconcile_gates` non è usato).
- **Mix di frequenza**: gli slot si pesano con il cap di frequenza del targeting (k impression: 1ª, 2ª–3ª, 4ª+); senza cap vale
  un mix assunto 45/35/20, dichiarato nel risultato (`slot_mix.info.source`). Gli slot non valutati rinormalizzano il mix.
- **Consegna dal forecast**: impression, spesa e CPM restano quelli del forecast (non dipendono dal pannello). Le quote d'età sono la
  quota di reach del pannello; CTR e click per età sono le decisioni delle persone di quella fascia.
- **Incertezza**: ricampionamento (bootstrap) delle persone del pannello. Non copre la variabilità del modello linguistico, del
  prompt né le ipotesi sul pubblico: il risultato lo dichiara.
- **Riferimento e divergenza**: ogni riga conserva `reference_forecast`; per creatività, `report.native.divergence` segnala se il CTR
  degli agenti è fuori dall'intervallo del forecast o oltre 2× il suo valore. Una divergenza non dice quale dei due sbagli.
- **Segmenti**: per creatività, CTR, notice ed engage per fascia d'età, placement, nucleo, animale, genere, reddito, zona, sistema
  operativo e `in_ideal_target`, con `low_sample` sotto 8 persone.
- **Etichette**: `mode: agent_native`, `quantitative_source: agent_native_decisions`, `validated: false`, dominio non verificato,
  confronto tra creatività `out_of_domain`. Il placement per persona è uno solo (assunzione): le stime per placement sono grezze.
- **Non modellato**: ottimizzazione della piattaforma verso la creatività migliore, aste, orari e giorni, pubblici personalizzati.
  La qualità delle reazioni v8 (`reaction_quality`) non è ancora valutata: è la Fase 6.

## Qualità delle reazioni v8 e confronto dei prompt (Fase 6)

Tutto è descrittivo: segnala decisioni e pannelli da rivedere, non prova somiglianza con persone reali (`human_validated: false`).
Le soglie sono costanti dichiarate nel codice (`decision_quality.THRESHOLDS`), non calibrate; si scelgono solo su dev.

**Controlli sulle decisioni** (`decision_quality.py`, nelle run `agent_native` in `behavior.reaction_quality` e in
`report.reaction_quality`, e in `run_reactions` come `quality`):
- ripetitività delle prime impressioni (concetti e lessico), aderenza all'annuncio visto, numeri inventati rispetto a
  annuncio, scheda e situazione, linguaggio da marketing;
- incoerenze (`read_without_stopping`, `reaction_after_without_stopping`, `clicks_but_hides`,
  `cites_text_not_seen_at_a_glance`);
- **bias di positività**: quota di decisioni con almeno 20 interazioni su 100, mix di azioni positive e negative;
- **dipendenza dal profilo**: eta² di attenzione e click per pet, nucleo, genere, reddito, età, occupazione, zona e routine.
  Con almeno 30 decisioni e nessun attributo oltre l'1% scatta `insensitive_to_profile`;
- sanità sui livelli (avvisi, mai obiettivi): attenzione media fuori da 3–60% o click medio fuori da 0,05–10 su 100.

**Test contro-fattuali** (`counterfactual.py`, `POST /api/v1/scenarios/{id}/quality/counterfactual`): la stessa esposizione si
chiede due volte cambiando una sola cosa.
- persona pertinente o no (animale, routine di cura della pelle) con schede di soli fatti, così nessun testo libero può
  contraddire il cambio; annuncio del brief o di un altro settore; persona benestante e poco attenta al prezzo o con reddito
  basso e molto attenta davanti a un prezzo alto; prima vista o saturazione;
- un **placebo** (solo nome e città scambiati) misura il rumore del modello: un test è `sensitive` solo se almeno il 70% dei
  casi che si muovono va nella direzione attesa, il test binomiale è sotto 0,05 e l'effetto supera il rumore del placebo;
  troppe coppie senza variazione dà `insensitive`, poche coppie `inconclusive`.
- Le direzioni attese sono ipotesi dichiarate. Essere sensibile ai propri fatti non basta per essere realistico: mostra che il
  prompt non ignora la scheda.

**Rubrica cieca** (`GET /api/v1/simulations/{run_id}/rubric`): annuncio visto, fatti della persona e reazione, senza creatività,
modello né segnali automatici; tre dimensioni (realismo, coerenza con la persona, aderenza all'annuncio). La chiave che riporta gli
identificativi ciechi alle esposizioni va tenuta separata dal CSV dato ai valutatori. `score_rubric` calcola accordo tra
valutatori (kappa pesato) e confronta il realismo medio di decisioni segnalate e non segnalate.

**Confronto di prompt** (`prompt_eval.py`): varianti (`v8`, senza esempi, temperatura 0 e 1) o v7 contro v8 sulle stesse esposizioni,
con differenze appaiate e intervallo bootstrap. Rifiuta `split="test"` (PROMISE, regola 1) e accetta solo `dev` o `synthetic`.
Non è stato eseguito su un modello reale: i numeri di v7 contro v8 vanno prodotti prima di dire che uno sia migliore.
Il benchmark B2 con persone e prompt v8 (Fase 8) resta da eseguire su dev.

## Interfaccia (Fase 7)

- **Nuova simulazione**: sezione facoltativa «A chi vuoi arrivare» (`components/targeting-form.tsx`). Un campo di testo libero
  («chi ha un cane e vive da solo») mostra subito «Come l'ho capito»: i vincoli riconosciuti, ciò che non è stato capito, gli
  avvisi e, per gli attributi che Ads Manager non offre, i termini vicini da aggiungere con un clic e la precisione attesa
  (dichiarata ipotesi). Sotto, «Impostazioni come in Ads Manager»: età, genere, zona, regioni, dispositivi, posizionamenti
  (automatici o i 12 manuali), targeting dettagliato con includi, restringi, escludi, Advantage+ audience, limite di frequenza e,
  in un gruppo a parte, le impostazioni registrate ma senza effetto sul pubblico (obiettivo, offerta, lingue, Wi-Fi, giorni,
  orari, pubblici salvati). Il catalogo viene da `GET /api/v1/targeting/catalog`.
- **Come simulare**: «Stima dai dati storici» (invariata) o «Persone simulate · sperimentale», attiva solo con un pubblico
  descritto; mostra il numero minimo di reazioni, un avviso di non validazione e la scelta di considerare o no le ripetizioni.
  Senza pubblico il brief non invia `targeting` e il comportamento di prima non cambia.
- **Risultati** (`native-panels.tsx`, `persona-gallery.tsx`): etichetta «Persone simulate · non validato» e avviso; «Chi raggiunge
  davvero» (quota del target ideale tra chi vedrebbe l'annuncio contro la popolazione di partenza, età, avvisi, controllo del
  pannello, anche per le run storiche con targeting); «Persone simulate e dati storici» con la divergenza; «Chi reagisce di più» per
  età, placement, nucleo, animale, genere, reddito, zona, telefono e target ideale, con i gruppi sotto 8 persone segnati;
  la galleria delle persone con scheda, reazione in prima persona e ripartizione su 100 volte; «Quanto sono credibili le
  reazioni» con i segnali dei controlli automatici e il download della rubrica cieca e della sua chiave (due file separati).
