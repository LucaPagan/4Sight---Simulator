import type {TargetingSpec} from "./contracts.generated";

// Il pubblico è facoltativo: senza impostazioni la simulazione usa il pubblico generico di prima.
export function isTargetingActive(t?: TargetingSpec | null): boolean {
  if (!t) return false;
  return Boolean(
    (t.audience_intent ?? "").trim() || t.constraints?.length || t.regions?.length || (t.urbanicity && t.urbanicity !== "any") ||
    (t.age_min ?? 18) !== 18 || (t.age_max ?? 65) !== 65 || (t.gender && t.gender !== "all") || t.languages?.length ||
    t.detailed?.length || t.custom_audiences?.length || t.advantage_audience || t.advantage_placements === false || t.placements?.length ||
    t.device_platforms?.length || t.wifi_only || t.hours?.length || t.weekdays?.length || t.frequency_cap ||
    (t.optimization_goal && t.optimization_goal !== "link_clicks") || (t.bid_strategy && t.bid_strategy !== "lowest_cost")
  );
}

// Cosa impedisce di partire con questo pubblico: gli stessi vincoli del server, detti in anticipo.
export function targetingProblems(t?: TargetingSpec | null): string[] {
  if (!t) return [];
  const problems: string[] = [];
  if ((t.age_min ?? 18) > (t.age_max ?? 65)) problems.push("l'età minima è maggiore della massima");
  if (t.advantage_placements === false && !t.placements?.length) problems.push("nessun posizionamento scelto");
  if (t.bid_strategy && t.bid_strategy !== "lowest_cost" && (t.bid_amount_eur === null || t.bid_amount_eur === undefined)) problems.push("l'importo dell'offerta");
  return problems;
}

const split = (text: string) => text.split(",").map(x => x.trim()).filter(Boolean);
export const listToText = (items?: string[]) => (items ?? []).join(", ");
export const textToList = split;

// Ciò che si invia: niente testo vuoto, posizionamenti manuali solo se disattivati quelli automatici.
export function toPayload(t: TargetingSpec): TargetingSpec {
  const next: TargetingSpec = {...t, audience_intent: (t.audience_intent ?? "").trim()};
  if (next.advantage_placements !== false) next.placements = [];
  if (!next.bid_strategy || next.bid_strategy === "lowest_cost") next.bid_amount_eur = null;
  return next;
}

export const HOURS = Array.from({length: 24}, (_, h) => h);
export function hoursBetween(from: number, to: number): number[] {
  if (from === to) return [];
  const out: number[] = [];
  for (let h = from; h !== to; h = (h + 1) % 24) out.push(h);
  return out;
}
