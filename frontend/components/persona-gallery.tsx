"use client";

import {useMemo, useState} from "react";
import {SEGMENT_VALUE} from "@/lib/copy";
import type {Decision, NativeProfile, PersonaCard, Result} from "@/lib/types";

const PAGE = 12;
type Filter = "all" | "ideal" | "other";

function Split({d}: {d: Decision}) {
  const parts = [
    {key: "skip", label: "salta", value: d.skip_per_100},
    {key: "stop", label: "guarda", value: d.stop_per_100},
    {key: "engage", label: "interagisce", value: d.engage_per_100},
    {key: "click", label: "clicca", value: d.click_per_100}
  ];
  const text = `Su 100 volte: ${parts.map(p => `${p.label} ${p.value}`).join(", ")}.`;
  return (
    <div>
      <div className="split" role="img" aria-label={text}>
        {parts.map(p => p.value > 0 && <span key={p.key} className={`part ${p.key}`} style={{width: `${p.value}%`}} />)}
      </div>
      <p className="hint">{text}</p>
    </div>
  );
}

function facts(profile: NativeProfile): string[] {
  const out: string[] = [];
  if (profile.household) out.push(SEGMENT_VALUE.household[profile.household] ?? profile.household);
  if (profile.pet_species && profile.pet_species !== "none") out.push(SEGMENT_VALUE.pet_species[profile.pet_species] ?? profile.pet_species);
  if (profile.income_band) out.push(SEGMENT_VALUE.income_band[profile.income_band] ?? profile.income_band);
  return out;
}

function PersonaCardView({profile, card, decision}: {profile: NativeProfile; card: PersonaCard; decision?: Decision}) {
  return (
    <li className="persona">
      <header>
        <h3>{card.name}</h3>
        <p className="muted">{profile.age ? `${profile.age} anni · ` : ""}{card.city} · {card.job}</p>
        <div className="chips">
          {facts(profile).map(f => <span key={f} className="chip">{f}</span>)}
          {profile.in_ideal_target === false && <span className="chip off">Fuori dal target ideale</span>}
          {card.source === "template" && <span className="chip off">Scheda essenziale</span>}
        </div>
      </header>
      {decision ? (
        <>
          <blockquote>
            «{decision.first_impression}»
            {decision.reaction_after_stopping && <p>Se si ferma a leggere: «{decision.reaction_after_stopping}»</p>}
          </blockquote>
          <Split d={decision} />
        </>
      ) : <p className="muted">Nessuna reazione per questa creatività.</p>}
      <details>
        <summary>Chi è</summary>
        <p>{card.bio}</p>
        <p><b>Routine.</b> {card.daily_routine}</p>
        <p><b>Rapporto con la categoria.</b> {card.category_relationship}</p>
        <p><b>Sui social.</b> {card.social_habits}</p>
        <p><b>Davanti alle pubblicità.</b> {card.ad_reaction_style}</p>
        {card.pain_points.length > 0 && <p><b>Gli dà fastidio.</b> {card.pain_points.join("; ")}.</p>}
      </details>
    </li>
  );
}

// Le persone simulate, con la scheda e la reazione alla creatività scelta (prima visione).
export function PersonaGallery({result, creativeId}: {result: Result; creativeId: string}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [shown, setShown] = useState(PAGE);
  const rows = useMemo(() => {
    const decisions = new Map<string, Decision>();
    for (const s of result.decision_snapshot ?? []) {
      if (s.creative_id === creativeId && s.slot === "first" && !decisions.has(s.agent_id)) decisions.set(s.agent_id, s.decision);
    }
    return result.profiles
      .filter(p => result.cards?.[p.agent_id])
      .map(p => ({profile: p, card: result.cards![p.agent_id], decision: decisions.get(p.agent_id)}))
      .filter(r => filter === "all" || (filter === "ideal") === (r.profile.in_ideal_target !== false));
  }, [result, creativeId, filter]);
  if (!result.cards || !rows.length && filter === "all") return null;
  const templates = Object.values(result.cards).filter(c => c.source === "template").length;
  return (
    <section aria-labelledby="persona-heading">
      <div className="title-row">
        <h2 id="persona-heading">Le persone simulate</h2>
        <label className="inline-select">Mostra
          <select value={filter} onChange={e => {setFilter(e.target.value as Filter); setShown(PAGE);}}>
            <option value="all">Tutte</option>
            <option value="ideal">Nel target ideale</option>
            <option value="other">Fuori dal target ideale</option>
          </select>
        </label>
      </div>
      <p className="muted">Sono personaggi costruiti dal modello, non persone reali. Le loro reazioni sono ipotesi.{templates ? (templates === 1 ? " Una ha solo una scheda essenziale." : ` ${templates} hanno solo una scheda essenziale.`) : ""}</p>
      <ul className="personas">
        {rows.slice(0, shown).map(r => <PersonaCardView key={r.profile.agent_id} {...r} />)}
      </ul>
      {rows.length === 0 && <p className="muted">Nessuna persona in questo gruppo.</p>}
      {rows.length > shown && <button className="button secondary" onClick={() => setShown(n => n + PAGE)}>Mostra altre {Math.min(PAGE, rows.length - shown)}</button>}
    </section>
  );
}
