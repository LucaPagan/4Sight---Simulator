"use client";

import {useState} from "react";
import {ATTRIBUTE_LABEL, NATIVE_WARNING, QUALITY_FLAG, QUALITY_WARNING, SEGMENT_LABEL, segmentValue, valueLabel} from "@/lib/copy";
import {BANDS, fmt, percent} from "@/lib/format";
import {Mark, markLetter} from "@/components/mark";
import type {Divergence, Native, Quality, Result, TargetingReport} from "@/lib/types";

const pct = (share: number, digits = 0) => `${fmt(share * 100, digits)}%`;

export function NativeBanner() {
  return (
    <aside className="native-banner" role="note">
      <b>Persone simulate · non validato.</b> {NATIVE_WARNING}
    </aside>
  );
}

// Chi vedrebbe davvero l'annuncio, rispetto a chi vorresti raggiungere.
export function ReachPanel({report}: {report: TargetingReport}) {
  const reach = report.reach;
  if (!reach) return null;
  const warnings = report.notes.filter(n => n.severity !== "info");
  const infos = report.notes.filter(n => n.severity === "info" && ["ideal_share", "setting_not_modelled", "term_not_modelled"].includes(n.code));
  return (
    <section className="reach" aria-labelledby="reach-heading">
      <h2 id="reach-heading">Chi raggiunge davvero</h2>
      {reach.ideal_share_in_reached !== null && reach.ideal_share_in_reached !== undefined && (
        <div className="ideal">
          <p><b className="num big-number">{pct(reach.ideal_share_in_reached)}</b> di chi vedrebbe l&apos;annuncio rientra nel pubblico che volevi.</p>
          <div className="meter" role="img" aria-label={`Target ideale: ${pct(reach.ideal_share_in_reached)} tra chi vede l'annuncio, ${pct(reach.ideal_share_in_base ?? 0)} nella popolazione di partenza`}>
            <span style={{width: `${Math.min(100, (reach.ideal_share_in_reached ?? 0) * 100)}%`}} />
          </div>
          <p className="hint">Nella popolazione di partenza sono il {pct(reach.ideal_share_in_base ?? 0)}{reach.lift ? `: la scelta del pubblico li rende ${fmt(reach.lift, 1)} volte più presenti` : ""}. Stima basata su ipotesi dichiarate, non su dati di consegna.</p>
        </div>
      )}
      {reach.constraints.length > 0 && (
        <table className="plain-table">
          <thead><tr><th>Caratteristica voluta</th><th className="r">Tra chi vede l&apos;annuncio</th><th className="r hide-s">Nella popolazione</th></tr></thead>
          <tbody>
            {reach.constraints.map((c, i) => (
              <tr key={i}>
                <th scope="row">{ATTRIBUTE_LABEL[c.attribute] ?? c.attribute}: {c.negate ? "non " : ""}{c.values.map(v => valueLabel(c.attribute, v)).join(" o ")}</th>
                <td className="r num">{pct(c.share_in_reached)}</td>
                <td className="r num hide-s">{pct(c.share_in_base)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details className="more">
        <summary>Età di chi vede l&apos;annuncio</summary>
        <ul className="bars" aria-label="Quote per fascia d'età">
          {BANDS.map((band, i) => (
            <li key={band}><span>{band}</span><span className="meter small"><span style={{width: `${reach.age_shares[i] * 100}%`}} /></span><b className="num">{pct(reach.age_shares[i])}</b></li>
          ))}
        </ul>
      </details>
      {(warnings.length > 0 || infos.length > 0) && (
        <details className="more" open={warnings.length > 0}>
          <summary>Avvisi sul pubblico ({warnings.length + infos.length})</summary>
          <ul className="notes">{[...warnings, ...infos].map((n, i) => <li key={i} className={n.severity}>{n.message}</li>)}</ul>
        </details>
      )}
      <p className="hint">Controllo del pannello: {reach.audit.status === "ok" ? "nessun problema rilevato" : reach.audit.warnings.join("; ")}. Distanza media tra le persone {fmt(reach.audit.mean_distance ?? 0, 2)}.</p>
    </section>
  );
}

// Le decisioni degli agenti contro il riferimento storico: quanto distano, senza dire chi ha ragione.
export function DivergencePanel({divergence, order}: {divergence: Divergence[]; order: string[]}) {
  return (
    <section className="divergence" aria-labelledby="divergence-heading">
      <h2 id="divergence-heading">Persone simulate e dati storici</h2>
      <p className="muted">Il CTR qui sopra viene dalle decisioni delle persone. Il riferimento storico è un altro modo di stimarlo: se si discostano molto, almeno uno dei due è sbagliato per questa campagna.</p>
      <div className="table-scroll">
        <table className="plain-table">
          <thead><tr><th>Creatività</th><th className="r">Persone simulate</th><th className="r">Dati storici</th><th className="r hide-s">Intervallo storico</th><th /></tr></thead>
          <tbody>
            {divergence.map(d => {
              const index = Math.max(0, order.indexOf(d.ad_id));
              return (
                <tr key={d.ad_id}>
                  <th scope="row"><span className="mark-label"><Mark index={index} />Creatività {markLetter(index)}</span></th>
                  <td className="r num">{percent(d.agent_native_ctr)}</td>
                  <td className="r num">{percent(d.reference_ctr)}</td>
                  <td className="r num hide-s">{percent(d.reference_interval[0])} – {percent(d.reference_interval[1])}</td>
                  <td>{d.diverges ? <span className="badge wait">Molto diverso</span> : <span className="badge">Compatibile</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function SegmentsPanel({native, creativeId}: {native: Native; creativeId: string}) {
  const entry = native.breakdowns.find(b => b.ad_id === creativeId) ?? native.breakdowns[0];
  const dimensions = Object.keys(entry?.segments ?? {}).filter(d => (entry.segments[d] ?? []).length > 1);
  const [dimension, setDimension] = useState("");
  const active = dimensions.includes(dimension) ? dimension : dimensions[0];
  if (!entry || !active) return null;
  const rows = entry.segments[active];
  const top = Math.max(...rows.map(r => r.ctr_pct), 0.0001);
  return (
    <section aria-labelledby="segments-heading">
      <div className="title-row">
        <h2 id="segments-heading">Chi reagisce di più</h2>
        <label className="inline-select">Per
          <select value={active} onChange={e => setDimension(e.target.value)}>
            {dimensions.map(d => <option key={d} value={d}>{SEGMENT_LABEL[d] ?? d}</option>)}
          </select>
        </label>
      </div>
      <div className="table-scroll">
        <table className="plain-table">
          <thead><tr><th>{SEGMENT_LABEL[active] ?? active}</th><th className="r">Persone</th><th className="r hide-s">Notano</th><th className="r">CTR</th><th aria-hidden="true" /></tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.key}>
                <th scope="row">{active === "age_band" ? r.key : segmentValue(active, r.key)}{r.low_sample && <em className="faint"> pochi casi</em>}</th>
                <td className="r num">{fmt(r.personas)}</td>
                <td className="r num hide-s">{pct(r.notice_rate)}</td>
                <td className="r num">{percent(r.ctr_pct)}</td>
                <td className="bar-cell"><span className="meter small"><span style={{width: `${(r.ctr_pct / top) * 100}%`}} /></span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">Con poche persone per gruppo le differenze sono rumore: i gruppi con meno di 8 persone sono segnati.</p>
    </section>
  );
}

export function QualityPanel({quality, result, onRubric, busy}: {quality: Quality; result: Result; onRubric: () => void; busy: boolean}) {
  const flags = quality.flags;
  const dependence = Object.entries(quality.profile_dependence ?? {}).sort((a, b) => b[1].notice - a[1].notice).slice(0, 3);
  return (
    <section aria-labelledby="quality-heading">
      <h2 id="quality-heading">Quanto sono credibili le reazioni</h2>
      {flags.length === 0 && quality.warnings.length === 0 ? <p>Nessun segnale automatico di problemi. Non significa che siano realistiche: i controlli sono solo lessicali.</p> : (
        <ul className="notes">
          {flags.map(f => <li key={f} className="warning">{QUALITY_FLAG[f] ?? f}</li>)}
          {quality.warnings.map(w => <li key={w} className="warning">{QUALITY_WARNING[w] ?? w}</li>)}
        </ul>
      )}
      <dl className="metrics">
        <div><dt>Reazioni che riguardano l&apos;annuncio visto</dt><dd className="num">{pct(quality.grounded_share)}</dd></div>
        <div><dt>Persone che sembrano interessate</dt><dd className="num">{pct(quality.positive_share)}</dd></div>
        <div><dt>Attenzione media</dt><dd className="num">{pct(quality.mean_notice, 1)}</dd></div>
        {dependence.length > 0 && <div><dt>Cosa fa cambiare le decisioni di più</dt><dd>{dependence.map(([k, v]) => `${SEGMENT_LABEL[k] ?? k} (${pct(v.notice)})`).join(", ")}</dd></div>}
      </dl>
      <p className="hint">Controlli automatici sulle risposte del modello. Per sapere se somigliano a persone vere servono valutatori umani.</p>
      {result.mode === "agent_native" && <button className="button secondary" onClick={onRubric} disabled={busy}>Scarica la rubrica per i valutatori</button>}
    </section>
  );
}
