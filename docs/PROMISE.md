# Promessa verificabile e pre-registrazione

**Stato: bozza v1, soglie da confermare prima di toccare il test.** Nessun dato di test è stato ancora costruito o letto. Una volta confermato, questo file viene committato e il suo hash entra nel manifest del benchmark (fase 2): modificarlo dopo aver visto il test invalida la verifica.

## Promessa

> Dato un brief con 2–4 creatività nello stesso dominio, il motore indica quale ha il CTR più alto, oppure dichiara «differenza non risolvibile», oppure «campagna fuori dal dominio verificato».

È l'unica promessa che il prodotto può fare. Non promette: CTR assoluto, CPM, spesa, clic totali, acquisti, ROAS, opinioni o quote per età. Queste uscite restano ipotesi da scenario (stato attuale in `docs/MVP_VALIDATION.md`) finché non hanno un proprio benchmark: ognuna richiede dati e verifiche diverse.

**Dominio** = (settore, paese, obiettivo, placement, lingua). Un dominio è «verificato» solo se è nel registro `backend/audience_simulator/domain.py` (`VERIFIED_DOMAINS`), che oggi è **vuoto**, e solo per la coppia esatta (versione del prompt, modello) con cui il benchmark è passato. Cambiare prompt o modello riporta lo stato a «non verificato per questa configurazione».

## Unità di analisi

Una **coppia** = due creatività della stessa campagna o dello stesso esperimento, con impression e link click osservati per entrambe. Le coppie della stessa campagna non sono indipendenti: le stime e gli intervalli usano il bootstrap a cluster sulle campagne.

Una coppia è **risolta** quando l'intervallo di Newcombe–Wilson al 95% della differenza di CTR osservata esclude zero. Le coppie non risolte non entrano nelle metriche primarie, ma vengono riportate.

## Metriche

**Primarie** (sul solo insieme di test, solo coppie risolte)
1. **Accuratezza di ranking**: quota di coppie in cui la creatività indicata dal motore è quella con CTR osservato maggiore.
2. **Tasso di falsi vincitori**: tra le coppie in cui il motore dichiara un vincitore, quota in cui il vincitore dichiarato ha CTR osservato significativamente inferiore.

**Secondarie**: errore medio di CTR (punti percentuali, ponderato per impression); copertura degli intervalli dichiarati; log-loss e Brier di P(A > B); quota di coppie dichiarate «non risolvibili» e accuratezza sulle sole coppie dichiarate risolvibili.

## Confronti obbligatori

- **B0**: baseline senza LLM (base rate e feature semplici del testo).
- **B1**: LLM senza profili sintetici.
- **B2**: pannello completo.

Il pannello conta come utile solo se supera **sia B0 sia B1** (test di permutazione appaiato per campagna). Un pannello che non li batte non viene promosso e il prodotto resta un laboratorio di scenari.

## Soglie di successo proposte (da confermare)

Tutte sul test escluso, con intervallo di confidenza bootstrap a cluster al 95%:

| Criterio | Soglia |
|---|---|
| Accuratezza di ranking B2 | stima puntuale ≥ 65% **e** estremo inferiore dell'intervallo > 50% |
| B2 vs B0 e B2 vs B1 | differenza di accuratezza > 0, p < 0,05 (permutazione appaiata) |
| Falsi vincitori B2 | ≤ 25% dei vincitori dichiarati, e non peggiore di B0 |
| Copertura intervalli dichiarati al 90% | tra 85% e 95% |

Le soglie di accuratezza e falsi vincitori sono scelte per essere utili a una decisione di budget tra due creatività; il 25% e il 65% sono proposte da validare con chi userà il prodotto. Se non vengono rivedute, restano questi valori.

## Analisi di potenza

Test binomiale esatto unilaterale, ipotesi nulla 50% (esito casuale), α = 0,05, potenza 80%:

| Accuratezza vera | Coppie risolte indipendenti necessarie |
|---|---:|
| 70% | 37 |
| 65% | 69 |
| 60% | 158 |

La soglia minima per dichiarare un risultato è quindi **69 coppie risolte nel test**, assumendo coppie indipendenti. Con coppie correlate dentro la stessa campagna servono più coppie, o più campagne. Se il corpus non lo consente, l'esito corretto è «non certificabile», non una soglia abbassata dopo il fatto.

## Sottocampione del test e definizioni operative (fase 2)

- **Sottocampione finale**: 60 campagne del test (confermato dall'utente il 14 novembre 2026), scelte ordinando gli ID per hash salato (`final-sample-v1`), mai per esiti. Aspettativa: ~93 coppie risolte, sopra il minimo di 69. Se le coppie risolte effettive fossero meno di 69, l'esito è «non certificabile», non una soglia più bassa.
- **Congelamento**: `audience verify freeze --config FILE` registra configurazione, ID del campione, hash del test e hash di questo file. Modificare questo file dopo il congelamento blocca il test.
- **Accuratezza**: una coppia non dichiarata (differenza dei punteggi entro il margine) conta come non corretta; si riporta anche l'accuratezza sulle sole coppie dichiarate. **Falsi vincitori** = 1 − accuratezza sulle dichiarate.
- **B0** = regressione logistica a coppie su sette feature del testo (lunghezza, parole, cifre, `?`, `!`, maiuscole, inizio numerico), addestrata sulle coppie risolte di sviluppo. **B1** e **B2** entrano come file di punteggi `validation/scores/<sistema>-<split>.json`.
- **Statistiche**: bootstrap a cluster sulle campagne (2000 ricampionamenti) e test di permutazione appaiato con inversione dei segni per campagna, unilaterale.
- **Una sola valutazione finale** per configurazione congelata. Ogni tentativo, anche rifiutato, è registrato in `validation/test-evaluations.json`.
- **Primo riferimento su sviluppo (14 novembre 2026)**: B0 raggiunge 59,6% di accuratezza (IC95% 56,2–63,2) su 1.159 coppie risolte, in validazione incrociata per campagna. Non è la soglia del test; mostra che il pannello deve battere una baseline già sopra il caso. Il pannello non può dichiarare un risultato utile con meno.

## Regole di conduzione

1. Prompt, modello, parametri e soglie si scelgono **solo** sulla parte `dev`. Il test si valuta una sola volta in modalità finale (fase 6).
2. Nessun esito osservato entra in un prompt o in un payload agli agenti.
3. I risultati negativi restano nel rapporto. Non si cambia criterio dopo aver visto i risultati.
4. Qualsiasi modifica a prompt, modello o profili ripete il benchmark prima di rimettere il dominio nel registro.
5. Limiti dichiarati: le fonti pubbliche possono essere state viste dal modello in addestramento; le campagne pubbliche non sono ecommerce IT/ES/FR/DE. Gli esiti valgono solo per il dominio del benchmark.

## Modalità `agent_native` (dichiarata il 14 novembre 2026, prima di qualsiasi esito)

- Le decisioni delle persone simulate (`agent-reaction-v8`, schede `persona-writer-v1`, pubblico `persona-skeleton-v1`) sono la stima del CTR; il forecast storico resta come riferimento con un flag di divergenza.
- Questa modalità **non è coperta** dal benchmark pre-registrato sopra: nessun dominio è verificato per essa (`VERIFIED_DOMAINS` vuoto), quindi ogni run è etichettata «non validata» e il confronto tra creatività resta `out_of_domain`.
- Per entrare nel registro dei domini verificati servirà un B2 con persone e prompt v8, valutato come tutte le altre configurazioni: scelta di prompt e parametri solo su `dev`, una sola valutazione finale sul test congelato, risultati negativi inclusi. Il test non è stato toccato per questa modalità.
- Non si dichiara alcuna soglia di accuratezza per `agent_native` prima di aver visto i controlli di qualità della Fase 6 su `dev`.
