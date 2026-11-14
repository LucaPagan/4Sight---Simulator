// Numero di consumatori sintetici, affidabilità e legenda dei termini del report.
// Parole da marketer: nessun gergo statistico a vista.

export const MIN_AGENTS = 30;
export const MAX_AGENTS = 1000;
export const DEFAULT_AGENTS = 120;
export const RECOMMENDED_AGENTS = 600;
const BANDS = 6;

export const AGENT_PRESETS: {value: number; label: string; hint: string}[] = [
  {value: 60, label: "Veloce", hint: "Un primo sguardo, in meno tempo."},
  {value: DEFAULT_AGENTS, label: "Standard", hint: "Il punto di partenza per quasi tutti i test."},
  {value: RECOMMENDED_AGENTS, label: "Consigliato", hint: "Il miglior equilibrio tra solidità e tempi."},
  {value: MAX_AGENTS, label: "Massimo", hint: "Il massimo dettaglio, con tempi molto più lunghi."}
];

export function clampAgents(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_AGENTS;
  return Math.min(MAX_AGENTS, Math.max(MIN_AGENTS, Math.round(value)));
}

export const perBand = (agents: number) => Math.round(agents / BANDS);

// L'incertezza della lettura per età cala con la radice del numero di agenti per fascia.
// Misurata sulle valutazioni reali del modello: scarto tipico ≈ 0,13 su una scala da -0,75 a +0,5,
// quindi errore ≈ 0,13 / √(agenti per fascia): 0,041 con 60 agenti, 0,029 con 120, 0,013 con 600, 0,010 con 1000.
// Il CTR e il costo attesi (e quindi la creatività vincente) vengono dai dati storici e NON cambiano.
export function noiseVersusStandard(agents: number): number {
  return Math.sqrt(DEFAULT_AGENTS / agents) - 1;
}

export type Reliability = {level: "Indicativa" | "Buona" | "Alta" | "Molto alta"; summary: string; change: string};

export function agentReliability(agents: number): Reliability {
  const delta = Math.round(noiseVersusStandard(agents) * 100);
  const change = delta === 0 ? "Come il panel standard." : delta > 0 ? `Le stime per età oscillano il ${delta}% in più del panel standard.` : `Le stime per età oscillano il ${-delta}% in meno del panel standard.`;
  if (agents < 90) return {level: "Indicativa", change, summary: "Va bene per un primo sguardo: le differenze tra fasce d'età possono cambiare ripetendo il test."};
  if (agents < 240) return {level: "Buona", change, summary: "Adatta alla maggior parte dei test. Le differenze piccole tra fasce d'età vanno lette con cautela."};
  if (agents < 600) return {level: "Alta", change, summary: "La lettura per età è stabile e le reazioni dei consumatori sono più varie."};
  return {level: "Molto alta", change, summary: agents <= 700 ? "È il punto di equilibrio: oltre questo numero il miglioramento è piccolo e i tempi crescono molto." : "Il miglioramento rispetto a 600 è ridotto (circa il 22% di oscillazione in meno) e richiede molto più tempo."};
}

// Cosa cambia e cosa no con il numero di agenti: la stessa spiegazione in modulo e nei risultati.
export const AGENTS_NOTE = {
  same: "Non cambiano il CTR atteso, il costo e la creatività consigliata: vengono dai dati storici.",
  changes: "Cambiano la stabilità delle differenze per età, la varietà delle reazioni e il confronto con il panel.",
  limit: "Gli agenti sono lo stesso modello AI con profili diversi, non persone indipendenti: oltre qualche centinaio il guadagno è piccolo."
};

export function evaluationsFor(agents: number, creatives: number): number {
  return agents * creatives;
}

export const OBJECTIVE_LABEL: Record<string, string> = {vendite: "Vendite", traffico: "Traffico"};
export const COUNTRY_LABEL: Record<string, string> = {IT: "Italia", ES: "Spagna", FR: "Francia", DE: "Germania"};
export const PLACEMENT_LABEL: Record<string, string> = {instagram_feed: "Feed di Instagram", facebook_feed: "Feed di Facebook", instagram_stories: "Storie di Instagram"};
export const FORMAT_LABEL: Record<string, string> = {immagine: "Immagine", video: "Video", carosello: "Carosello"};
export const TASK_LABEL: Record<string, string> = {casual_scrolling: "Scorre senza meta", product_research: "Cerca un prodotto", comparison_shopping: "Confronta le offerte"};

// Legenda dei termini che compaiono nel report, in ordine di apparizione.
export const GLOSSARY: {term: string; meaning: string}[] = [
  {term: "CTR atteso", meaning: "Su 100 volte che l'annuncio viene visto, quante persone cliccano. Più è alto, meglio funziona."},
  {term: "Costo per 1.000 visualizzazioni", meaning: "Quanto paghi ogni 1.000 volte che l'annuncio compare (in gergo CPM). Più è basso, meglio è."},
  {term: "Clic attesi", meaning: "Quanti clic aspettarti con il budget e il periodo scelti."},
  {term: "Spesa attesa", meaning: "La parte di budget che verrà davvero spesa."},
  {term: "Intervallo", meaning: "Il minimo e il massimo plausibili: più è stretto, più la stima è stabile."},
  {term: "Fascia d'età", meaning: "Un gruppo di età del pubblico. Le differenze tra fasce sono ipotesi, non dati osservati."},
  {term: "Consumatori sintetici", meaning: "Persone simulate dall'AI che valutano gli annunci. Non sono persone reali."},
  {term: "Stima preliminare", meaning: "Calcolata dai dati storici prima che tutti i consumatori abbiano risposto."}
];
