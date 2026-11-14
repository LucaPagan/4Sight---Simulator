# Corpus di campagne reali confrontabili

Stato: 14 novembre 2026. Discovery chiusa e corpus preparato con `audience corpus prepare --download`, dopo il tuo consenso al download. Checksum SHA-256 verificati. Risultati nella sezione «Esito della preparazione».

Criteri minimi (dal piano): testo creativo originale; impression e link click per variante; varianti della stessa campagna o esperimento, nello stesso periodo; licenza che consente l'uso; abbastanza unità indipendenti per la potenza fissata in `docs/PROMISE.md` (**69 coppie risolte nel test**).

## Fonti valutate

| Fonte | Esito | Motivo |
|---|---|---|
| Upworthy Research Archive, parte *exploratory* | **Accettata come corpus principale** (dominio proxy) | 4.873 test, 22.666 pacchetti con titolo, impression e clic; assegnazione casuale entro il test; licenza CC BY 4.0 secondo OSF. **Non sono annunci**: titoli di news USA 2013–2015. |
| GWWC Giving Guide 2021 (repo EAMT, commit fissato) | **Accettata come smoke test pubblicitario**, non conta per la potenza | Vero annuncio Facebook con testi e clic, ma una sola campagna di beneficenza: poche unità indipendenti, consegna ottimizzata da Meta, licenza non specificata (niente redistribuzione). |
| Upworthy *confirmatory* e *holdout* | **Esclusi** | La pagina del progetto dice che il set confirmatory viene condiviso con ricercatori con piano d'analisi sottoposto a revisione. Anche se OSF elenca i file, non ho verificato di averne il diritto d'uso. Da chiedere agli autori prima di qualsiasi uso. |
| Meta Ad Targeting dataset (FORT) | **Scartata** | Solo annunci politici/sociali, accesso su domanda, nessun CTR per variante. |
| Meta Ad Library | **Scartata** | Impression a fasce, nessun link click. |
| Report di benchmark di settore | **Scartati** | Analisi aggregate, non dati per variante. |

Nessuna fonte pubblica trovata contiene annunci ecommerce con testo, impression e clic per variante.

## Conseguenza per la promessa

Il corpus principale valida un **meccanismo**: ordinare varianti di testo per CTR. Lo fa nel dominio `news_headline`, inglese, USA. Non valida annunci Meta ecommerce IT/ES/FR/DE. Quindi:

- il registro `VERIFIED_DOMAINS` potrà contenere al massimo il dominio del benchmark (titoli di news), mai skincare, pet o abbigliamento;
- per gli annunci ecommerce il prodotto continua a dichiarare «fuori dal dominio verificato» finché non arrivano dati reali di quel dominio.

## Limiti noti del corpus Upworthy

1. Ogni pacchetto è titolo **più immagine**; le immagini non sono disponibili e variano tra i pacchetti. La differenza di CTR non è attribuibile al solo titolo.
2. Nessun prezzo, offerta, CTA o landing page: lo stimolo è solo il titolo.
3. Il periodo 25 giugno 2013 – 10 gennaio 2014 ha problemi di randomizzazione. Il file *exploratory* **non contiene** la colonna `problem` descritta dagli autori, quindi l'esclusione è per data di creazione (`created_at`): questi test sono esclusi. Gli autori sconsigliano il loro uso confirmatory.
4. Le fonti pubbliche possono essere state viste dal modello in addestramento: è un rischio di contaminazione, da controllare con titoli parafrasati (fase 6).
5. Gli autori chiedono di essere contattati prima di unire i dati con dati scrapati dal web: non lo facciamo.
6. Gli accordi di utilizzo tra Good/Upworthy e Cornell non sono noti: usiamo solo la parte pubblica *exploratory* e citiamo Matias, Munger, Le Quere, Ebersole (2021), *Scientific Data*, doi 10.1038/s41597-021-00934-7.

## Regole di costruzione (codice: `backend/audience_simulator/corpus.py`)

- Unità: un test (Upworthy) o una coppia campagna/annuncio (GWWC) = una **campagna**; le coppie sono le combinazioni delle sue varianti.
- Esclusioni, tutte contate nel rapporto e nessuna basata sugli esiti: test nella finestra di randomizzazione (o con `problem` > 0 se la colonna esiste); varianti con titolo duplicato nello stesso test (non attribuibili al testo); meno di due varianti distinte; più di quattro varianti; qualunque variante con meno di 500 impression; clic mancanti; per GWWC anche testi mancanti o duplicati nello stesso annuncio.
- Conteggi impossibili (clic > impression, negativi, frazionari) fanno fallire la preparazione.
- Gli input (`ComparableCampaign.inputs()`) non contengono impression, clic, spesa, flag `winner` o colonne non mostrate agli utenti (`excerpt`, `lede`, `share_text`).
- L'ordine delle varianti è deterministico dall'hash del testo, mai dagli esiti.
- **Split** per campagna, mai per riga: `test_fraction` 0,3, hash con sale `corpus-split-v1`. Un test che condivide un testo normalizzato con una campagna di sviluppo viene scartato dal test e riportato nel manifest.
- Il manifest registra gli hash di input di `dev` e `test` e l'hash delle osservazioni di test. Gli input e gli esiti del test sono scritti in file separati (`corpus/test/inputs.json`, `corpus/test/observations.json`).
- Il rapporto di `prepare` riporta quante coppie del test sono **risolte** (intervallo di Newcombe–Wilson al 95% che esclude zero). È un controllo di fattibilità sul numero minimo (69), non un'informazione per scegliere prompt o modelli.

## Esito della preparazione (14 novembre 2026)

Upworthy exploratory: 22.666 pacchetti, 4.873 test. Dopo i criteri sopra restano **1.051 campagne**. Esclusioni: 1.050 nella finestra di randomizzazione, 1.982 con meno di due titoli distinti (molti test variano solo l'immagine), 790 con più di quattro varianti, 0 per impression basse.

| Insieme | Campagne | Coppie | Coppie risolte |
|---|---:|---:|---:|
| Sviluppo | 726 | 3.904 | non calcolate |
| Test | 306 | 1.568 | 474 (in 193 campagne) |
| GWWC (smoke, non diviso) | 23 | 221 | non usate per la potenza |

19 campagne del test sono state scartate perché condividono un testo con lo sviluppo. Hash di test: `be4d324e…988995ef` (completo in `artifacts/corpus/split-manifest.json`).

**Fattibilità statistica: soddisfatta.** 474 coppie risolte contro un minimo di 69. Le coppie dentro la stessa campagna sono correlate: per questo le stime usano il bootstrap a cluster (193 campagne con almeno una coppia risolta). Il conteggio è un aggregato e non è stato usato per scegliere nulla.

**Costo LLM: non soddisfatto con il test completo.** Il test ha 1.122 varianti. Con 30 profili per variante sono ~33.700 chiamate, circa 56 ore a 10 richieste al minuto. Per la fase 6 occorre un **sottocampione del test scelto da hash, indipendente dagli esiti** (ad esempio 60 campagne, ~93 coppie risolte attese). La regola va fissata e committata prima di eseguire il test.

## Come preparare il corpus

Il download è esplicito e verifica lo SHA-256 fissato:

| File | Fonte | Dimensione | SHA-256 fissato |
|---|---|---|---|
| `upworthy-archive-exploratory-packages-03.12.2020.csv` | OSF `jd64p`, https://osf.io/download/3vqmp/ | ~14,3 MB | `8368313b060f4015a0c6fb34e6d788163cee29554144aba9390b14922eb9d8ce` |
| `gg_campaign_by_ad_by_text.csv` | repo EAMT, commit `5c97d53…` | ~108 kB | già in `retrospective.py` |

```sh
.venv/bin/python -m audience_simulator.cli corpus prepare --download
# oppure, con file già scaricati:
.venv/bin/python -m audience_simulator.cli corpus prepare --upworthy-file PATH [--gwwc-file PATH]
```

I file restano in `artifacts/` (non versionato): la licenza del dataset GWWC non consente la redistribuzione.

## Decisione go/no-go (a valle di `prepare`)

Se le coppie risolte nel test sono **meno di 69**, la promessa non è certificabile con questo corpus e non si abbassa la soglia. In quel caso: si amplia il corpus (ad esempio chiedendo agli autori l'accesso al set confirmatory) oppure si dichiara l'esito «non certificabile».
