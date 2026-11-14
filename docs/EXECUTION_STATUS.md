# Stato dell'esecuzione

## Implementato e sottoposto a test automatici

Audit CSV offline e manifest, import SQLAlchemy transazionale, feature in-time, baseline CTR/GLM con scelta su validation e calibrazione su finestre nel training, CPM/delivery, forecast699 e4194 fasce, MonteCarlo, prior e riconciliazione età,120profili,clientOllamaJSON,policy cache individuali,gate/memoria/A-B,job atomici/ripresa,API/export/report,UI brief/pubblico/creatività/risultati/storico/fonti/validation,Compose e CI.

Verifiche intermedie:32testPython passati,mypy e buildNext passati. Benchmark hardware reale iniziato:Qwen3.5-9B ha prodotto risposte non conformi; nessuna idoneità dichiarata. In corso analisi prompt/runtime e confronto conMinistral.

## Verifiche ancora richieste

- Benchmark completo e rubrica dei modelli locali; scegliere modello realmente conforme.
- Run reale completa120agenti×2creative e verifica esportazioni.
- Revisione indipendente e correzione rilievi.
- Test Compose/PostgreSQL/RQ/S3.
- Schema OpenAPI aggiornato, documentazione metriche e stato finale.
- Browser integrato:accesso a127.0.0.1:3000 rifiutato dall'utente. Nessuna ulteriore verifica browser verrà tentata senza nuova autorizzazione. Test precedenti:mobilepass;desktoperroreselector poi corretto,nonriverificato.

## Limiti scientifici correnti

Il primo GLM era peggiore dello smoothing. Il registry ora sceglie il candidato migliore;coverageCTR ancora insufficiente,quindiunvalidated. Nessuno score futuro o per età. AblationL L M/panel non ancora eseguita e non rivendicata. L'export699 è baselinepreliminary,nonunpanelLLMcompleto.
