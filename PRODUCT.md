# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Marketer non tecnici che preparano campagne Meta (Instagram e Facebook feed) per piccoli brand e e-commerce: beauty e skincare, pet, abbigliamento. Aprono l'app per scegliere tra due o più creatività prima di spendere budget reale. Non conoscono modelli, prior, seed o policy e non devono doverli conoscere. Un secondo pubblico, secondario, è chi guarda la demo dell'hackathon e deve capire il prodotto in pochi secondi.

## Product Purpose

Audience Simulator è un laboratorio locale per testare campagne Meta prima di lanciarle. L'utente inserisce prodotto, creatività, pubblico, periodo e budget; 120 consumatori sintetici valutano individualmente gli annunci con un modello locale (Ollama) o cloud (Gemini, Cloudflare Workers AI). Il report mostra quale creatività funziona meglio, con CTR e CPM attesi, le reazioni del panel e le ipotesi per fascia d'età. Il successo è: un marketer sceglie la creatività vincente in pochi minuti e capisce quanto fidarsi del risultato.

## Positioning

Non è una validazione su persone reali e non esegue campagne né spese su Meta: è una simulazione con un pubblico sintetico; i numeri vengono da una baseline storica sul kit, non dal panel. Nessun dominio è ancora verificato in modo indipendente (`docs/PROMISE.md`). Questa onestà (cosa è dato, cosa è stima, cosa è ipotesi) è parte del prodotto.

## Operating Context

Uso locale su un computer, un utente alla volta, senza autenticazione. Il motore AI può essere locale o cloud e si sceglie per ogni test. Una simulazione richiede minuti: l'app mostra l'avanzamento e permette di riprendere le valutazioni mancanti. I dati del kit Wevion sono simulati e coprono tre settori.

## Capabilities and Constraints

- Percorso: Nuova simulazione (campagna e creatività, pubblico, avvio) → risultati → elenco simulazioni.
- Funzioni tecniche mantenute ma fuori dal percorso principale, sotto Impostazioni: scelta e prova del motore AI, chiavi cloud, backtest e export delle previsioni del kit, import dei CSV, fonti e metodo.
- Nessun contratto API o funzione backend cambia con il redesign; il proxy `/api/v1` resta invariato.
- Interfaccia in italiano. Stack: Next.js 16, React 19, CSS globale a mano, recharts, lucide-react.
- Il pubblico per età è un'ipotesi (nessuna etichetta demografica nei dati); il CTR e il CPM derivano dalla baseline storica del kit simulato, non da persone reali, e non sono ancora verificati su campagne escluse.

## Brand Commitments

Nome del prodotto: Audience Simulator. Copy in italiano, tono diretto e sobrio. Nessun impegno su logo, palette o font: il look attuale (verde salvia) è evidenza, non vincolo.

## Evidence on Hand

Dati del kit in `data/` (13 CSV simulati, tre asset creativi in `data/asset_creativi/`), registro di evidenze comportamentali (`/evidence`), run di esempio generate dal backend. Non esistono loghi, testimonianze, clienti o benchmark da citare: non inventarli.

## Product Principles

1. Un compito per schermata: un solo passo successivo evidente.
2. Il default funziona, l'avanzato si apre solo se serve (progressive disclosure).
3. Parole da marketer, non da data scientist: nessun gergo a vista fuori da Impostazioni.
4. Onestà senza rumore: una sola nota chiara "simulazione, non persone reali", al posto di avvisi ripetuti.
5. Il risultato è una decisione (quale creatività vince e di quanto), poi i dettagli.

## Accessibility & Inclusion

Obiettivo WCAG AA: contrasto, focus visibile, uso da tastiera, testo di corpo ≥ 14 px anche su mobile, rispetto di `prefers-reduced-motion`. Lingua italiana coerente.
