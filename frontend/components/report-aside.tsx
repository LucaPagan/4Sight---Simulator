"use client";

import {useRouter} from "next/navigation";
import {useEffect, useState} from "react";
import {RotateCcw} from "lucide-react";
import {api} from "@/lib/api";
import {useApp} from "@/components/app-provider";
import {Mark, markLetter} from "@/components/mark";
import {euros, fmt, shortDate} from "@/lib/format";
import {GLOSSARY} from "@/lib/panel";
import type {Brief, Run} from "@/lib/types";

// A destra del report: i dati con cui è partita la simulazione e, sotto, la legenda dei termini.
export function ReportAside({run}: {run: Run}) {
  const router = useRouter();
  const {setBrief, setError} = useApp();
  const [brief, setScenarioBrief] = useState<Brief | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let stopped = false;
    setScenarioBrief(null); setFailed(false);
    api<{brief: Brief}>(`/scenarios/${run.scenario_id}`)
      .then(s => {if (!stopped) {setScenarioBrief(s.brief ?? null); setFailed(!s.brief);}})
      .catch(() => {if (!stopped) setFailed(true);});
    return () => {stopped = true;};
  }, [run.scenario_id]);

  // Riporta i dati nel modulo "Nuova simulazione" per ripeterla cambiando solo ciò che serve.
  function repeat() {
    if (!brief) return;
    setError("");
    setBrief(brief);
    router.push("/");
  }

  const complete = run.completion_status === "complete";
  const terms = GLOSSARY.filter(item => ["CTR atteso", "Costo per 1.000 visualizzazioni", "Clic attesi", "Spesa attesa", ...(complete ? [] : ["Stima preliminare"])].includes(item.term));

  return (
    <aside className="report-aside" aria-label="Dati della simulazione e legenda">
      <section aria-labelledby="inputs-title">
        <h2 id="inputs-title">La simulazione</h2>
        {brief ? (
          <>
            <dl className="inputs">
              <div><dt>Campagna</dt><dd>{brief.name}<small>{brief.date_from === brief.date_to ? shortDate(brief.date_from) : `${shortDate(brief.date_from)} → ${shortDate(brief.date_to)}`} · {euros(brief.daily_adset_budget_eur, 0)} al giorno</small></dd></div>
              <div><dt>Creatività</dt><dd>
                <ul className="inline-list">
                  {brief.creatives.map((c, i) => (
                    <li key={c.id}><Mark index={i} size={16} /><span><b>{markLetter(i)}</b> {c.headline}</span></li>
                  ))}
                </ul>
              </dd></div>
              <div><dt>Pubblico</dt><dd>{fmt(brief.population_size)} consumatori sintetici</dd></div>
            </dl>
            <button className="button secondary" onClick={repeat}><RotateCcw size={18} aria-hidden="true" /> Ripeti con altri dati</button>
          </>
        ) : failed ? <p className="muted">I dati di partenza non sono disponibili per questa simulazione.</p> : <p className="muted">Carico i dati…</p>}
      </section>

      <section aria-labelledby="legend-title">
        <h2 id="legend-title">Come leggere i numeri</h2>
        <dl className="glossary">
          {terms.map(item => (
            <div key={item.term}><dt>{item.term}</dt><dd>{item.meaning}</dd></div>
          ))}
        </dl>
      </section>
    </aside>
  );
}
