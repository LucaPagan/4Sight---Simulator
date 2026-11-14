"use client";

import {useEffect, useRef} from "react";
import {X} from "lucide-react";
import {fmt} from "@/lib/format";
import type {Event, Profile} from "@/lib/types";

export function AgentDialog({agent, events, onClose}: {agent: Profile | null; events: Event[]; onClose: () => void}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (agent && dialog && !dialog.open) dialog.showModal();
    return () => dialog?.close();
  }, [agent]);
  if (!agent) return null;
  const traits: [string, number][] = [
    ["Interesse per la categoria", agent.category_affinity],
    ["Attenzione al prezzo", agent.budget_sensitivity],
    ["Bisogno del prodotto", agent.purchase_need],
    ["Conosce già il brand", agent.brand_familiarity]
  ];
  return (
    <dialog ref={ref} className="dialog" aria-label="Profilo del consumatore" onCancel={onClose} onClose={onClose}>
      <div className="dialog-head">
        <h2>Consumatore {agent.agent_id.split("-").slice(1).join("–")}</h2>
        <button className="icon-button" aria-label="Chiudi" onClick={onClose}><X size={20} /></button>
      </div>
      <p className="muted">{agent.age_band} anni · profilo sintetico, non una persona reale</p>
      <dl className="traits">
        {traits.map(([name, value]) => (
          <div key={name}>
            <dt>{name}</dt>
            <dd><span className="meter"><span style={{width: `${value * 100}%`}} /></span><b className="num">{fmt(value * 100)}%</b></dd>
          </div>
        ))}
      </dl>
      <h3>Cosa ha fatto in questa simulazione</h3>
      {events.length ? (
        <div className="table-scroll">
          <table>
            <thead><tr><th>Giorno</th><th>Creatività</th><th>Esito</th></tr></thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i}><td>{e.date}</td><td>{e.ad_id.replace("creative-", "")}</td><td>{e.clicked ? "Ha cliccato" : e.noticed ? "Ha notato l'annuncio" : "Ha ignorato l'annuncio"}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="muted">Nessuna reazione salvata per questo consumatore.</p>}
    </dialog>
  );
}
