---
version: 1
slug: "frontend-app-page-tsx"
primary_target: "frontend/app/page.tsx"
related_targets: ["frontend/app/globals.css"]
---

# Surface brief: app Audience Simulator (frontend)

Scope: tutta l'interfaccia web (nuova simulazione, risultati, elenco simulazioni, impostazioni). Modalità: **Operate**.

Visitatore: marketer non tecnico che confronta creatività Meta prima di spendere. Compito: descrivere la campagna, lanciare la simulazione, leggere quale creatività vince e quanto fidarsi. Frequenza: alcune volte a settimana, sessioni brevi, scrivania e luce diurna da ufficio (tema chiaro). Vincoli: nessun gergo fuori da Impostazioni, WCAG AA, testo ≥14 px, nessun contratto API cambia.

## Direction contract

THESIS: un gestionale che parla come una pubblicità Olivetti: campi piatti di blu profondo, geometria di base, un solo rosso per l'azione successiva. Rifiuta il gestionale grigio con un accento e le schede tutte uguali con icona.

OWN-WORLD: ground #F3F5F7, ink #1B1D21, blu Olivetti #14357A pieno per la barra laterale, i titoli e gli stati selezionati, rosso #E4352B riservato al pulsante primario, agli errori e alla voce attiva. Ogni creatività ha un segno geometrico fisso, usato ovunque (form, grafico, verdetto): A cerchio blu, B quadrato ambra #F0A300, C triangolo verde #2E8B6A, D rombo nero. Sans geometrico caricato in locale (Jost), cifre tabulari per CTR, CPM e budget. Filetti da 1 px, niente ombre decorative, raggi 4-6 px.

STORY: il marketer capisce a colpo d'occhio dove si trova (4 voci, passo 1 di 3), compila solo l'essenziale, vede cosa verrà simulato e per quanto, e ottiene un verdetto in una frase: quale creatività vince e di quanto.

FIRST VIEWPORT: barra blu piena di 240 px a sinistra con wordmark e 4 voci (Nuova simulazione, Risultati, Simulazioni, Impostazioni); al centro lo stepper a 3 passi, titolo 44 px blu, modulo con campi essenziali e due schede creatività A/B con il loro segno; colonna destra di 300 px con tre cifre (creatività, consumatori, attesa) e un unico pulsante rosso «Continua al pubblico».

FORM: Pubblicità Olivetti, card IMPECCABLE'S PICK; seed: seed:345a0153e4874585.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Segni distintivi da non perdere

Segnale unico: i segni A/B/C/D coerenti tra form, grafico, verdetto e elenco. Nessun eyebrow sopra i titoli, nessun bordo colorato laterale >1px, nessuna scheda dentro una scheda.
