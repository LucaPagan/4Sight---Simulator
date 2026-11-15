"use client";

import {useApp} from "@/components/app-provider";
import {RuntimePanel} from "@/components/runtime-panel";

export function SettingsView() {
  const {runtimeChoice, setRuntimeChoice, refresh} = useApp();
  return (
    <div className="page">
      <h1>Motore AI</h1>
      <p className="lead">Scegli dove lavorano i consumatori simulati: sul tuo computer, gratis, oppure in cloud. Per un test normale non devi toccare nulla.</p>
      <div className="cols"><RuntimePanel selection={runtimeChoice} onChange={setRuntimeChoice} onSaved={refresh} /></div>
    </div>
  );
}
