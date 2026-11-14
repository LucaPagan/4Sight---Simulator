"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {useEffect} from "react";
import type {ReactNode} from "react";
import {ChartColumn, History, Plus, Settings, X} from "lucide-react";
import {useApp} from "@/components/app-provider";
import {PROVIDER_LABEL} from "@/lib/copy";

export function AppShell({children}: {children: ReactNode}) {
  const pathname = usePathname();
  const {runs, runtime, runtimeChoice, error, setError} = useApp();
  useEffect(() => setError(""), [pathname, setError]);

  const latest = runs[0];
  const nav = [
    {href: "/", label: "Nuova simulazione", icon: Plus, active: pathname === "/"},
    {href: latest ? `/results/${latest.id}` : "/runs", label: "Risultati", icon: ChartColumn, active: pathname.startsWith("/results")},
    {href: "/runs", label: "Simulazioni", icon: History, active: pathname === "/runs"},
    {href: "/settings", label: "Impostazioni", icon: Settings, active: pathname.startsWith("/settings")}
  ];
  const engine = PROVIDER_LABEL[runtimeChoice.provider] || "Modello locale";
  const ready = !!runtime?.ready;

  return (
    <div className="shell">
      <aside className="rail">
        <Link href="/" className="wordmark">Audience<br />Simulator</Link>
        <nav aria-label="Navigazione principale">
          {nav.map(item => (
            <Link key={item.label} href={item.href} className={`nav-link${item.active ? " active" : ""}`} aria-current={item.active ? "page" : undefined}>
              <item.icon size={20} aria-hidden="true" />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>
        <Link href="/settings" className="engine-status" title="Apri le impostazioni del motore AI">
          <span className={`dot${ready ? " ready" : ""}`} aria-hidden="true" />
          <span>{engine}<small>{ready ? "Pronto" : "Da verificare"}</small></span>
        </Link>
      </aside>
      <main className="stage" id="contenuto">
        {error && (
          <div className="alert" role="alert">
            <span>{error}</span>
            <button className="icon-button" aria-label="Chiudi l'avviso" onClick={() => setError("")}><X size={18} /></button>
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
