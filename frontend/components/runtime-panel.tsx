"use client";
import {useCallback, useEffect, useState} from "react";
import {Cloud, Download, LoaderCircle, Radio, RefreshCw, ShieldCheck} from "lucide-react";
import {api} from "@/lib/api";

export type RuntimeChoice = {provider: "ollama" | "gemini" | "cloudflare"; model: string};
type Config = {configured: boolean; free_tier_confirmed: boolean; requests_per_minute: number; account_id: string};
type Probe = {seconds: number; tokens: number; qualified: boolean; evaluation: unknown; warning: string; estimated_neurons?: number|null};
const MODELS = {
  gemini: [{id:"gemini-3.5-flash-lite",label:"Gemini 3.5 Flash-Lite · velocità"},{id:"gemini-3.8-flash",label:"Gemini 3.8 Flash · da confrontare"}],
  cloudflare: [{id:"@cf/google/gemma-4-26b-a4b-it",label:"Gemma 4 26B A4B · bilanciato"},{id:"@cf/zai-org/glm-4.7-flash",label:"GLM 4.7 Flash · confronto"}]
};

export function RuntimeSelector({value, onChange}: {value: RuntimeChoice; onChange: (value: RuntimeChoice)=>void}) {
  const [localModel, setLocalModel] = useState("Caricamento…");
  useEffect(() => {
    if (value.provider !== "ollama") return;
    let stopped = false;
    setLocalModel("Caricamento…");
    api<{selected_model: string}>("/runtime/status?provider=ollama").then(status => {
      if (!stopped) setLocalModel(status.selected_model);
    }).catch(() => {if (!stopped) setLocalModel("Non disponibile");});
    return () => {stopped = true;};
  }, [value.provider]);
  return <div className="form-grid"><label>Motore degli agenti<select value={value.provider} onChange={e=>{const provider=e.target.value as RuntimeChoice["provider"];onChange({provider,model:provider==="ollama"?"":MODELS[provider][0].id});}}><option value="ollama">Locale · Ollama</option><option value="gemini">Cloud · Google Gemini</option><option value="cloudflare">Cloud · Cloudflare Workers Free</option></select></label>{value.provider==="ollama"&&<label>Modello locale<input readOnly value={localModel}/></label>}{value.provider!=="ollama"&&<label>Modello cloud<select value={value.model} onChange={e=>onChange({...value,model:e.target.value})}>{MODELS[value.provider].map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</select></label>}</div>;
}

type LocalStatus = {available: boolean; ready: boolean; selected_model: string; recommended_model?: string; error: string | null; models?: {name: string; size?: number}[]};
type Pull = {status: "idle" | "downloading" | "done" | "error"; model?: string; completed?: number; total?: number; message?: string};
const gb = (bytes?: number) => bytes ? `${(bytes / 1e9).toFixed(1).replace(".", ",")} GB` : "";

// Il motore locale ha tre stati: Ollama spento, modello mancante, pronto. Ogni stato dice cosa fare.
export function LocalEngine({onChange}: {onChange: () => void}) {
  const [status, setStatus] = useState<LocalStatus | null>(null);
  const [pull, setPull] = useState<Pull>({status: "idle"});
  const [error, setError] = useState("");
  const load = useCallback(() => {
    api<LocalStatus>("/runtime/status?provider=ollama").then(s => {setStatus(s); onChange();}).catch(() => setStatus(null));
    api<Pull>("/runtime/pull").then(setPull).catch(() => {});
  }, [onChange]);
  useEffect(() => {load(); const id = setInterval(load, pull.status === "downloading" ? 1500 : 5000); return () => clearInterval(id);}, [load, pull.status]);
  async function download() {
    setError("");
    try {setPull(await api<Pull>("/runtime/pull", {model: status?.recommended_model}));} catch (e) {setError((e as Error).message);}
  }
  const model = status?.recommended_model ?? "qwen3.5:4b";
  const percent = pull.total ? Math.round(100 * (pull.completed ?? 0) / pull.total) : 0;
  return (
    <section className="panel" aria-live="polite">
      <div className="panel-heading"><Download size={20} /><h2>Modello sul tuo computer</h2>
        <span className={`badge ${status?.ready ? "" : "wait"}`}>{status?.ready ? "PRONTO" : status?.available ? "MODELLO DA SCARICARE" : "OLLAMA NON ATTIVO"}</span></div>
      {!status && <p className="muted">Controllo…</p>}
      {status?.ready && <p>Sta funzionando: <strong>{status.selected_model}</strong>. Non devi fare altro.</p>}
      {status && !status.available && (
        <>
          <p>Per usare un modello sul tuo computer serve <strong>Ollama</strong>, gratuito.</p>
          <ol className="steps">
            <li>Scaricalo da <a href="https://ollama.com/download" target="_blank" rel="noreferrer">ollama.com/download</a> e aprilo.</li>
            <li>Torna qui: il resto lo facciamo noi.</li>
          </ol>
          <p className="muted small-text">Nel frattempo l&apos;app funziona già, con una stima statistica dai dati storici (senza le reazioni dei consumatori simulati).</p>
        </>
      )}
      {status?.available && !status.ready && (
        <>
          <p>Ollama è attivo, ma manca il modello consigliato: <strong>{model}</strong> (circa 3,3 GB, un solo download).</p>
          {pull.status === "downloading" ? (
            <>
              <div className="bar" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}><span style={{width: `${percent}%`}} /></div>
              <p className="muted small-text">{pull.total ? `${percent}% · ${gb(pull.completed)} di ${gb(pull.total)}` : pull.message || "Avvio"}</p>
            </>
          ) : <button className="button primary" onClick={download}><Download size={16} />Scarica {model}</button>}
          {pull.status === "error" && <p role="alert" className="error-banner">{pull.message}</p>}
          {error && <p role="alert" className="error-banner">{error}</p>}
        </>
      )}
      <button className="button ghost" onClick={load}><RefreshCw size={16} />Ricontrolla</button>
    </section>
  );
}

export function RuntimePanel({selection, onChange, onSaved}: {selection: RuntimeChoice; onChange: (value:RuntimeChoice)=>void; onSaved: ()=>void}) {
  const [config,setConfig]=useState<Config|null>(null);
  const [key,setKey]=useState("");
  const [account,setAccount]=useState("");
  const [free,setFree]=useState(false);
  const [rpm,setRpm]=useState(10);
  const [busy,setBusy]=useState("");
  const [error,setError]=useState("");
  const [note,setNote]=useState("");
  const [probe,setProbe]=useState<Probe|null>(null);
  const provider=selection.provider==="ollama"?"gemini":selection.provider;
  const isCf=provider==="cloudflare";
  const name=isCf?"Cloudflare Workers AI":"Google AI Studio";
  const quotaUrl=isCf?"https://dash.cloudflare.com/":"https://aistudio.google.com/rate-limit";
  useEffect(()=>{
    let stopped=false;
    setConfig(null);setKey("");setNote("");setError("");setProbe(null);
    api<Config>(`/runtime/config?provider=${provider}`).then(c=>{if(!stopped){setConfig(c);setFree(c.free_tier_confirmed);setRpm(c.requests_per_minute);setAccount(c.account_id||"");}}).catch(e=>{if(!stopped)setError(e.message);});
    return ()=>{stopped=true;};
  },[provider]);
  async function save() {
    setBusy("save");setError("");setNote("");
    try {const c=await api<Config>("/runtime/config",{provider,api_key:key||undefined,account_id:isCf?account:undefined,free_tier_confirmed:free,requests_per_minute:rpm});setConfig(c);setKey("");setNote("Configurazione salvata. La chiave è stata cifrata e resta nel backend.");onSaved();} catch(e){setError((e as Error).message);}finally{setBusy("");}
  }
  async function test() {
    setBusy("test");setError("");setProbe(null);
    try {setProbe(await api<Probe>("/runtime/test",{...selection,model:selection.model||null}));onSaved();}catch(e){setError((e as Error).message);}finally{setBusy("");}
  }
  return <><section className="panel"><div className="panel-heading"><Radio size={20}/><h2>Dove lavorano i consumatori simulati</h2></div><RuntimeSelector value={selection} onChange={v=>{setProbe(null);onChange(v);}}/><p className="muted top-space">La scelta vale per le nuove simulazioni.</p></section>{selection.provider==="ollama"&&<LocalEngine onChange={onSaved}/>}{selection.provider!=="ollama"&&<section className="panel"><div className="panel-heading"><Cloud size={20}/><h2>{name}</h2><span className="badge">{config?.configured?"CREDENZIALI PRESENTI":"DA CONFIGURARE"}</span></div>{isCf&&<><p>Quota gratuita rinnovabile: <strong>10.000 Neurons al giorno</strong>, reset alle 00:00 UTC. Non è illimitata: il numero di agenti dipende dai token elaborati.</p><label className="top-space">Account ID Cloudflare<input value={account} maxLength={32} pattern="[a-fA-F0-9]{32}" onChange={e=>setAccount(e.target.value)} placeholder="32 caratteri esadecimali"/></label><p className="muted small-text">Dashboard → Workers AI → Use REST API: copia Account ID e crea il token con il template Workers AI.</p></>}<label className="top-space">{isCf?"API token Cloudflare":"Chiave API Gemini"}<input type="password" autoComplete="off" spellCheck={false} value={key} onChange={e=>setKey(e.target.value)} placeholder={config?.configured?"Già salvata · lascia vuoto per conservarla":"Incolla qui la chiave, non nella chat"}/></label><p className="muted small-text">Il segreto viene salvato solo cifrato (AES + firma di integrità), con la chiave di cifratura in una cartella privata fuori dal progetto; non compare mai in report, database, log e storage S3. <a href={isCf?"https://dash.cloudflare.com/":"https://aistudio.google.com/apikey"} target="_blank" rel="noreferrer">Apri {name} ↗</a></p><details className="more"><summary>Avanzate</summary><label className="range-label">Massimo richieste al minuto<input type="number" min={1} max={60} value={rpm} onChange={e=>setRpm(Number(e.target.value))}/></label><p className="muted small-text">Tieni un valore entro le quote del tuo account. Se la quota finisce, la simulazione si ferma e si può riprendere.</p></details><label className="checkbox-label"><input type="checkbox" checked={free} onChange={e=>setFree(e.target.checked)}/>{isCf?"Confermo che uso il piano Workers Free, senza upgrade automatico.":"Confermo che la chiave appartiene a un progetto Free Tier senza fatturazione attiva."}</label><div className="note-box"><ShieldCheck size={18}/><p>Il brief e i profili sintetici vengono inviati a {isCf?"Cloudflare":"Google"}. Il piano dell’account non è verificabile dalla chiave: su un piano a pagamento gli extra possono generare costi. L’app non attiva upgrade e non usa modelli a pagamento come fallback. <a href={quotaUrl} target="_blank" rel="noreferrer">Quote dell’account ↗</a> · <a href={isCf?"https://developers.cloudflare.com/workers-ai/platform/pricing/":"https://aistudio.google.com/docs/terms"} target="_blank" rel="noreferrer">{isCf?"Allocazione gratuita":"Condizioni dati Free Tier"} ↗</a></p></div><button className="button primary" disabled={!!busy||(!key&&!config?.configured)||(isCf&&account.length!==32)} onClick={save}>{busy==="save"&&<LoaderCircle size={16} className="spin"/>}Salva configurazione</button></section>}<section className="panel"><div className="panel-heading"><Radio size={20}/><h2>Prova il motore</h2></div><p className="muted">Una valutazione di prova, senza dati della tua campagna.</p><button className="button secondary top-space" disabled={!!busy} onClick={test}>{busy==="test"?<LoaderCircle size={16} className="spin"/>:<Radio size={16}/>}Prova ora</button>{probe&&<><p className="top-space"><strong>Funziona.</strong> Risposta in {probe.seconds.toFixed(1)} secondi.</p></>}{note&&<p role="status" className="note-box">{note}</p>}{error&&<p role="alert" className="error-banner">{error}</p>}</section></>;
}
