"use client";

import {useEffect, useState} from "react";
import {ArrowDownToLine, ArrowRight, LoaderCircle, Play} from "lucide-react";
import {api} from "@/lib/api";
import {useApp} from "@/components/app-provider";
import {RuntimePanel} from "@/components/runtime-panel";
import {euros, fmt} from "@/lib/format";

type Source = {study_id: string; source_url: string; outcome_measured: string; transferability_warning: string; review_status: string};
const TABS = [{id: "engine", label: "Motore AI"}, {id: "quality", label: "Qualità del modello"}, {id: "sources", label: "Fonti e metodo"}] as const;
type Tab = typeof TABS[number]["id"];

export function SettingsView() {
  const [tab, setTab] = useState<Tab>("engine");
  return (
    <div className="page">
      <h1>Impostazioni</h1>
      <p className="lead">Qui c&apos;è tutto ciò che serve a chi vuole controllare come lavora il simulatore. Per un test normale non devi toccare nulla.</p>
      <div className="tabs" role="tablist" aria-label="Sezioni delle impostazioni">
        {TABS.map(t => <button key={t.id} role="tab" id={`tab-${t.id}`} aria-selected={tab === t.id} aria-controls={`panel-${t.id}`} className={tab === t.id ? "selected" : ""} onClick={() => setTab(t.id)}>{t.label}</button>)}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="tab-panel">
        {tab === "engine" && <EngineTab />}
        {tab === "quality" && <QualityTab />}
        {tab === "sources" && <SourcesTab />}
      </div>
    </div>
  );
}

function EngineTab() {
  const {runtimeChoice, setRuntimeChoice, refresh} = useApp();
  return (
    <>
      <p className="muted">Scegli dove lavorano i consumatori sintetici: sul tuo computer o in cloud. Un modello più veloce non è per forza più accurato.</p>
      <div className="cols"><RuntimePanel selection={runtimeChoice} onChange={setRuntimeChoice} onSaved={refresh} /></div>
    </>
  );
}

function QualityTab() {
  const {setError, reloadAssets} = useApp();
  const [validation, setValidation] = useState<Record<string, unknown> | null>(null);
  const [official, setOfficial] = useState<{download_url: string; age_download_url: string} | null>(null);
  const [busy, setBusy] = useState("");
  useEffect(() => {api<Record<string, unknown>[]>("/backtests").then(v => {if (v.length) setValidation(v[0]);}).catch(() => {});}, []);

  async function backtest() {
    setBusy("backtest"); setError("");
    try {setValidation(await api<Record<string, unknown>>("/backtests", {}));} catch (e) {setError((e as Error).message);} finally {setBusy("");}
  }
  async function forecast() {
    setBusy("forecast"); setError("");
    try {setOfficial(await api("/official-forecast", {}));} catch (e) {setError((e as Error).message);} finally {setBusy("");}
  }
  async function importFiles(files: FileList | null) {
    if (!files?.length) return;
    setBusy("import");
    const form = new FormData();
    Array.from(files).forEach(f => form.append("files", f));
    try {
      const response = await fetch("/api/v1/datasets/import", {method: "POST", body: form});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail);
      setError(""); reloadAssets();
    } catch (e) {setError((e as Error).message);} finally {setBusy("");}
  }

  return (
    <div className="cols">
      <section className="block">
        <h2>Quanto sono precise le stime</h2>
        <p className="muted">Il simulatore confronta le sue previsioni con i dati storici del kit: addestra sulle settimane passate e verifica su quelle successive.</p>
        <button className="button secondary" onClick={backtest} disabled={!!busy}>{busy === "backtest" ? <LoaderCircle className="spin" size={18} aria-hidden="true" /> : <Play size={18} aria-hidden="true" />} Verifica ora</button>
        {validation ? (
          <dl className="metrics">
            <div><dt>Errore medio sul CTR</dt><dd className="num">{fmt(Number(validation.ctr_weighted_mae_pp), 3)} punti</dd></div>
            <div><dt>Errore medio sul costo per 1.000 visualizzazioni</dt><dd className="num">{euros(Number(validation.cpm_mae_eur))}</dd></div>
            <div><dt>Quante volte il CTR reale cade nell&apos;intervallo previsto (90%)</dt><dd className="num">{fmt(Number(validation.ctr_coverage_90) * 100, 1)}%</dd></div>
          </dl>
        ) : <p className="muted">Nessuna verifica ancora eseguita.</p>}
        {validation && <details className="more"><summary>Dati tecnici completi</summary><pre>{JSON.stringify(validation, null, 2)}</pre></details>}
      </section>

      <section className="block">
        <h2>Previsioni per l&apos;hackathon</h2>
        <p className="muted">Genera le 699 righe di previsione del kit (stima preliminare, senza i consumatori simulati).</p>
        <button className="button secondary" onClick={forecast} disabled={!!busy}>{busy === "forecast" ? <LoaderCircle className="spin" size={18} aria-hidden="true" /> : <ArrowDownToLine size={18} aria-hidden="true" />} Genera i file</button>
        {official && <div className="row"><a className="button ghost" href={official.download_url}>Scarica il CSV dei KPI</a><a className="button ghost" href={official.age_download_url}>Scarica il CSV per età</a></div>}
      </section>

      <section className="block">
        <h2>Importa i dati del kit</h2>
        <p className="muted">Seleziona tutti i 13 file CSV originali, compresi i tre degli asset creativi.</p>
        <input type="file" aria-label="Importa i 13 file CSV" accept=".csv" multiple onChange={e => importFiles(e.target.files)} disabled={busy === "import"} />
      </section>
    </div>
  );
}

function SourcesTab() {
  const [sources, setSources] = useState<Source[]>([]);
  useEffect(() => {api<{sources: Source[]}>("/evidence").then(v => setSources(v.sources)).catch(() => {});}, []);
  return (
    <div className="cols">
      <section className="block">
        <h2>Cosa è un dato e cosa è un&apos;ipotesi</h2>
        <dl className="legend">
          <div><dt>Dato del kit</dt><dd>Quello che è scritto nei file storici. È interamente simulato, ma è il metro per verificare le previsioni.</dd></div>
          <div><dt>Stima calibrata</dt><dd>CTR e costo confrontati con lo storico. Se il modello non è stato verificato, lo diciamo.</dd></div>
          <div><dt>Ipotesi</dt><dd>Le fasce d&apos;età e le reazioni dei consumatori dipendono da assunzioni: non sono dati demografici misurati.</dd></div>
        </dl>
        <p className="muted">Se i consumatori simulati non migliorano la verifica sullo storico, la previsione numerica resta quella dei dati storici e il report lo dichiara.</p>
      </section>
      <section className="block">
        <h2>Studi di riferimento</h2>
        {sources.length ? (
          <ul className="rows">
            {sources.map(s => (
              <li key={s.study_id}>
                <a href={s.source_url} target="_blank" rel="noreferrer">
                  <span className="row-main"><b>{s.study_id}</b><small>{s.outcome_measured}. {s.transferability_warning}</small></span>
                  <ArrowRight size={20} aria-hidden="true" />
                </a>
              </li>
            ))}
          </ul>
        ) : <p className="muted">Nessuno studio caricato.</p>}
      </section>
    </div>
  );
}
