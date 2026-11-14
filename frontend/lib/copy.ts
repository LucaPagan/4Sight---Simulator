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

export const TRUST = {
  preliminary: "Stima preliminare: aspetta che la simulazione sia completa prima di decidere.",
  strong: "Differenza netta: puoi fidarti di questa indicazione.",
  medium: "Differenza media: è un'indicazione, non una certezza.",
  weak: "Differenza piccola: considerala solo un'indicazione.",
  unknown: "Confronto non ancora verificato: considera il risultato indicativo."
};
