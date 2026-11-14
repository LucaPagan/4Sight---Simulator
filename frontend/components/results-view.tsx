"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";
import {ArrowDownToLine, LoaderCircle, RefreshCw} from "lucide-react";
import {Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import {api} from "@/lib/api";
import {AgentDialog} from "@/components/agent-dialog";
import {useApp} from "@/components/app-provider";
import {Mark, markColor, markLetter} from "@/components/mark";
import {ReportAside} from "@/components/report-aside";
import {COMPLETION_LABEL, SIMULATION_NOTE, STATUS_LABEL, TRUST, runLabel, runState} from "@/lib/copy";
import {BANDS, dateTime, euros, fmt, percent} from "@/lib/format";
import {isRunResumable, validCreative} from "@/lib/selection";
import type {Age, Prediction, Result, Run} from "@/lib/types";

type Summary = {id: string; index: number; ctr: number; cpm: number; clicks: number; spend: number; impressions: number};

export function summarize(predictions: Prediction[]): Summary[] {
  const ids = Array.from(new Set(predictions.map(p => p.ad_id)));
  return ids.map((id, index) => {
    const rows = predictions.filter(p => p.ad_id === id);
    const impressions = rows.reduce((s, p) => s + p.expected_impressions, 0);
    const clicks = rows.reduce((s, p) => s + p.expected_clicks, 0);
    const spend = rows.reduce((s, p) => s + p.expected_spend, 0);
    return {id, index, impressions, clicks, spend, ctr: impressions ? clicks / impressions * 100 : 0, cpm: impressions ? spend / impressions * 1000 : 0};
  });
}

export function verdict(summaries: Summary[], result: Result): {title: string; detail: string; winner: number | null; trust?: string} {
  if (summaries.length === 1) return {title: "Risultato della creatività", detail: `CTR atteso ${percent(summaries[0].ctr)} e costo di ${euros(summaries[0].cpm)} ogni 1.000 visualizzazioni.`, winner: null};
  const ranked = [...summaries].sort((a, b) => b.ctr - a.ctr);
  const [top, second] = ranked;
  const diff = top.ctr - second.ctr;
  const pair = result.comparison?.pairwise.find(p => [p.a, p.b].includes(top.id) && [p.a, p.b].includes(second.id));
  const partial = result.completion_status !== "complete";
  if (pair?.status === "practical_tie" || Math.abs(diff) < 0.005) {
    return {title: "Le creatività si equivalgono", detail: "La differenza è troppo piccola per scegliere: usa altri criteri, come il costo o il messaggio.", winner: null};
  }
  if (pair && !pair.winner) {
    return {title: "Nessun vincitore netto", detail: `${markLetter(top.index)} è avanti di ${fmt(diff, 2)} punti di CTR, ma la differenza resta dentro l'incertezza.`, winner: null};
  }
  const chance = pair ? (pair.a === top.id ? pair.probability_a_better : pair.probability_b_better) : null;
  const trust = partial ? TRUST.preliminary : chance === null ? TRUST.unknown : chance >= 0.9 ? TRUST.strong : chance >= 0.7 ? TRUST.medium : TRUST.weak;
  return {
    trust,
    title: `${partial ? "In vantaggio" : "Vince"} la creatività ${markLetter(top.index)}`,
    detail: `CTR atteso ${percent(top.ctr)} contro ${percent(second.ctr)} della ${markLetter(second.index)}: ${fmt(diff, 2)} punti in più.${partial ? " È una stima preliminare." : ""}`,
    winner: top.index
  };
}

export function ResultsView({runId}: {runId: string}) {
  const {runNames, setError, refresh, rememberRunWinner} = useApp();
  const [run, setRun] = useState<Run | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [active, setActive] = useState("");
  const [busy, setBusy] = useState("");
  const [agentId, setAgentId] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    setRun(null); setResult(null);
    let final = false;
    async function poll() {
      try {
        const current = await api<Run>(`/simulations/${runId}/status`);
        if (stopped) return;
        setRun(current);
        // Con molti agenti il risultato completo pesa diversi MB: una volta ricevuto non si riscarica.
        if (current.result_key && !(final && current.completion_status === "complete")) {
          const data = await api<Result>(`/predictions?run_id=${current.id}`);
          if (!stopped) {setResult(data); final = data.completion_status === "complete";}
        }
      } catch (e) {if (!stopped) setError((e as Error).message);}
    }
    poll();
    const id = setInterval(poll, 2500);
    return () => {stopped = true; clearInterval(id);};
  }, [runId, setError]);

  const summaries = useMemo(() => (result ? summarize(result.predictions) : []), [result]);
  const selected = validCreative(result?.predictions || [], active);
  const winnerIndex = result && summaries.length ? verdict(summaries, result).winner : null;
  useEffect(() => {if (winnerIndex !== null && result?.completion_status === "complete") rememberRunWinner(runId, winnerIndex);}, [winnerIndex, result?.completion_status, runId, rememberRunWinner]);
  const current = summaries.find(s => s.id === selected);
  const ageRows: Age[] = useMemo(() => {
    const rows = result?.predictions.filter(p => p.ad_id === selected) || [];
    return BANDS.map((band, i) => {
      const relevant = rows.map(p => p.ages[i]).filter(Boolean);
      const impressions = relevant.reduce((s, a) => s + a.expected_impressions, 0);
      const clicks = relevant.reduce((s, a) => s + a.clicks_estimate, 0);
      return {age_band: band, impression_share: 0, expected_impressions: impressions, clicks_estimate: clicks, expected_spend: relevant.reduce((s, a) => s + a.expected_spend, 0), ctr_estimate: impressions ? clicks / impressions * 100 : 0, ctr_range: relevant.length ? [Math.min(...relevant.map(a => a.ctr_range[0])), Math.max(...relevant.map(a => a.ctr_range[1]))] : [0, 0], evidence_level: "modeled_assumption"};
    });
  }, [result, selected]);

  async function post(path: string) {
    if (!run) return;
    setBusy(path);
    try {setRun(await api<Run>(path, {})); refresh();} catch (e) {setError((e as Error).message);} finally {setBusy("");}
  }
  async function exportRun(kind: string) {
    if (!run) return;
    setBusy("export");
    try {
      const value = await api<{download_url: string}>("/exports", {run_id: run.id, kind, allow_preliminary: run.completion_status !== "complete"});
      window.open(value.download_url, "_blank", "noopener");
    } catch (e) {setError((e as Error).message);} finally {setBusy("");}
  }

  if (!run) return <div className="empty"><LoaderCircle className="spin" size={28} aria-hidden="true" /><h1>Carico la simulazione…</h1></div>;

  const state = runState(run);
  const inProgress = ["queued", "running"].includes(run.status);
  const complete = run.completion_status === "complete";
  const v = result && summaries.length ? verdict(summaries, result) : null;
  const agentEvents = agentId ? result?.behavior?.events.filter(e => e.agent_id === agentId) || [] : [];
  const agent = agentId ? result?.profiles.find(p => p.agent_id === agentId) || null : null;
  const reactions = result?.behavior?.events.filter(e => e.ad_id === selected).slice(0, 6) || [];
  const title = runLabel(run, runNames);

  return (
    <div className="results-layout">
    <div className="results">
      <header className="results-head">
        <div>
          <h1 className="verdict">{v?.winner !== null && v?.winner !== undefined && <Mark index={v.winner} size={34} />}{v ? v.title : inProgress ? "Simulazione in corso" : state.label}</h1>
          {v && <p className="lead">{v.detail}</p>}
          {v?.trust && <p className="trust">{v.trust}</p>}
        </div>
        <div className="head-side"><span className={`badge ${state.tone}`}>{state.label}</span><span className="muted">{runNames[run.id] ? `${title} · ` : ""}{dateTime(run.created_at)}</span></div>
      </header>

      {(!complete || inProgress) && (
        <section className="progress" aria-label="Avanzamento">
          <div className="progress-line"><span>{STATUS_LABEL[run.status] || run.status}</span><b className="num">{fmt(run.progress)}%</b></div>
          <div className="bar" role="progressbar" aria-valuenow={run.progress} aria-valuemin={0} aria-valuemax={100}><span style={{width: `${run.progress}%`}} /></div>
          <p className="muted">{fmt(run.completed_policies)} di {run.required_policies ? fmt(run.required_policies) : "…"} valutazioni completate. La pagina si aggiorna da sola.</p>
          {run.error && <p className="warn">{run.error}</p>}
          <div className="row">
            {isRunResumable(run) && <button className="button secondary" onClick={() => post(`/simulations/${run.id}/resume`)} disabled={!!busy}><RefreshCw size={18} aria-hidden="true" /> Riprendi dove si era fermata</button>}
            {inProgress && <button className="button ghost" onClick={() => post(`/simulations/${run.id}/cancel`)} disabled={!!busy}>Annulla</button>}
          </div>
        </section>
      )}

      {result && summaries.length > 0 && <>
        <section>
          <h2 className="section-title">Le creatività a confronto</h2>
          <div className="table-scroll">
            <table className="compare">
              <thead><tr><th>Creatività</th><th className="r">CTR atteso</th><th className="r">Costo per 1.000 visualizzazioni</th><th className="r hide-s">Clic attesi</th><th className="r">Spesa attesa</th></tr></thead>
              <tbody>
                {summaries.map(s => (
                  <tr key={s.id} className={v?.winner === s.index ? "winner" : ""}>
                    <th scope="row"><span className="mark-label"><Mark index={s.index} />Creatività {markLetter(s.index)}</span>{v?.winner === s.index ? <em>consigliata</em> : null}</th>
                    <td className="r num">{percent(s.ctr)}</td>
                    <td className="r num">{euros(s.cpm)}</td>
                    <td className="r num hide-s">{fmt(s.clicks, 1)}</td>
                    <td className="r num">{euros(s.spend)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="note">{SIMULATION_NOTE} Il CTR è calibrato sui dati storici del kit. Il numero di agenti non cambia questi valori.</p>
          <div className="row">
            <button className="button secondary" onClick={() => exportRun("aggregate")} disabled={!!busy}><ArrowDownToLine size={18} aria-hidden="true" /> {complete ? "Scarica i numeri (CSV)" : "Scarica la stima preliminare"}</button>
            {complete && <button className="button ghost" onClick={() => exportRun("report")} disabled={!!busy}>Scarica il report completo</button>}
          </div>
        </section>

        <section>
          <div className="title-row sec">
            <h2>Come cambia per età</h2>
            {summaries.length > 1 && (
              <div className="tabs" role="tablist" aria-label="Creatività">
                {summaries.map(s => (
                  <button key={s.id} role="tab" aria-selected={selected === s.id} className={selected === s.id ? "selected" : ""} onClick={() => setActive(s.id)}><Mark index={s.index} /> {markLetter(s.index)}</button>
                ))}
              </div>
            )}
          </div>
          <p className="muted">Ipotesi del simulatore: nei dati non ci sono età osservate, quindi leggi le differenze come indicazioni.</p>
          <div className="chart" role="img" aria-label={`CTR atteso per fascia d'età, creatività ${markLetter(current?.index ?? 0)}`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={ageRows} margin={{top: 12, right: 8, left: 0, bottom: 0}}>
                <CartesianGrid vertical={false} stroke="var(--line)" />
                <XAxis dataKey="age_band" axisLine={false} tickLine={false} tick={{fill: "var(--ink-2)", fontSize: 14}} />
                <YAxis axisLine={false} tickLine={false} width={52} tickFormatter={x => `${fmt(x, 1)}%`} tick={{fill: "var(--ink-2)", fontSize: 14}} />
                <Tooltip cursor={{fill: "var(--ground)"}} formatter={value => [`${fmt(Number(value), 2)}%`, "CTR atteso"]} contentStyle={{borderRadius: 4, border: "1px solid var(--line)", fontSize: 14}} />
                <Bar dataKey="ctr_estimate" isAnimationActive={false} fill={markColor(current?.index ?? 0)} radius={[2, 2, 0, 0]} maxBarSize={64} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details className="more">
            <summary>Mostra i numeri per fascia</summary>
            <div className="table-scroll">
              <table>
                <caption className="sr-only">CTR atteso per fascia d&apos;età</caption>
                <thead><tr><th>Fascia</th><th className="r">CTR atteso</th><th className="r">Intervallo</th><th className="r">Visualizzazioni</th><th className="r">Clic</th></tr></thead>
                <tbody>
                  {ageRows.map(a => (
                    <tr key={a.age_band}><th scope="row">{a.age_band}</th><td className="r num">{percent(a.ctr_estimate)}</td><td className="r num">{fmt(a.ctr_range[0], 2)}–{fmt(a.ctr_range[1], 2)}%</td><td className="r num">{fmt(a.expected_impressions)}</td><td className="r num">{fmt(a.clicks_estimate, 1)}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>

        <section>
          <h2 className="section-title">Come hanno reagito i consumatori</h2>
          {result.behavior ? (
            reactions.length ? (
              <ul className="reactions">
                {reactions.map((e, i) => (
                  <li key={i}>
                    <div className="reaction-top">
                      <b>{e.clicked ? "Ha cliccato" : e.noticed ? "Ha notato l'annuncio" : "Ha ignorato l'annuncio"}</b>
                      <button className="link" onClick={() => setAgentId(e.agent_id)}>Chi è</button>
                    </div>
                    <p>{e.explanation || "Nessuna spiegazione: l'annuncio è stato scorso senza attenzione."}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="muted">Nessuna reazione registrata per questa creatività.</p>
          ) : <p className="muted">Le reazioni dei consumatori compaiono quando tutte le valutazioni sono completate.</p>}
        </section>

        {(result.comparison || result.report || result.behavior) && (
          <details className="more">
            <summary>Dettagli e limiti</summary>
            {result.comparison && (
              <div>
                <h3>Confronto a coppie</h3>
                <ul className="plain">
                  {result.comparison.pairwise.map((p, i) => (
                    <li key={i}><b>{p.a.replace("creative-", "")} contro {p.b.replace("creative-", "")}</b>: {p.winner ? `in vantaggio ${p.winner.replace("creative-", "")}` : p.status === "practical_tie" ? "pareggio" : "nessun vincitore netto"}, differenza di {fmt(p.difference_pp, 2)} punti.</li>
                  ))}
                </ul>
              </div>
            )}
            {result.behavior?.raw_panel.length ? (
              <div>
                <h3>Cosa dicono solo i consumatori simulati</h3>
                <ul className="plain">{result.behavior.raw_panel.map(r => <li key={r.ad_id}><b>{r.ad_id.replace("creative-", "")}</b>: CTR del panel {percent(r.raw_panel_ctr)}, non calibrato sui dati storici.</li>)}</ul>
              </div>
            ) : null}
            {result.report && (
              <div>
                <h3>Cosa provare dopo</h3>
                {result.report.diagnoses.map(d => <p key={d.creative_id}><b>{d.creative_id.replace("creative-", "")}</b>: {d.hypothesis} <span className="muted">{d.experiment.design}</span></p>)}
                <h3>Limiti</h3>
                <ul className="plain">{result.report.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
              </div>
            )}
            <p className="muted">Stato della simulazione: {COMPLETION_LABEL[run.completion_status] || run.completion_status}. <Link href="/settings">Come si calcola</Link></p>
          </details>
        )}
      </>}

      {!result && !inProgress && !run.result_key && <p className="muted">Non ci sono ancora risultati per questa simulazione.</p>}
      <AgentDialog agent={agent} events={agentEvents} onClose={() => setAgentId(null)} />
    </div>
    <ReportAside run={run} />
    </div>
  );
}
