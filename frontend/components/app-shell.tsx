"use client";

import Link from "next/link";
import {usePathname} from "next/navigation";
import {useEffect} from "react";
import type {ReactNode} from "react";
import {History, Plus, Settings, X} from "lucide-react";
import {useApp} from "@/components/app-provider";
import {PROVIDER_LABEL} from "@/lib/copy";

export function AppShell({children}: {children: ReactNode}) {
  const pathname = usePathname();
  const {runtime, runtimeChoice, error, setError} = useApp();
  useEffect(() => setError(""), [pathname, setError]);

  const nav = [
    {href: "/", label: "Nuova", icon: Plus, active: pathname === "/"},
    {href: "/runs", label: "Simulazioni", icon: History, active: pathname === "/runs" || pathname.startsWith("/results")},
    {href: "/settings", label: "Impostazioni", icon: Settings, active: pathname.startsWith("/settings")}
  ];
  const engine = PROVIDER_LABEL[runtimeChoice.provider] || "Modello locale";
  const ready = !!runtime?.ready;

  return (
    <div className="shell">
      <header className="topbar">
        <Link href="/" className="wordmark">Audience Simulator</Link>
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
          <span>{engine} · {ready ? "pronto" : "da verificare"}</span>
        </Link>
      </header>
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
