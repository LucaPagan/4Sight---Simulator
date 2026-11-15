"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useMemo, useState} from "react";
import {LoaderCircle, Plus} from "lucide-react";
import {api} from "@/lib/api";
import {useApp} from "@/components/app-provider";
import {Hero} from "@/components/hero";
import {Mark, markLetter} from "@/components/mark";
import {TargetingSection} from "@/components/targeting-form";
import {MODE_LABEL, NATIVE_WARNING, PROVIDER_LABEL, SIMULATION_NOTE, VERTICALS} from "@/lib/copy";
import {isTargetingActive, targetingProblems, toPayload} from "@/lib/targeting";
import {fmt} from "@/lib/format";
import type {Brief, Mode, Run, Slot} from "@/lib/types";

// Quanti consumatori sintetici: tre scelte, niente numeri da calcolare.
const SIZES = [
  {value: 60, label: "Veloce", hint: "Una prima occhiata"},
  {value: 120, label: "Standard", hint: "Per quasi tutti i test"},
  {value: 600, label: "Approfondito", hint: "Più stabile, molto più lento"}
];

export function NewSimulation() {
  const router = useRouter();
  const {brief, patch, setError, editCreative, addCreative, removeCreative, loadExample, resetBrief, rememberRunName, refresh, runtime, runtimeChoice} = useApp();
  const [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<Mode>("history_forecast");
  const [full, setFull] = useState(true);
  const targeted = isTargetingActive(brief.targeting);
  const native = mode === "agent_native" && targeted;
  const slots: Slot[] = full ? ["first", "repeat", "saturated"] : ["first"];

  const payload: Brief = useMemo(() => ({
    ...brief,
    targeting: targeted && brief.targeting ? toPayload(brief.targeting) : undefined,
    brand: brief.brand.trim() || brief.name.trim(),
    creatives: brief.creatives.map(c => {
      const next: Record<string, unknown> = {...c};
      for (const key of ["offer", "price_text", "landing_page_summary"]) if (!String(next[key] ?? "").trim()) delete next[key];
      return next as typeof c;
    })
  }), [brief]);
  const missing = [
    !brief.name.trim() && "il nome",
    !brief.product_description.trim() && "cosa promuovi",
    !(brief.date_from && brief.date_to && brief.date_from <= brief.date_to) && "date valide",
    !brief.creatives.every(c => c.headline.trim() && c.primary_text.trim()) && "titolo e testo di ogni creatività",
    ...targetingProblems(brief.targeting).map(p => `nel pubblico: ${p}`)
  ].filter(Boolean) as string[];
  const empty = !brief.name && !brief.product_description && brief.creatives.every(c => !c.headline && !c.primary_text);
  const sizes = SIZES.some(s => s.value === brief.population_size) ? SIZES : [...SIZES, {value: brief.population_size, label: "Personalizzato", hint: "Dalla simulazione ripetuta"}];
  const engine = runtimeChoice.provider === "ollama" ? "Modello locale" : PROVIDER_LABEL[runtimeChoice.provider];

  async function launch() {
    if (missing.length || busy) return;
    setBusy(true); setError("");
    try {
      const scenario = await api<{id: string}>("/scenarios", payload);
      const run = await api<Run>("/simulations", {scenario_id: scenario.id, idempotency_key: crypto.randomUUID(), ...runtimeChoice, model: runtimeChoice.model || null, ...(native ? {mode: "agent_native", slots} : {})});
      rememberRunName(run.id, brief.name.trim());
      refresh();
      router.push(`/results/${run.id}`);
    } catch (e) {setError((e as Error).message); setBusy(false);}
  }

  return (
    <div className="page-form">
      <Hero title="Quale annuncio funziona meglio?" lead="Scrivi le tue creatività. Un pubblico simulato le valuta e ti dice quale scegliere, prima di spendere budget.">
        <p className="quick">{empty ? <button className="link" onClick={loadExample}>Compila con un esempio</button> : <button className="link" onClick={resetBrief}>Svuota il modulo</button>}</p>
      </Hero>

      <div className="form-layout">
      <div className="form-main">
      <section className="block-form">
        <h2>La campagna</h2>
        <div className="fields">
          <label className="field">Nome
            <input value={brief.name} onChange={e => patch("name", e.target.value)} placeholder="Es. Routine autunno" autoComplete="off" />
          </label>
          <label className="field wide">Cosa promuovi
            <textarea rows={2} value={brief.product_description} onChange={e => patch("product_description", e.target.value)} placeholder="Il prodotto in una o due frasi" />
          </label>
          <label className="field">Budget al giorno (€)
            <input type="number" min={0} max={100000} inputMode="decimal" value={brief.daily_adset_budget_eur} onChange={e => patch("daily_adset_budget_eur", Number(e.target.value))} />
          </label>
          <label className="field">Settore
            <select value={brief.vertical} onChange={e => patch("vertical", e.target.value)}>
              {Object.entries(VERTICALS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
        </div>
        <details className="more">
          <summary>Periodo e posizione</summary>
          <div className="fields">
            <label className="field">Dal
              <input type="date" value={brief.date_from} onChange={e => patch("date_from", e.target.value)} />
            </label>
            <label className="field">Al
              <input type="date" value={brief.date_to} min={brief.date_from} onChange={e => patch("date_to", e.target.value)} />
            </label>
            <label className="field wide">Dove compare
              <select value={brief.placement} onChange={e => patch("placement", e.target.value)}>
                <option value="instagram_feed">Feed di Instagram</option>
                <option value="facebook_feed">Feed di Facebook</option>
                <option value="instagram_stories">Storie di Instagram</option>
              </select>
            </label>
          </div>
        </details>
      </section>

      <section className="block-form">
        <h2>Le creatività da confrontare</h2>
        <div className="creatives">
          {brief.creatives.map((creative, index) => (
            <fieldset className="creative" key={creative.id}>
              <legend><Mark index={index} size={22} /> Creatività {markLetter(index)}</legend>
              <label className="field">Titolo
                <input value={creative.headline} onChange={e => editCreative(index, "headline", e.target.value)} />
              </label>
              <label className="field">Testo
                <textarea rows={3} value={creative.primary_text} onChange={e => editCreative(index, "primary_text", e.target.value)} />
              </label>
              <label className="field">Formato
                <select value={creative.format} onChange={e => editCreative(index, "format", e.target.value)}>
                  <option value="immagine">Immagine</option>
                  <option value="video">Video</option>
                  <option value="carosello">Carosello</option>
                </select>
              </label>
              <details>
                <summary>Altri dettagli</summary>
                <label className="field">Cosa si vede
                  <textarea rows={2} value={creative.visual_description} onChange={e => editCreative(index, "visual_description", e.target.value)} placeholder="Descrivi l'immagine o il video" />
                </label>
                <label className="field">Offerta
                  <input value={creative.offer ?? ""} onChange={e => editCreative(index, "offer", e.target.value)} placeholder="Es. -20% fino a domenica" />
                </label>
                <label className="field">Prezzo mostrato
                  <input value={creative.price_text ?? ""} onChange={e => editCreative(index, "price_text", e.target.value)} placeholder="Es. 19,90 € invece di 24,90 €" />
                </label>
                <label className="field">Pagina dopo il clic
                  <textarea rows={2} value={creative.landing_page_summary ?? ""} onChange={e => editCreative(index, "landing_page_summary", e.target.value)} placeholder="Cosa trova chi clicca" />
                </label>
              </details>
              {brief.creatives.length > 2 && <button className="link remove" onClick={() => removeCreative(index)}>Rimuovi la creatività {markLetter(index)}</button>}
            </fieldset>
          ))}
        </div>
        {brief.creatives.length < 4 && <button className="button ghost" onClick={addCreative}><Plus size={18} aria-hidden="true" /> Aggiungi una creatività</button>}
      </section>

      <TargetingSection />

      </div>

      <aside className="form-side" aria-label="Avvio">
        <h2>Quanti consumatori simulare</h2>
        <div className="choice" role="radiogroup" aria-label="Numero di consumatori simulati">
          {sizes.map(option => (
            <label key={option.value} className={brief.population_size === option.value ? "selected" : ""}>
              <input type="radio" name="size" checked={brief.population_size === option.value} onChange={() => patch("population_size", option.value)} />
              <b className="num">{fmt(option.value)}</b>
              <em>{option.label}</em>
              <span>{option.hint}</span>
            </label>
          ))}
        </div>

        <h2>Come simulare</h2>
        <div className="choice" role="radiogroup" aria-label="Come simulare">
          <label className={!native ? "selected" : ""}>
            <input type="radio" name="mode" checked={!native} onChange={() => setMode("history_forecast")} />
            <em>{MODE_LABEL.history_forecast}</em>
            <span>Il CTR parte dai dati storici; le persone spiegano il perché.</span>
          </label>
          <label className={native ? "selected" : ""} aria-disabled={!targeted}>
            <input type="radio" name="mode" disabled={!targeted} checked={native} onChange={() => setMode("agent_native")} />
            <em>{MODE_LABEL.agent_native} <small>sperimentale</small></em>
            <span>{targeted ? "Il CTR nasce dalle decisioni di ogni persona. Più lenta." : "Richiede di descrivere il pubblico."}</span>
          </label>
        </div>
        {native && (
          <label className="checkbox-label"><input type="checkbox" checked={full} onChange={e => setFull(e.target.checked)} />Considera anche chi ha già visto l&apos;annuncio più volte</label>
        )}

        <div className="launch">
          {native ? (
            <>
              <p><b className="num">{fmt(brief.population_size * brief.creatives.length * slots.length)}</b> reazioni, almeno</p>
              <p className="hint">Più le schede di {fmt(brief.population_size)} persone. {runtimeChoice.provider === "ollama" ? "Con il modello locale ogni scheda e ogni reazione richiedono decine di secondi: per una prima prova scegli 60 persone e togli le ripetizioni." : "Con un modello online può servire più di un'ora."} Si riprende da dove si ferma.</p>
              <p className="warn">{NATIVE_WARNING}</p>
            </>
          ) : <p><b className="num">{fmt(brief.population_size * brief.creatives.length)}</b> valutazioni</p>}
          <p className="hint">{engine} · {runtime?.ready ? "pronto" : "da verificare"}. <Link href="/settings">Cambia motore</Link></p>
          {!runtime?.ready && <p className="hint">Se il modello non risponde, parte una stima preliminare dai dati storici.</p>}
          {missing.length > 0 && <p className="hint">Per partire mancano: {missing.join(", ")}.</p>}
          <button className="button primary big" disabled={missing.length > 0 || busy} onClick={launch}>
            {busy && <LoaderCircle className="spin" size={18} aria-hidden="true" />} Avvia simulazione
          </button>
        </div>
        <p className="note">{SIMULATION_NOTE}</p>
      </aside>
      </div>
    </div>
  );
}
