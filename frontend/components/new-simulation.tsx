"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useEffect, useMemo, useState} from "react";
import {ArrowLeft, ArrowRight, Check, LoaderCircle, Plus, X} from "lucide-react";
import {api} from "@/lib/api";
import {AgentCount} from "@/components/agent-count";
import {AgentDialog} from "@/components/agent-dialog";
import {useApp} from "@/components/app-provider";
import {Mark, markLetter} from "@/components/mark";
import {RuntimeSelector, type RuntimeChoice} from "@/components/runtime-panel";
import {LEVERS, PROVIDER_LABEL, SENSITIVITY, SIMULATION_NOTE, VERTICALS} from "@/lib/copy";
import {BANDS, euros, fmt, minutes, shortDate} from "@/lib/format";
import {agentReliability} from "@/lib/panel";
import type {Brief, Profile, Run} from "@/lib/types";

const STEPS = ["Campagna e creatività", "Pubblico", "Controlla e avvia"];

type Pending = {id: string; count: number; cached: number; seconds: number | null; ready: boolean; withinLimit: boolean; selection: RuntimeChoice; name: string};

export function NewSimulation() {
  const router = useRouter();
  const app = useApp();
  const {brief, patch, setError, runtimeChoice, setRuntimeChoice} = app;
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [agent, setAgent] = useState<Profile | null>(null);

  const payload: Brief = useMemo(() => ({...brief, brand: brief.brand.trim() || brief.name.trim()}), [brief]);
  const campaignOk = !!brief.name.trim() && !!brief.product_description.trim() && !!brief.date_from && !!brief.date_to && brief.date_from <= brief.date_to;
  const creativesOk = brief.creatives.every(c => c.headline.trim() && c.primary_text.trim());
  const canContinue = campaignOk && creativesOk;

  useEffect(() => {setPending(null); setProfiles([]);}, [brief, runtimeChoice.provider, runtimeChoice.model]);

  useEffect(() => {
    if (step !== 2 || pending) return;
    let stopped = false;
    setBusy("prepare");
    (async () => {
      try {
        const scenario = await api<{id: string}>("/scenarios", payload);
        const check = await api<{required_policies: number; cached_policies: number; estimated_seconds: number | null; within_limit: boolean; runtime: {ready: boolean}}>("/simulations/preflight", {scenario_id: scenario.id, ...runtimeChoice, model: runtimeChoice.model || null});
        if (!stopped) setPending({id: scenario.id, count: check.required_policies, cached: check.cached_policies, seconds: check.estimated_seconds, ready: check.runtime.ready, withinLimit: check.within_limit !== false, selection: runtimeChoice, name: brief.name.trim()});
      } catch (e) {
        if (!stopped) {setError((e as Error).message); setStep(1);}
      } finally {
        if (!stopped) setBusy("");
      }
    })();
    return () => {stopped = true;};
  }, [step, pending, payload, runtimeChoice, brief.name, setError]);

  async function showAudience() {
    setBusy("population"); setError("");
    try {
      const scenario = await api<{population_id: string}>("/scenarios", payload);
      const pop = await api<{profiles: Profile[]}>(`/populations/${scenario.population_id}`);
      setProfiles(pop.profiles);
    } catch (e) {setError((e as Error).message);} finally {setBusy("");}
  }

  async function launch() {
    if (!pending) return;
    setBusy("launch"); setError("");
    try {
      const run = await api<Run>("/simulations", {scenario_id: pending.id, idempotency_key: crypto.randomUUID(), ...pending.selection, model: pending.selection.model || null});
      app.rememberRunName(run.id, pending.name);
      app.refresh();
      router.push(`/results/${run.id}`);
    } catch (e) {setError((e as Error).message); setBusy("");}
  }

  function go(next: number) {setError(""); setStep(next); window.scrollTo({top: 0});}

  return (
    <div className="flow">
      <div className="flow-main">
        <ol className="steps" aria-label="Passi della simulazione">
          {STEPS.map((label, i) => (
            <li key={label} className={i === step ? "current" : i < step ? "done" : ""} aria-current={i === step ? "step" : undefined}>
              {i < step ? <button className="step-button" onClick={() => go(i)}><b>{<Check size={14} aria-hidden="true" />}</b>{label}</button> : <span><b>{i + 1}</b>{label}</span>}
            </li>
          ))}
        </ol>

        {step === 0 && <CampaignStep />}
        {step === 1 && <AudienceStep profiles={profiles} busy={busy === "population"} onShow={showAudience} onOpen={setAgent} />}
        {step === 2 && <ReviewStep pending={pending} onEditAudience={() => go(1)} />}
      </div>

      <aside className="flow-aside" aria-label="Riepilogo">
        <h2>{step === 2 ? "Pronto a partire" : "Riepilogo"}</h2>
        {step < 2 ? (
          <ul className="facts">
            <li><b className="num">{brief.creatives.length}</b> creatività da confrontare</li>
            <li><b className="num">{fmt(brief.population_size)}</b> consumatori sintetici</li>
            <li><b className="num">{fmt(brief.daily_adset_budget_eur)} €</b> al giorno di budget</li>
          </ul>
        ) : (
          <div className="estimate" aria-live="polite">
            {busy === "prepare" || !pending ? <p><LoaderCircle className="spin" size={18} aria-hidden="true" /> Calcolo la durata…</p> : (
              <p><b className="num">{fmt(pending.count)}</b> valutazioni{pending.cached ? `, di cui ${fmt(pending.cached)} già pronte` : ""}{minutes(pending.seconds) ? `, ${minutes(pending.seconds)}` : ""}.</p>
            )}
            {pending && !pending.seconds && pending.count - pending.cached > 400 && <p className="hint">Con tanti agenti può servire un po&apos; di tempo: puoi lasciarla andare e tornare più tardi.</p>}
            {pending && !pending.withinLimit && <p className="hint">Supera il limite di valutazioni per sessione: si fermerà e potrai riprenderla da dove era arrivata.</p>}
          </div>
        )}
        {step === 0 && <>
          <button className="button primary" disabled={!canContinue} onClick={() => go(1)}>Continua al pubblico <ArrowRight size={18} aria-hidden="true" /></button>
          {!canContinue && <p className="hint">Per continuare servono nome, prodotto, date valide e titolo e testo di ogni creatività.</p>}
        </>}
        {step === 1 && <>
          <button className="button primary" onClick={() => go(2)}>Continua al riepilogo <ArrowRight size={18} aria-hidden="true" /></button>
          <button className="button ghost" onClick={() => go(0)}><ArrowLeft size={18} aria-hidden="true" /> Torna alla campagna</button>
        </>}
        {step === 2 && <>
          <button className="button primary" disabled={!pending || busy === "launch"} onClick={launch}>
            {busy === "launch" ? <LoaderCircle className="spin" size={18} aria-hidden="true" /> : null}
            {pending && !pending.ready ? "Avvia con stima preliminare" : "Avvia simulazione"}
          </button>
          <button className="button ghost" onClick={() => go(1)}><ArrowLeft size={18} aria-hidden="true" /> Torna al pubblico</button>
        </>}
        <p className="note">{SIMULATION_NOTE}</p>
      </aside>

      <AgentDialog agent={agent} events={[]} onClose={() => setAgent(null)} />
    </div>
  );
}

function CampaignStep() {
  const {brief, patch, editCreative, addCreative, removeCreative, applyAsset, assets, loadExample, resetBrief} = useApp();
  const empty = !brief.name && !brief.product_description && brief.creatives.every(c => !c.headline && !c.primary_text);
  return (
    <section>
      <h1>Descrivi la campagna</h1>
      <p className="lead">Bastano pochi dati. Quello che manca ha già un valore sensato e lo trovi in «Altri dettagli».</p>
      <p className="quick">{empty ? <button className="link" onClick={loadExample}>Compila con un esempio</button> : <button className="link" onClick={resetBrief}>Svuota il modulo</button>}</p>

      <div className="fields">
        <label className="field wide">Nome della campagna
          <input value={brief.name} onChange={e => patch("name", e.target.value)} placeholder="Es. Routine autunno" autoComplete="off" />
        </label>
        <label className="field wide">Cosa promuovi
          <textarea rows={2} value={brief.product_description} onChange={e => patch("product_description", e.target.value)} placeholder="Descrivi il prodotto in una o due frasi" />
        </label>
      </div>
      <div className="fields three">
        <label className="field">Dal
          <input type="date" value={brief.date_from} onChange={e => patch("date_from", e.target.value)} />
        </label>
        <label className="field">Al
          <input type="date" value={brief.date_to} min={brief.date_from} onChange={e => patch("date_to", e.target.value)} />
        </label>
        <label className="field">Budget al giorno (€)
          <input type="number" min={0} max={100000} inputMode="decimal" value={brief.daily_adset_budget_eur} onChange={e => patch("daily_adset_budget_eur", Number(e.target.value))} />
        </label>
      </div>

      <details className="more">
        <summary>Altri dettagli</summary>
        <div className="fields">
          <label className="field">Obiettivo
            <select value={brief.objective} onChange={e => patch("objective", e.target.value)}>
              <option value="vendite">Vendite</option>
              <option value="traffico">Traffico (stima indicativa)</option>
            </select>
          </label>
          <label className="field">Brand
            <input value={brief.brand} onChange={e => patch("brand", e.target.value)} placeholder="Se vuoto uso il nome della campagna" />
          </label>
          <label className="field">Settore
            <select value={brief.vertical} onChange={e => patch("vertical", e.target.value)}>
              {Object.entries(VERTICALS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <label className="field">Mercato
            <select value={brief.country} onChange={e => patch("country", e.target.value)}>
              <option value="IT">Italia</option>
              <option value="ES">Spagna (scenario)</option>
              <option value="FR">Francia (scenario)</option>
              <option value="DE">Germania (scenario)</option>
            </select>
          </label>
          <label className="field">Dove compare l&apos;annuncio
            <select value={brief.placement} onChange={e => patch("placement", e.target.value)}>
              <option value="instagram_feed">Feed di Instagram</option>
              <option value="facebook_feed">Feed di Facebook</option>
              <option value="instagram_stories">Storie di Instagram</option>
            </select>
          </label>
          <label className="field">Prezzo del prodotto (€, facoltativo)
            <input type="number" min={0} inputMode="decimal" placeholder="Non lo so" value={brief.price_eur ?? ""} onChange={e => patch("price_eur", e.target.value === "" ? null : Number(e.target.value))} />
          </label>
        </div>
      </details>

      <h2 className="section-title">Creatività da confrontare</h2>
      <div className="creatives">
        {brief.creatives.map((creative, index) => {
          const options = assets.filter(a => a.vertical === brief.vertical);
          return (
            <fieldset className="creative" key={creative.id}>
              <legend><Mark index={index} size={20} /> Creatività {markLetter(index)}</legend>
              <label className="field">Titolo
                <input value={creative.headline} onChange={e => editCreative(index, "headline", e.target.value)} />
              </label>
              <label className="field">Testo dell&apos;annuncio
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
                {options.length > 0 && (
                  <label className="field">Parti da un esempio
                    <select value="" onChange={e => {const a = assets.find(x => x.asset_id === e.target.value); if (a) applyAsset(a, index);}}>
                      <option value="">Scegli un annuncio del settore</option>
                      {options.map(a => <option key={a.asset_id} value={a.asset_id}>{a.headline}</option>)}
                    </select>
                  </label>
                )}
                <label className="field">Cosa si vede
                  <textarea rows={2} value={creative.visual_description} onChange={e => editCreative(index, "visual_description", e.target.value)} placeholder="Foto, video o carosello: descrivilo a parole" />
                </label>
                <label className="field">Leva principale
                  <select value={creative.lever} onChange={e => editCreative(index, "lever", e.target.value)}>
                    {Object.entries(LEVERS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                  </select>
                </label>
                <label className="check">
                  <input type="checkbox" checked={creative.claim_verified} onChange={e => editCreative(index, "claim_verified", e.target.checked)} />
                  Ho verificato che le promesse dell&apos;annuncio sono vere
                </label>
              </details>
              {brief.creatives.length > 1 && (
                <button className="link remove" onClick={() => removeCreative(index)}>Rimuovi la creatività {markLetter(index)}</button>
              )}
            </fieldset>
          );
        })}
      </div>
      {brief.creatives.length < 4 && (
        <button className="button secondary" onClick={addCreative}><Plus size={18} aria-hidden="true" /> Aggiungi una creatività</button>
      )}
    </section>
  );
}

function AudienceStep({profiles, busy, onShow, onOpen}: {profiles: Profile[]; busy: boolean; onShow: () => void; onOpen: (p: Profile) => void}) {
  const {brief, patch} = useApp();
  return (
    <section>
      <h1>Chi vedrà l&apos;annuncio</h1>
      <p className="lead">{fmt(brief.population_size)} consumatori sintetici, circa {fmt(Math.round(brief.population_size / 6))} per ogni fascia d&apos;età, valutano ogni creatività. Scegli quanti simularne e quanta fiducia dare alle ipotesi sul pubblico.</p>

      <AgentCount />

      <h2 className="section-title tight">Quanta fiducia dare alle ipotesi sul pubblico</h2>
      <div className="choice" role="radiogroup" aria-label="Fiducia nelle ipotesi sul pubblico">
        {SENSITIVITY.map(option => (
          <label key={option.id} className={brief.sensitivity_profile === option.id ? "selected" : ""}>
            <input type="radio" name="sensitivity" checked={brief.sensitivity_profile === option.id} onChange={() => patch("sensitivity_profile", option.id)} />
            <b>{option.label}</b>
            <span>{option.hint}</span>
          </label>
        ))}
      </div>

      <details className="more">
        <summary>Avanzate: quote per età e controlli esperti</summary>
        <p className="muted">Quanta parte delle visualizzazioni va a ogni fascia d&apos;età. Nei dati non c&apos;è alcuna età osservata: è un&apos;ipotesi tua.</p>
        {BANDS.map((band, i) => (
          <div className="slider" key={band}>
            <label htmlFor={`age-${i}`}>{band}</label>
            <input id={`age-${i}`} aria-label={`Quota ${band}`} type="range" min={0} max={100} value={Math.round(brief.age_shares[i] * 100)} onChange={e => {
              const next = Number(e.target.value) / 100;
              const rest = brief.age_shares.reduce((s, x, j) => (j === i ? s : s + x), 0);
              patch("age_shares", brief.age_shares.map((x, j) => (j === i ? next : rest ? x / rest * (1 - next) : (1 - next) / 5)));
            }} />
            <b className="num">{fmt(brief.age_shares[i] * 100, 1)}%</b>
          </div>
        ))}
        <div className="fields">
          <label className="field">Quanto contano le differenze tra le età: <b className="num">{fmt(brief.prior_strength, 1)}×</b>
            <input type="range" min={0} max={2} step={0.1} value={brief.prior_strength} onChange={e => patch("prior_strength", Number(e.target.value))} />
          </label>
          <label className="field">Cosa sta facendo il consumatore
            <select value={brief.browsing_task} onChange={e => patch("browsing_task", e.target.value)}>
              <option value="casual_scrolling">Scorre senza meta</option>
              <option value="product_research">Cerca un prodotto</option>
              <option value="comparison_shopping">Confronta le offerte</option>
            </select>
          </label>
          <label className="field">Codice per ripetere lo stesso risultato
            <input type="number" min={0} value={brief.seed} onChange={e => patch("seed", Number(e.target.value))} />
          </label>
        </div>
        <div className="row">
          <button className="button secondary" onClick={() => patch("age_effects", brief.age_effects.map(x => -x))}>Inverti le differenze tra le età</button>
          <button className="button secondary" onClick={() => patch("prior_strength", 0)}>Ignora le differenze tra le età</button>
        </div>
      </details>

      <details className="more" onToggle={e => {if ((e.currentTarget as HTMLDetailsElement).open && !profiles.length && !busy) onShow();}}>
        <summary>Vedi alcuni dei {fmt(brief.population_size)} consumatori</summary>
        {busy ? <p className="muted"><LoaderCircle className="spin" size={18} aria-hidden="true" /> Preparo i consumatori…</p> : profiles.length ? (
          <ul className="plain-list">
            {profiles.filter((_, i) => i % Math.max(1, Math.ceil(profiles.length / 12)) === 0).map(p => (
              <li key={p.agent_id}>
                <button onClick={() => onOpen(p)}><span>{p.age_band} anni</span><span className="muted">Interesse per la categoria {fmt(p.category_affinity * 100)}%</span></button>
              </li>
            ))}
          </ul>
        ) : null}
      </details>
    </section>
  );
}

function ReviewStep({pending, onEditAudience}: {pending: Pending | null; onEditAudience: () => void}) {
  const {brief, runtimeChoice, setRuntimeChoice, runtime} = useApp();
  const engine = runtimeChoice.provider === "ollama" ? "Modello locale (Ollama)" : `${PROVIDER_LABEL[runtimeChoice.provider]} · ${runtimeChoice.model}`;
  return (
    <section>
      <h1>Controlla e avvia</h1>
      <p className="lead">Rivedi cosa verrà simulato. Puoi tornare indietro in qualsiasi momento.</p>

      <dl className="summary">
        <div><dt>Campagna</dt><dd>{brief.name || "Senza nome"}<small>{brief.product_description}</small></dd></div>
        <div><dt>Periodo e budget</dt><dd>{brief.date_from === brief.date_to ? shortDate(brief.date_from) : `${shortDate(brief.date_from)} → ${shortDate(brief.date_to)}`}<small>{euros(brief.daily_adset_budget_eur, 0)} al giorno</small></dd></div>
        <div><dt>Creatività</dt><dd>
          <ul className="inline-list">{brief.creatives.map((c, i) => <li key={c.id}><Mark index={i} /> {c.headline}</li>)}</ul>
        </dd></div>
        <div><dt>Pubblico</dt><dd>{fmt(brief.population_size)} consumatori sintetici<small>Affidabilità per età: {agentReliability(brief.population_size).level.toLowerCase()} · <button className="link" onClick={onEditAudience}>Cambia numero</button><br />Ipotesi: {SENSITIVITY.find(s => s.id === brief.sensitivity_profile)?.label.toLowerCase()}</small></dd></div>
        <div><dt>Motore AI</dt><dd>{engine}<small>{runtime?.ready ? "Pronto" : "Non ancora verificato"} · <Link href="/settings">Cambia o prova</Link></small></dd></div>
      </dl>

      {pending && !pending.ready && <p className="warn">Il modello non è pronto: parte una stima preliminare dai dati storici e le reazioni dei consumatori arrivano quando il modello risponde. Puoi controllarlo in Impostazioni.</p>}
      {brief.date_from !== brief.date_to && <p className="muted top-space">Per un primo test conviene un solo giorno: è molto più veloce.</p>}

      <details className="more">
        <summary>Cambia motore AI</summary>
        <RuntimeSelector value={runtimeChoice} onChange={setRuntimeChoice} />
      </details>
    </section>
  );
}
