"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useEffect, useMemo, useState} from "react";
import {ArrowDownToLine, LoaderCircle, RefreshCw, RotateCcw} from "lucide-react";
import {Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis} from "recharts";
import {api} from "@/lib/api";
import {Hero} from "@/components/hero";
import {useApp} from "@/components/app-provider";
import {Mark, markColor, markLetter} from "@/components/mark";
import {DivergencePanel, NativeBanner, QualityPanel, ReachPanel, SegmentsPanel} from "@/components/native-panels";
import {PersonaGallery} from "@/components/persona-gallery";
import {NATIVE_BADGE, OUTCOME_LABEL, OUT_OF_DOMAIN, PHASE_LABEL, SIMULATION_NOTE, STATUS_LABEL, TRUST, runLabel, runState} from "@/lib/copy";
import {BANDS, dateTime, euros, fmt, percent} from "@/lib/format";
import {isRunResumable, validCreative} from "@/lib/selection";
import type {Age, Brief, Prediction, Quality, Result, Run, TargetingReport} from "@/lib/types";

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
  const broken = new Set((result.report?.creative_checks ?? []).filter(c => c.status === "problematic").map(c => c.creative_id));
  if (broken.size) {
    const sound = summaries.filter(s => !broken.has(s.id));
    const flagged = summaries.filter(s => broken.has(s.id)).map(s => markLetter(s.index)).join(", ");
    const note = `${broken.size > 1 ? "Le creatività" : "La creatività"} ${flagged} ${broken.size > 1 ? "sono segnalate come problematiche" : "è segnalata come problematica"} e non entra nel confronto.`;
    if (sound.length === 0) return {title: "Nessuna creatività regge", detail: `${note} Riscrivile prima di spendere budget.`, winner: null};
    if (sound.length === 1) return {title: `Regge solo la creatività ${markLetter(sound[0].index)}`, detail: `CTR atteso ${percent(sound[0].ctr)}. ${note}`, winner: sound[0].index};
    const rest = verdict(sound, {...result, report: result.report && {...result.report, creative_checks: []}});
    return {...rest, detail: `${rest.detail} ${note}`};
  }
  const ranked = [...summaries].sort((a, b) => b.ctr - a.ctr);
  const [top, second] = ranked;
  const diff = top.ctr - second.ctr;
  const pair = result.comparison?.pairwise.find(p => [p.a, p.b].includes(top.id) && [p.a, p.b].includes(second.id));
  const partial = result.completion_status !== "complete";
  if (pair?.decision === "out_of_domain") {
    const leader = pair.model_leader ? summaries.find(s => s.id === pair.model_leader) : null;
    return {
      title: "Nessun vincitore verificato",
      detail: `${leader ? `Il modello indica la creatività ${markLetter(leader.index)} in vantaggio di ${fmt(Math.abs(pair.difference_pp), 2)} punti di CTR. ` : ""}${OUT_OF_DOMAIN}`,
      winner: null
    };
  }
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
  const router = useRouter();
  const {runNames, setError, setBrief, refresh, rememberRunWinner} = useApp();
  const [run, setRun] = useState<Run | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [active, setActive] = useState("");
  const [busy, setBusy] = useState("");
  const [targetingReport, setTargetingReport] = useState<TargetingReport | null>(null);

  const scenarioId = run?.scenario_id;
  useEffect(() => {
    if (!scenarioId) return;
    let stopped = false;
    api<{targeting_report?: TargetingReport}>(`/scenarios/${scenarioId}`).then(s => {if (!stopped) setTargetingReport(s.targeting_report ?? null);}).catch(() => {});
    return () => {stopped = true;};
  }, [scenarioId]);

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
  // Riporta i dati nel modulo per ripetere la simulazione cambiando solo ciò che serve.
  async function repeat() {
    if (!run) return;
    setBusy("repeat");
    try {
      const scenario = await api<{brief: Brief}>(`/scenarios/${run.scenario_id}`);
      if (!scenario.brief) throw new Error("I dati di partenza non sono disponibili per questa simulazione.");
      setError(""); setBrief(scenario.brief); router.push("/");
    } catch (e) {setError((e as Error).message); setBusy("");}
  }

  if (!run) return <div className="empty"><LoaderCircle className="spin" size={28} aria-hidden="true" /><h1>Carico la simulazione…</h1></div>;

  const state = runState(run);
  const inProgress = ["queued", "running"].includes(run.status);
  const native = result?.mode === "agent_native" || run.mode === "agent_native";
  const nativeReport = result?.report?.native;
  const quality: Quality | undefined = result?.report?.reaction_quality ?? result?.behavior?.reaction_quality;
  const order = summaries.map(x => x.id);
  const complete = run.completion_status === "complete";
  const v = result && summaries.length ? verdict(summaries, result) : null;
  const reactions = result?.behavior?.events.filter(e => e.ad_id === selected).slice(0, 4) || [];
  const title = runLabel(run, runNames);
  const heading = v ? v.title : inProgress ? "Simulazione in corso" : state.label;

  return (
    <div className="results">
      <Hero
        title={<>{v?.winner !== null && v?.winner !== undefined && <Mark index={v.winner} size={40} onDark />}{heading}</>}
        lead={v?.detail}
      >
        {v?.trust && <p className="trust">{v.trust}</p>}
        <p className="hero-meta"><span className={`badge ${state.tone}`}>{state.label}</span>{native && <span className="badge wait">{NATIVE_BADGE}</span>} {runNames[run.id] ? `${title} · ` : ""}{dateTime(run.created_at)}</p>
      </Hero>

      {(!complete || inProgress) && (
        <section className="progress" aria-label="Avanzamento">
          <div className="progress-line"><span>{inProgress && PHASE_LABEL[run.phase] ? PHASE_LABEL[run.phase] : STATUS_LABEL[run.status] || run.status}</span><b className="num">{fmt(run.progress)}%</b></div>
          <div className="bar" role="progressbar" aria-valuenow={run.progress} aria-valuemin={0} aria-valuemax={100}><span style={{width: `${run.progress}%`}} /></div>
          <p className="muted">{native && run.phase === "personas" ? `${fmt(run.persona_cards_done ?? 0)} di ${run.persona_cards_total ? fmt(run.persona_cards_total) : "…"} schede scritte` : `${fmt(run.completed_policies)} di ${run.required_policies ? fmt(run.required_policies) : "…"} ${native ? "reazioni" : "valutazioni"}`}. La pagina si aggiorna da sola.</p>
          {native && run.performance && <p className="muted" aria-live="polite">{run.phase === "personas"
            ? `${fmt(run.performance.cards?.attempts ?? 0)} tentativi · ${fmt(run.performance.cards?.rejected ?? 0)} scarti · ${fmt(run.performance.cards?.cache_hits ?? 0)} riusi dalla cache`
            : `${fmt(run.performance.reactions?.cache_hits ?? 0)} riusi di reazioni dalla cache`}</p>}
          {run.error && <p className="warn">{run.error}</p>}
          {run.status === "waiting_for_runtime" && <p className="muted">I numeri qui sotto sono una stima statistica dai dati storici. Per far reagire i consumatori simulati <Link href="/settings">prepara il motore AI</Link> e poi riprendi la simulazione.</p>}
          <div className="row">
            {isRunResumable(run) && <button className="button secondary" onClick={() => post(`/simulations/${run.id}/resume`)} disabled={!!busy}><RefreshCw size={18} aria-hidden="true" /> Riprendi dove si era fermata</button>}
            {inProgress && <button className="button ghost" onClick={() => post(`/simulations/${run.id}/cancel`)} disabled={!!busy}>Annulla</button>}
          </div>
        </section>
      )}

      {native && <NativeBanner />}
      {result?.report?.creative_checks?.filter(c => c.message).map(c => <p key={c.creative_id} className="warn" role="alert">{c.message}</p>)}
      {result && summaries.length > 0 && <div className="results-grid">
        <section className="results-main">
          <div className="table-scroll">
            <table className="compare">
              <thead><tr><th>Creatività</th><th className="r">CTR atteso</th>{native && <th className="r hide-s">Dati storici</th>}<th className="r">Costo ogni 1.000 viste</th><th className="r hide-s">Clic attesi</th></tr></thead>
              <tbody>
                {summaries.map(s => (
                  <tr key={s.id} className={v?.winner === s.index ? "winner" : ""}>
                    <th scope="row"><span className="mark-label"><Mark index={s.index} />Creatività {markLetter(s.index)}</span>{v?.winner === s.index ? <em>consigliata</em> : null}</th>
                    <td className="r num">{percent(s.ctr)}</td>
                    {native && <td className="r num hide-s">{nativeReport ? percent(nativeReport.divergence.find(d => d.ad_id === s.id)?.reference_ctr ?? 0) : "–"}</td>}
                    <td className="r num">{euros(s.cpm)}</td>
                    <td className="r num hide-s">{fmt(s.clicks, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row">
            <button className="button secondary" onClick={() => exportRun("aggregate")} disabled={!!busy}><ArrowDownToLine size={18} aria-hidden="true" /> {complete ? "Scarica i numeri (CSV)" : "Scarica la stima preliminare"}</button>
            {complete && <button className="button ghost" onClick={() => exportRun("report")} disabled={!!busy}>Scarica il report</button>}
            <button className="button ghost" onClick={repeat} disabled={!!busy}><RotateCcw size={18} aria-hidden="true" /> Ripeti con altri dati</button>
          </div>
        </section>

        <section className="results-side">
          <div className="title-row">
            <h2>Come hanno reagito</h2>
            {summaries.length > 1 && (
              <div className="tabs" role="tablist" aria-label="Creatività">
                {summaries.map(s => (
                  <button key={s.id} role="tab" aria-selected={selected === s.id} className={selected === s.id ? "selected" : ""} onClick={() => setActive(s.id)}><Mark index={s.index} /> {markLetter(s.index)}</button>
                ))}
              </div>
            )}
          </div>
          {result.behavior ? (
            reactions.length ? (
              <ul className="reactions">
                {reactions.map((e, i) => (
                  <li key={i}>
                    <b>{e.outcome ? OUTCOME_LABEL[e.outcome] : e.clicked ? "Ha cliccato" : e.noticed ? "Ha notato l'annuncio" : "Ha ignorato l'annuncio"}</b>
                    <p>{e.explanation || "L'annuncio è stato scorso senza attenzione."}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="muted">Nessuna reazione registrata per questo annuncio.</p>
          ) : <p className="muted">Le reazioni arrivano quando la simulazione è completa.</p>}

          <details className="more">
            <summary>Come cambia per età</summary>
            <p className="muted">Sono ipotesi del simulatore: nei dati non ci sono età osservate.</p>
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
          </details>
        </section>

        {targetingReport?.reach && <div className="results-wide"><ReachPanel report={targetingReport} /></div>}
        {nativeReport && <div className="results-wide"><DivergencePanel divergence={nativeReport.divergence} order={order} /></div>}
        {nativeReport && <div className="results-wide"><SegmentsPanel native={nativeReport} creativeId={selected} /></div>}
        {native && result.cards && <div className="results-wide"><PersonaGallery result={result} creativeId={selected} /></div>}
        {native && quality && <div className="results-wide"><QualityPanel quality={quality} /></div>}

        {result.report && (
          <details className="more">
            <summary>Cosa provare dopo e limiti</summary>
            {result.report.diagnoses.map(d => <p key={d.creative_id} className="top-space"><b>{d.creative_id.replace("creative-", "")}</b>: {d.hypothesis} <span className="muted">{d.experiment.design}</span></p>)}
            <ul className="plain top-space">{result.report.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
          </details>
        )}
      </div>}
      {result && summaries.length > 0 && <p className="note">{SIMULATION_NOTE}</p>}

      {!result && !inProgress && !run.result_key && <p className="muted">Non ci sono ancora risultati per questa simulazione.</p>}
    </div>
  );
}
