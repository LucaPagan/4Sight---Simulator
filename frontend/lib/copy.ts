import type {Run} from "./types";

// Un solo posto per le parole mostrate agli utenti: nessun gergo tecnico fuori da Impostazioni.

export const COMPLETION_LABEL: Record<string, string> = {
  complete: "Completa",
  partial: "Parziale",
  preliminary: "Preliminare"
};

export const STATUS_LABEL: Record<string, string> = {
  queued: "In coda",
  running: "In corso",
  waiting_for_runtime: "In attesa del modello",
  waiting_for_capacity: "In attesa della quota",
  failed: "Interrotta",
  canceled: "Annullata",
  cancelled: "Annullata",
  succeeded: "Completata",
  completed: "Completata"
};

export const PROVIDER_LABEL: Record<string, string> = {
  ollama: "Modello locale",
  gemini: "Google Gemini",
  cloudflare: "Cloudflare"
};

export const SENSITIVITY: {id: string; label: string; hint: string}[] = [
  {id: "conservative", label: "Cautela", hint: "Parti soprattutto dai dati storici."},
  {id: "central", label: "Equilibrato", hint: "Il caso di partenza, per quasi tutti i test."},
  {id: "exploratory", label: "Esplorativo", hint: "Dà più spazio alle ipotesi sul pubblico, per provare scenari estremi."}
];

export const VERTICALS: Record<string, string> = {
  beauty_skincare: "Beauty e skincare",
  pet_ecommerce: "Pet e-commerce",
  abbigliamento: "Abbigliamento"
};

export const LEVERS: Record<string, string> = {
  value: "Valore",
  scarcity: "Scarsità",
  urgency: "Urgenza",
  black_friday: "Black Friday"
};

export const SIMULATION_NOTE = "Simulazione con un pubblico sintetico, non persone reali. Nessuna campagna viene pubblicata.";

export function runLabel(run: Run, names: Record<string, string>): string {
  const name = names[run.id];
  if (name) return name;
  const when = run.created_at ? new Intl.DateTimeFormat("it-IT", {day: "numeric", month: "short"}).format(new Date(run.created_at)) : "";
  return when ? `Simulazione del ${when}` : "Simulazione";
}

export function runState(run: Run): {label: string; tone: "ok" | "wait" | "bad"} {
  if (["failed", "canceled", "cancelled"].includes(run.status)) return {label: STATUS_LABEL[run.status] || "Interrotta", tone: "bad"};
  if (run.completion_status === "complete") return {label: "Completa", tone: "ok"};
  if (["queued", "running"].includes(run.status)) return {label: STATUS_LABEL[run.status], tone: "wait"};
  return {label: STATUS_LABEL[run.status] || COMPLETION_LABEL[run.completion_status] || "In corso", tone: "wait"};
}

export function engineLabel(run: {provider?: string; requested_model?: string | null; model_name?: string | null}): string {
  const base = PROVIDER_LABEL[run.provider || "ollama"] || "Modello locale";
  return base;
}

export const OUT_OF_DOMAIN = "Questa campagna è fuori dal dominio verificato: l'indicazione è un'ipotesi del modello, non una previsione verificata.";

export const TRUST = {
  preliminary: "Stima preliminare: aspetta che la simulazione sia completa prima di decidere.",
  strong: "Differenza netta: puoi fidarti di questa indicazione.",
  medium: "Differenza media: è un'indicazione, non una certezza.",
  weak: "Differenza piccola: considerala solo un'indicazione.",
  unknown: "Confronto non ancora verificato: considera il risultato indicativo."
};

// Pubblico e persone simulate
export const MODE_LABEL: Record<string, string> = {
  history_forecast: "Stima dai dati storici",
  agent_native: "Persone simulate"
};
export const NATIVE_BADGE = "Persone simulate · non validato";
export const NATIVE_WARNING = "Il CTR viene dalle decisioni di persone simulate da un modello linguistico. Nessuna campagna reale lo ha confermato: usalo per confrontare idee, non come previsione.";

export const PHASE_LABEL: Record<string, string> = {
  baseline: "Calcolo il riferimento storico",
  personas: "Scrivo le schede delle persone",
  agents: "Le persone reagiscono all'annuncio",
  behavior: "Metto insieme i risultati"
};

export const GENDER: Record<string, string> = {all: "Tutti", women: "Donne", men: "Uomini"};
export const URBANICITY: Record<string, string> = {any: "Ovunque", urban: "Città", suburban: "Periferia e provincia", rural: "Campagna"};
export const DEVICES: Record<string, string> = {ios: "iPhone e iPad", android: "Android", desktop: "Computer"};
export const TERM_MODE: Record<string, string> = {include: "Includi", narrow: "Restringi a chi ha anche", exclude: "Escludi"};
export const TERM_KIND: Record<string, string> = {interest: "Interessi", behavior: "Comportamenti", demographic: "Dati demografici"};
export const OPTIMIZATION: Record<string, string> = {link_clicks: "Clic sul link", landing_page_views: "Visualizzazioni della pagina", conversions: "Conversioni", reach: "Copertura", impressions: "Impression", leads: "Contatti"};
export const BID: Record<string, string> = {lowest_cost: "Costo più basso", cost_cap: "Tetto di costo", bid_cap: "Tetto di offerta", roas_goal: "Obiettivo di ROAS"};
export const WEEKDAYS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
export const CUSTOM_KIND: Record<string, string> = {custom: "Pubblico personalizzato", lookalike: "Lookalike", page_fans: "Chi segue la pagina"};

export const VALUE_LABEL: Record<string, Record<string, string>> = {
  household: {alone: "vive da solo", couple: "vive in coppia", family: "vive con la famiglia", shared: "vive in casa condivisa"},
  has_children: {yes: "ha figli", no: "non ha figli"},
  pet_species: {dog: "ha un cane", cat: "ha un gatto", other: "ha un altro animale", none: "non ha animali"},
  relationship_status: {single: "è single", partnered: "ha una relazione", married: "è sposato/a"},
  urbanicity: {urban: "vive in città", suburban: "vive in periferia", rural: "vive in campagna"},
  skincare_routine: {none: "nessuna routine di cura della pelle", basic: "routine essenziale", extended: "routine curata"},
  fitness_active: {yes: "fa sport", no: "non fa sport"}
};
export const ATTRIBUTE_LABEL: Record<string, string> = {household: "Nucleo", has_children: "Figli", pet_species: "Animale", relationship_status: "Stato civile", urbanicity: "Zona", skincare_routine: "Cura della pelle", fitness_active: "Sport"};
export const valueLabel = (attribute: string, value: string) => VALUE_LABEL[attribute]?.[value] ?? value;

export const SEGMENT_LABEL: Record<string, string> = {age_band: "Età", placement: "Dove lo vedono", household: "Nucleo", pet_species: "Animale", gender: "Genere", income_band: "Reddito", urbanicity: "Zona", device_os: "Telefono", in_ideal_target: "Target ideale"};
export const SEGMENT_VALUE: Record<string, Record<string, string>> = {
  household: {alone: "Da soli", couple: "In coppia", family: "In famiglia", shared: "Casa condivisa"},
  pet_species: {dog: "Cane", cat: "Gatto", other: "Altro animale", none: "Nessuno"},
  gender: {women: "Donne", men: "Uomini"},
  income_band: {low: "Reddito basso", mid: "Reddito medio", high: "Reddito alto"},
  urbanicity: {urban: "Città", suburban: "Periferia", rural: "Campagna"},
  device_os: {ios: "iPhone", android: "Android"},
  in_ideal_target: {true: "Nel target ideale", false: "Fuori dal target ideale"}
};
export const segmentValue = (dimension: string, key: string) => SEGMENT_VALUE[dimension]?.[key] ?? key;

export const QUALITY_FLAG: Record<string, string> = {
  conceptual_repetition: "Molte reazioni dicono la stessa cosa",
  weak_grounding: "Molte reazioni non riguardano ciò che si vede nell'annuncio",
  invented_numbers: "Alcune reazioni citano numeri che non c'erano",
  inconsistent_decisions: "Alcune decisioni si contraddicono",
  marketer_language: "Alcune reazioni parlano da esperti di marketing",
  positivity_bias: "Troppe persone sembrano interessate",
  uniform_decisions: "Tutte le persone hanno deciso allo stesso modo",
  insensitive_to_profile: "Le decisioni non cambiano con il profilo della persona"
};
export const QUALITY_WARNING: Record<string, string> = {
  mean_notice_outside_plausible_range: "L'attenzione media è fuori da un intervallo plausibile",
  mean_click_outside_plausible_range: "Il click medio è fuori da un intervallo plausibile"
};
export const NOTE_ACTION: Record<string, string> = {not_targetable: "Non esiste su Instagram e Facebook", low_precision: "Il pubblico raggiunto sarà più largo"};
export const OUTCOME_LABEL: Record<string, string> = {clicked: "Ha cliccato", engaged: "Ha interagito senza aprire", stopped: "Ha guardato senza interagire", skipped: "Ha ignorato l'annuncio"};
