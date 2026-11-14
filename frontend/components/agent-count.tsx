"use client";

import {useEffect, useState} from "react";
import {useApp} from "@/components/app-provider";
import {fmt} from "@/lib/format";
import {AGENTS_NOTE, AGENT_PRESETS, MAX_AGENTS, MIN_AGENTS, RECOMMENDED_AGENTS, agentReliability, clampAgents, evaluationsFor, perBand} from "@/lib/panel";

// Quanti consumatori sintetici simulare: pochi per una prova rapida, tanti per una lettura più stabile.
export function AgentCount() {
  const {brief, patch} = useApp();
  const agents = brief.population_size;
  const [draft, setDraft] = useState(String(agents));
  useEffect(() => setDraft(String(agents)), [agents]);

  const reliability = agentReliability(agents);
  const preset = AGENT_PRESETS.some(p => p.value === agents);
  const typed = Number(draft);
  const invalid = draft.trim() === "" || !Number.isFinite(typed) || typed < MIN_AGENTS || typed > MAX_AGENTS;

  function commit() {
    const next = clampAgents(draft.trim() === "" ? agents : typed);
    setDraft(String(next));
    if (next !== agents) patch("population_size", next);
  }

  return (
    <div className="agent-count">
      <h2 className="section-title tight">Quanti consumatori simulare</h2>
      <div className="choice agents" role="radiogroup" aria-label="Numero di consumatori sintetici">
        {AGENT_PRESETS.map(option => (
          <label key={option.value} className={agents === option.value ? "selected" : ""}>
            <input type="radio" name="agents" checked={agents === option.value} onChange={() => patch("population_size", option.value)} />
            <b className="num">{fmt(option.value)}</b>
            <em>{option.label}</em>
            <span>{option.hint}</span>
          </label>
        ))}
      </div>

      <div className="agent-custom">
        <label className="field" htmlFor="agents-custom">{preset ? "Oppure scegli un numero tuo" : "Numero scelto"}
          <input
            id="agents-custom" type="number" inputMode="numeric" min={MIN_AGENTS} max={MAX_AGENTS} step={10} value={draft}
            aria-invalid={invalid} aria-describedby="agents-help"
            onChange={e => {
              setDraft(e.target.value);
              const n = Number(e.target.value);
              if (e.target.value.trim() !== "" && Number.isInteger(n) && n >= MIN_AGENTS && n <= MAX_AGENTS) patch("population_size", n);
            }}
            onBlur={commit}
            onKeyDown={e => {if (e.key === "Enter") commit();}}
          />
        </label>
        <p className="hint" id="agents-help">{invalid ? `Inserisci un numero tra ${MIN_AGENTS} e ${fmt(MAX_AGENTS)}.` : `Da ${MIN_AGENTS} a ${fmt(MAX_AGENTS)} · ${fmt(perBand(agents))} per ogni fascia d'età.`}</p>
      </div>

      <div className="reliability" aria-live="polite">
        <p><b>Affidabilità per età: {reliability.level}.</b> {reliability.summary} <span className="muted">{reliability.change}</span></p>
        <p className="hint">{fmt(evaluationsFor(agents, brief.creatives.length))} valutazioni da completare ({fmt(agents)} agenti × {brief.creatives.length} creatività): più agenti, più tempo.</p>
      </div>

      <details className="more">
        <summary>Cosa cambia con il numero di agenti</summary>
        <ul className="plain">
          <li>{AGENTS_NOTE.same}</li>
          <li>{AGENTS_NOTE.changes}</li>
          <li>{AGENTS_NOTE.limit}</li>
          <li><b>Consigliato: {fmt(RECOMMENDED_AGENTS)} agenti.</b> Rispetto a 120 dimezzi l&apos;oscillazione delle stime per età; passare da 600 a 1000 la riduce solo di un altro quinto circa, ma richiede due terzi di tempo in più.</li>
        </ul>
      </details>
    </div>
  );
}
