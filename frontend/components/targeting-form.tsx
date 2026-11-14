"use client";

import {useEffect, useMemo, useState} from "react";
import {Plus, X} from "lucide-react";
import {api} from "@/lib/api";
import {useApp} from "@/components/app-provider";
import {ATTRIBUTE_LABEL, BID, CUSTOM_KIND, DEVICES, GENDER, OPTIMIZATION, TERM_KIND, TERM_MODE, URBANICITY, WEEKDAYS, valueLabel} from "@/lib/copy";
import {fmt} from "@/lib/format";
import {HOURS, hoursBetween, isTargetingActive, listToText, textToList, toPayload} from "@/lib/targeting";
import type {TargetingReport, TargetingSpec} from "@/lib/types";

type Device = "ios" | "android" | "desktop";
type Term = {id: string; mode?: "include" | "narrow" | "exclude"};
type Custom = NonNullable<TargetingSpec["custom_audiences"]>[number];

// Anteprima di come il testo viene letto: stesso calcolo che userà la simulazione.
function useReading(brief: ReturnType<typeof useApp>["brief"]) {
  const [reading, setReading] = useState<TargetingReport | null>(null);
  const [problem, setProblem] = useState("");
  const targeting = brief.targeting;
  const active = isTargetingActive(targeting);
  const key = JSON.stringify([targeting, brief.country, brief.vertical]);
  useEffect(() => {
    if (!active || !targeting) {setReading(null); setProblem(""); return;}
    let stale = false;
    const timer = setTimeout(() => {
      api<TargetingReport>("/targeting/analyze", {country: brief.country, vertical: brief.vertical, device: "mobile", targeting: toPayload(targeting)})
        .then(r => {if (!stale) {setReading(r); setProblem("");}})
        .catch(e => {if (!stale) {setReading(null); setProblem((e as Error).message);}});
    }, 600);
    return () => {stale = true; clearTimeout(timer);};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, active]);
  return {reading, problem, active};
}

export function TargetingSection() {
  const {brief, patchTargeting, clearTargeting, catalog} = useApp();
  const t: TargetingSpec = brief.targeting ?? {};
  const {reading, problem, active} = useReading(brief);
  const detailed = (t.detailed ?? []) as Term[];
  const manual = t.advantage_placements === false;
  const termsByKind = useMemo(() => {
    const groups: Record<string, NonNullable<typeof catalog>["terms"]> = {};
    for (const term of catalog?.terms ?? []) (groups[term.kind] ||= []).push(term);
    return groups;
  }, [catalog]);
  const label = (id: string) => catalog?.terms.find(x => x.id === id)?.label ?? id;
  const addTerm = (id: string) => {if (id && !detailed.some(d => d.id === id)) patchTargeting({detailed: [...detailed, {id, mode: "include"}]});};
  const setDevice = (device: Device, on: boolean) => {
    const current = (t.device_platforms ?? []) as Device[];
    patchTargeting({device_platforms: on ? [...current, device] : current.filter(d => d !== device)});
  };
  const setPlacement = (id: string, on: boolean) => {
    const current = t.placements ?? [];
    patchTargeting({placements: (on ? [...current, id] : current.filter(p => p !== id)) as TargetingSpec["placements"]});
  };
  const weekdays = t.weekdays ?? [];
  const hours = t.hours ?? [];
  const hourFrom = hours.length ? hours[0] : 0;
  const hourTo = hours.length ? (hours[hours.length - 1] + 1) % 24 : 0;
  const customs = (t.custom_audiences ?? []) as Custom[];
  const bidNeedsAmount = t.bid_strategy && t.bid_strategy !== "lowest_cost";

  return (
    <section className="block-form" aria-labelledby="audience-heading">
      <div className="title-row">
        <h2 id="audience-heading">A chi vuoi arrivare</h2>
        {active && <button className="link" onClick={clearTargeting}>Rimuovi il pubblico</button>}
      </div>
      <p className="hint">Facoltativo. Descrivi il pubblico come faresti su Instagram o Facebook: la simulazione sceglie persone come quelle che l&apos;annuncio raggiungerebbe davvero, non solo quelle che vorresti.</p>

      <label className="field wide">Descrivi il pubblico con parole tue
        <textarea rows={2} value={t.audience_intent ?? ""} onChange={e => patchTargeting({audience_intent: e.target.value})} placeholder="Es. chi ha un cane e vive da solo" />
      </label>

      {problem && <p className="warn" role="alert">{problem}</p>}
      {reading && <Reading reading={reading} detailed={detailed} label={label} onAdd={addTerm} />}

      <details className="more">
        <summary>Impostazioni come in Ads Manager</summary>
        <div className="fields">
          <label className="field">Età da
            <input type="number" min={18} max={65} value={t.age_min ?? 18} onChange={e => patchTargeting({age_min: Number(e.target.value)})} />
          </label>
          <label className="field">Età fino a
            <input type="number" min={18} max={65} value={t.age_max ?? 65} onChange={e => patchTargeting({age_max: Number(e.target.value)})} />
          </label>
          <label className="field">Genere
            <select value={t.gender ?? "all"} onChange={e => patchTargeting({gender: e.target.value as TargetingSpec["gender"]})}>
              {Object.entries(GENDER).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
            </select>
          </label>
          <label className="field">Zona
            <select value={t.urbanicity ?? "any"} onChange={e => patchTargeting({urbanicity: e.target.value as TargetingSpec["urbanicity"]})}>
              {Object.entries(URBANICITY).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
            </select>
          </label>
          <label className="field wide">Regioni o città (separate da virgole)
            <input value={listToText(t.regions)} onChange={e => patchTargeting({regions: textToList(e.target.value)})} placeholder="Es. Lombardia, Lazio" />
          </label>
        </div>

        <fieldset className="check-group">
          <legend>Dispositivi</legend>
          {Object.entries(DEVICES).map(([id, text]) => (
            <label key={id} className="checkbox-label"><input type="checkbox" checked={(t.device_platforms ?? []).includes(id as Device)} onChange={e => setDevice(id as Device, e.target.checked)} />{text}</label>
          ))}
          <p className="hint">Nessuna scelta significa tutti i dispositivi.</p>
        </fieldset>

        <fieldset className="check-group">
          <legend>Dove compare</legend>
          <label className="checkbox-label"><input type="checkbox" checked={!manual} onChange={e => patchTargeting({advantage_placements: e.target.checked})} />Posizionamenti automatici (Advantage+)</label>
          {manual && (
            <div className="check-grid">
              {(catalog?.placements ?? []).map(p => (
                <label key={p.id} className="checkbox-label"><input type="checkbox" checked={(t.placements ?? []).includes(p.id as never)} onChange={e => setPlacement(p.id, e.target.checked)} />{p.label}</label>
              ))}
            </div>
          )}
        </fieldset>

        <fieldset className="check-group">
          <legend>Targeting dettagliato</legend>
          <label className="field">Aggiungi interessi, comportamenti o dati demografici
            <select value="" onChange={e => addTerm(e.target.value)}>
              <option value="">Scegli…</option>
              {Object.entries(termsByKind).map(([kind, terms]) => (
                <optgroup key={kind} label={TERM_KIND[kind] ?? kind}>
                  {terms.map(term => <option key={term.id} value={term.id} disabled={detailed.some(d => d.id === term.id)}>{term.label.replace(/^[^:]+: /, "")}</option>)}
                </optgroup>
              ))}
            </select>
          </label>
          {detailed.length > 0 && (
            <ul className="term-list">
              {detailed.map((term, i) => (
                <li key={term.id}>
                  <span>{label(term.id)}{catalog?.terms.find(x => x.id === term.id)?.modelled === false && <small className="muted"> · nessun effetto sul pubblico simulato</small>}</span>
                  <select aria-label={`Modalità di ${label(term.id)}`} value={term.mode ?? "include"} onChange={e => patchTargeting({detailed: detailed.map((d, j) => (j === i ? {...d, mode: e.target.value as Term["mode"]} : d))})}>
                    {Object.entries(TERM_MODE).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
                  </select>
                  <button className="icon-button" aria-label={`Togli ${label(term.id)}`} onClick={() => patchTargeting({detailed: detailed.filter((_, j) => j !== i)})}><X size={18} aria-hidden="true" /></button>
                </li>
              ))}
            </ul>
          )}
          <label className="checkbox-label"><input type="checkbox" checked={!!t.advantage_audience} onChange={e => patchTargeting({advantage_audience: e.target.checked})} />Advantage+ audience: consenti di arrivare anche fuori da queste scelte</label>
        </fieldset>

        <fieldset className="check-group">
          <legend>Limite di frequenza</legend>
          <label className="checkbox-label"><input type="checkbox" checked={!!t.frequency_cap} onChange={e => patchTargeting({frequency_cap: e.target.checked ? {max_impressions: 3, days: 7} : null})} />Limita quante volte una persona vede l&apos;annuncio</label>
          {t.frequency_cap && (
            <div className="fields">
              <label className="field">Al massimo
                <input type="number" min={1} max={50} value={t.frequency_cap.max_impressions} onChange={e => patchTargeting({frequency_cap: {...t.frequency_cap!, max_impressions: Number(e.target.value)}})} />
              </label>
              <label className="field">Ogni (giorni)
                <input type="number" min={1} max={30} value={t.frequency_cap.days ?? 7} onChange={e => patchTargeting({frequency_cap: {...t.frequency_cap!, days: Number(e.target.value)}})} />
              </label>
            </div>
          )}
        </fieldset>

        <details className="more">
          <summary>Altre impostazioni (registrate, senza effetto sul pubblico simulato)</summary>
          <p className="hint">Esistono anche su Ads Manager. Qui restano nel brief e il rapporto le elenca, ma non cambiano le persone simulate.</p>
          <div className="fields">
            <label className="field">Obiettivo di ottimizzazione
              <select value={t.optimization_goal ?? "link_clicks"} onChange={e => patchTargeting({optimization_goal: e.target.value as TargetingSpec["optimization_goal"]})}>
                {Object.entries(OPTIMIZATION).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
              </select>
            </label>
            <label className="field">Strategia di offerta
              <select value={t.bid_strategy ?? "lowest_cost"} onChange={e => patchTargeting({bid_strategy: e.target.value as TargetingSpec["bid_strategy"]})}>
                {Object.entries(BID).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
              </select>
            </label>
            {bidNeedsAmount && (
              <label className="field">Importo (€)
                <input type="number" min={0} inputMode="decimal" value={t.bid_amount_eur ?? ""} onChange={e => patchTargeting({bid_amount_eur: e.target.value === "" ? null : Number(e.target.value)})} />
              </label>
            )}
            <label className="field wide">Lingue (separate da virgole)
              <input value={listToText(t.languages)} onChange={e => patchTargeting({languages: textToList(e.target.value)})} placeholder="Es. it, en" />
            </label>
          </div>
          <label className="checkbox-label"><input type="checkbox" checked={!!t.wifi_only} onChange={e => patchTargeting({wifi_only: e.target.checked})} />Solo con Wi-Fi</label>
          <fieldset className="check-group">
            <legend>Giorni della settimana</legend>
            <div className="check-grid">
              {WEEKDAYS.map((day, i) => (
                <label key={day} className="checkbox-label"><input type="checkbox" checked={weekdays.includes(i)} onChange={e => patchTargeting({weekdays: e.target.checked ? [...weekdays, i].sort() : weekdays.filter(d => d !== i)})} />{day}</label>
              ))}
            </div>
          </fieldset>
          <div className="fields">
            <label className="field">Dalle ore
              <select value={hourFrom} onChange={e => patchTargeting({hours: hoursBetween(Number(e.target.value), hourTo)})}>{HOURS.map(h => <option key={h} value={h}>{fmt(h)}:00</option>)}</select>
            </label>
            <label className="field">Alle ore
              <select value={hourTo} onChange={e => patchTargeting({hours: hoursBetween(hourFrom, Number(e.target.value))})}>{HOURS.map(h => <option key={h} value={h}>{fmt(h)}:00</option>)}</select>
            </label>
          </div>
          <p className="hint">Dalle e alle ore uguali significa tutto il giorno.</p>
          {customs.map((c, i) => (
            <div className="fields" key={i}>
              <label className="field">Tipo
                <select value={c.kind} onChange={e => patchTargeting({custom_audiences: customs.map((x, j) => (j === i ? {...x, kind: e.target.value as Custom["kind"]} : x))})}>
                  {Object.entries(CUSTOM_KIND).map(([id, text]) => <option key={id} value={id}>{text}</option>)}
                </select>
              </label>
              <label className="field">Descrizione
                <input value={c.description} onChange={e => patchTargeting({custom_audiences: customs.map((x, j) => (j === i ? {...x, description: e.target.value} : x))})} placeholder="Chi sono queste persone" />
              </label>
              <button className="link remove" onClick={() => patchTargeting({custom_audiences: customs.filter((_, j) => j !== i)})}>Togli</button>
            </div>
          ))}
          {customs.length < 5 && <button className="button ghost" onClick={() => patchTargeting({custom_audiences: [...customs, {kind: "custom", description: ""}]})}><Plus size={18} aria-hidden="true" /> Aggiungi un pubblico salvato</button>}
        </details>
      </details>
    </section>
  );
}

function Reading({reading, detailed, label, onAdd}: {reading: TargetingReport; detailed: Term[]; label: (id: string) => string; onAdd: (id: string) => void}) {
  const warnings = reading.notes.filter(n => n.severity !== "info" && n.code !== "not_applied");
  return (
    <div className="reading" aria-live="polite">
      <h3>Come l&apos;ho capito</h3>
      {reading.constraints.length > 0 ? (
        <ul className="chips">
          {reading.constraints.map((c, i) => <li key={i} className="chip">{c.negate ? "non " : ""}{c.values.map(v => valueLabel(c.attribute, v)).join(" o ")}</li>)}
        </ul>
      ) : <p className="muted">Nessun vincolo riconosciuto nel testo: la simulazione userà le impostazioni qui sotto.</p>}
      {reading.unrecognized_intent && <p className="muted">Non ho capito: «{reading.unrecognized_intent}».</p>}
      {reading.proxies.filter(p => !p.meta_direct).map((p, i) => (
        <div key={i} className="proxy">
          <p><b>{ATTRIBUTE_LABEL[p.attribute] ?? p.attribute}: {p.values.map(v => valueLabel(p.attribute, v)).join(" o ")}.</b> Su Instagram e Facebook non si può scegliere direttamente: si usano interessi e dati demografici vicini.</p>
          {p.suggested_terms.length > 0 && (
            <div className="row">
              {p.suggested_terms.map(id => (
                <button key={id} className="button ghost" disabled={detailed.some(d => d.id === id)} onClick={() => onAdd(id)}><Plus size={16} aria-hidden="true" /> {label(id)}</button>
              ))}
            </div>
          )}
          {p.expected_precision !== null && p.expected_precision !== undefined && <p className="hint">Con le scelte fatte, circa il {fmt(p.expected_precision * 100)}% di chi vedrebbe l&apos;annuncio ha davvero questa caratteristica (ipotesi, non misura).</p>}
        </div>
      ))}
      {warnings.length > 0 && <ul className="notes">{warnings.map((n, i) => <li key={i} className={n.severity}>{n.message}</li>)}</ul>}
    </div>
  );
}
