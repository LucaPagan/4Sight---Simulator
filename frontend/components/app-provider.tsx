"use client";

import {createContext, useCallback, useContext, useEffect, useMemo, useState} from "react";
import type {ReactNode} from "react";
import {api} from "@/lib/api";
import type {Brief, Catalog, Creative, Run, Runtime, TargetingSpec} from "@/lib/types";
import type {RuntimeChoice} from "@/components/runtime-panel";

export type Asset = {asset_id: string; vertical: string; headline: string; testo_principale: string; descrizione_visual: string; call_to_action: string; leva: string; formato: string};

const NAMES_KEY = "audience-simulator:run-names";
const WINNERS_KEY = "audience-simulator:run-winners";

function blankCreative(id: string): Creative {
  return {id, headline: "", primary_text: "", visual_description: "", cta: "Scopri di più", lever: "value", format: "immagine", claim_verified: false, offer: "", price_text: "", landing_page_summary: ""};
}

function today(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const EMPTY_BRIEF: Brief = {
  name: "", brand: "", product_description: "", vertical: "beauty_skincare", objective: "vendite", platform: "meta", country: "IT",
  date_from: "", date_to: "", daily_adset_budget_eur: 150,
  creatives: [blankCreative("creative-A"), blankCreative("creative-B")],
  population_size: 120, seed: 42, age_shares: Array(6).fill(1 / 6), age_effects: [-0.2, -0.1, 0, 0.05, 0.2, 0.05],
  sensitivity_profile: "central", prior_strength: 1, placement: "instagram_feed", browsing_task: "casual_scrolling", price_eur: null, notes: ""
};

function exampleBrief(): Brief {
  return {
    ...EMPTY_BRIEF,
    name: "Routine autunno · Test creatività",
    brand: "Nuvola Derma Lab",
    product_description: "Kit routine autunno con detergente, siero e crema.",
    date_from: today(), date_to: today(),
    creatives: [
      {...blankCreative("creative-A"), headline: "Edizione limitata: kit routine autunno", primary_text: "Solo 500 kit numerati. Detergente, siero e crema in un'unica scatola.", visual_description: "Carosello con il kit, i tre prodotti e le recensioni.", lever: "scarcity", format: "carosello"},
      {...blankCreative("creative-B"), headline: "Una routine semplice, ogni giorno", primary_text: "Scopri il kit per la tua routine autunnale.", visual_description: "Una persona mostra i tre passaggi della routine.", lever: "value", format: "video"}
    ]
  };
}

type Ctx = {
  brief: Brief;
  setBrief: (value: Brief | ((current: Brief) => Brief)) => void;
  patch: <K extends keyof Brief>(key: K, value: Brief[K]) => void;
  editCreative: (index: number, key: keyof Creative, value: string | boolean) => void;
  patchTargeting: (change: Partial<TargetingSpec>) => void;
  clearTargeting: () => void;
  catalog: Catalog | null;
  addCreative: () => void;
  removeCreative: (index: number) => void;
  applyAsset: (asset: Asset, index: number) => void;
  loadExample: () => void;
  resetBrief: () => void;
  assets: Asset[];
  reloadAssets: () => void;
  runtimeChoice: RuntimeChoice;
  setRuntimeChoice: (value: RuntimeChoice) => void;
  runtime: Runtime | null;
  demoData: boolean;
  runs: Run[];
  runNames: Record<string, string>;
  rememberRunName: (id: string, name: string) => void;
  runWinners: Record<string, number>;
  rememberRunWinner: (id: string, index: number) => void;
  refresh: () => void;
  error: string;
  setError: (value: string) => void;
};

const AppContext = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const value = useContext(AppContext);
  if (!value) throw new Error("useApp va usato dentro AppProvider");
  return value;
}

export function AppProvider({children}: {children: ReactNode}) {
  const [brief, setBrief] = useState<Brief>(EMPTY_BRIEF);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [runtime, setRuntime] = useState<Runtime | null>(null);
  const [demoData, setDemoData] = useState(false);
  const [runtimeChoice, setRuntimeChoice] = useState<RuntimeChoice>({provider: "ollama", model: ""});
  const [runs, setRuns] = useState<Run[]>([]);
  const [runNames, setRunNames] = useState<Record<string, string>>({});
  const [runWinners, setRunWinners] = useState<Record<string, number>>({});
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState("");

  // Le date partono da oggi, ma solo sul client: evita differenze tra server e browser.
  useEffect(() => {
    setBrief(b => (b.date_from ? b : {...b, date_from: today(), date_to: today()}));
    try {setRunWinners(JSON.parse(localStorage.getItem(WINNERS_KEY) || "{}"));} catch {/* facoltativo */}
    try {setRunNames(JSON.parse(localStorage.getItem(NAMES_KEY) || "{}"));} catch {/* senza storage il nome torna generico */}
  }, []);

  const refresh = useCallback(() => {
    api<Runtime>(`/runtime/status?provider=${runtimeChoice.provider}&model=${encodeURIComponent(runtimeChoice.model)}`).then(setRuntime).catch(() => setRuntime(null));
    api<Run[]>("/simulations").then(list => setRuns([...list].sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "")))).catch(() => {});
  }, [runtimeChoice.provider, runtimeChoice.model]);

  useEffect(() => {refresh();}, [refresh]);
  // Se un modello online è già configurato, parte da quello: è molto più veloce di quello locale.
  useEffect(() => {
    let live = true;
    (async () => {
      for (const provider of ["gemini", "cloudflare"] as const) {
        try {
          const config = await api<{configured: boolean; free_tier_confirmed: boolean; models: {id: string}[]}>(`/runtime/config?provider=${provider}`);
          if (!live) return;
          if (config.configured && config.free_tier_confirmed) {
            setRuntimeChoice(current => (current.provider === "ollama" && !current.model ? {provider, model: config.models[0]?.id ?? ""} : current));
            return;
          }
        } catch {/* senza configurazione resta il modello locale */}
      }
    })();
    return () => {live = false;};
  }, []);
  useEffect(() => {api<{demo_data?: boolean}>("/health").then(h => setDemoData(!!h.demo_data)).catch(() => {});}, []);
  useEffect(() => {api<Catalog>("/targeting/catalog").then(setCatalog).catch(() => {});}, []);
  const reloadAssets = useCallback(() => {api<Asset[]>("/assets").then(setAssets).catch(() => {});}, []);
  useEffect(() => reloadAssets(), [reloadAssets]);

  const patch = useCallback(<K extends keyof Brief>(key: K, value: Brief[K]) => setBrief(b => ({...b, [key]: value})), []);
  const editCreative = useCallback((index: number, key: keyof Creative, value: string | boolean) =>
    setBrief(b => ({...b, creatives: b.creatives.map((c, i) => (i === index ? {...c, [key]: value} : c))})), []);
  const patchTargeting = useCallback((change: Partial<TargetingSpec>) => setBrief(b => ({...b, targeting: {...(b.targeting ?? {}), ...change}})), []);
  const clearTargeting = useCallback(() => setBrief(b => {const {targeting: _removed, ...rest} = b; return rest;}), []);
  const addCreative = useCallback(() =>
    setBrief(b => (b.creatives.length >= 4 ? b : {...b, creatives: [...b.creatives, blankCreative(`creative-${crypto.randomUUID().slice(0, 8)}`)]})), []);
  const removeCreative = useCallback((index: number) =>
    setBrief(b => (b.creatives.length <= 1 ? b : {...b, creatives: b.creatives.filter((_, i) => i !== index)})), []);
  const applyAsset = useCallback((asset: Asset, index: number) =>
    setBrief(b => ({...b, creatives: b.creatives.map((c, i) => (i === index ? {id: c.id, headline: asset.headline, primary_text: asset.testo_principale, visual_description: asset.descrizione_visual, cta: asset.call_to_action, lever: asset.leva, format: asset.formato, claim_verified: false} : c))})), []);
  const loadExample = useCallback(() => setBrief(exampleBrief()), []);
  const resetBrief = useCallback(() => setBrief({...EMPTY_BRIEF, date_from: today(), date_to: today()}), []);
  const rememberRunName = useCallback((id: string, name: string) => {
    setRunNames(current => {
      const next = {...current, [id]: name};
      try {localStorage.setItem(NAMES_KEY, JSON.stringify(next));} catch {/* facoltativo */}
      return next;
    });
  }, []);

  const rememberRunWinner = useCallback((id: string, index: number) => {
    setRunWinners(current => {
      if (current[id] === index) return current;
      const next = {...current, [id]: index};
      try {localStorage.setItem(WINNERS_KEY, JSON.stringify(next));} catch {/* facoltativo */}
      return next;
    });
  }, []);

  const value = useMemo<Ctx>(() => ({
    brief, setBrief, patch, editCreative, patchTargeting, clearTargeting, catalog, addCreative, removeCreative, applyAsset, loadExample, resetBrief, assets, reloadAssets,
    runtimeChoice, setRuntimeChoice, runtime, demoData, runs, runNames, rememberRunName, runWinners, rememberRunWinner, refresh, error, setError
  }), [demoData, runWinners, rememberRunWinner, brief, patch, editCreative, patchTargeting, clearTargeting, catalog, addCreative, removeCreative, applyAsset, loadExample, resetBrief, assets, reloadAssets, runtimeChoice, runtime, runs, runNames, rememberRunName, refresh, error]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
