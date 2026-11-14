"use client";

import Link from "next/link";
import {useEffect} from "react";
import {api} from "@/lib/api";
import {summarize, verdict} from "@/components/results-view";
import type {Result} from "@/lib/types";
import {ChevronRight, Plus} from "lucide-react";
import {useApp} from "@/components/app-provider";
import {Mark, markLetter} from "@/components/mark";
import {runLabel, runState} from "@/lib/copy";
import {dateTime, fmt} from "@/lib/format";

export function RunsList() {
  const {runs, runNames, runWinners, rememberRunWinner, refresh} = useApp();
  useEffect(() => refresh(), [refresh]);
  // Il vincitore delle simulazioni complete mai aperte si ricava qui, dagli stessi dati dei risultati.
  useEffect(() => {
    let stopped = false;
    runs.filter(r => r.completion_status === "complete" && r.result_key && runWinners[r.id] === undefined).slice(0, 10).forEach(async r => {
      try {
        const data = await api<Result>(`/predictions?run_id=${r.id}`);
        const summaries = summarize(data.predictions);
        const w = summaries.length ? verdict(summaries, data).winner : null;
        if (!stopped && w !== null) rememberRunWinner(r.id, w);
      } catch {/* senza risultati la riga resta senza segno */}
    });
    return () => {stopped = true;};
  }, [runs, runWinners, rememberRunWinner]);
  return (
    <div className="page">
      <h1>Le tue simulazioni</h1>
      <p className="lead">Ogni simulazione resta salvata con i suoi dati, così puoi rileggerla e confrontarla.</p>
      {runs.length ? (
        <ul className="rows">
          {runs.map(run => {
            const state = runState(run);
            return (
              <li key={run.id}>
                <Link href={`/results/${run.id}`}>
                  <span className="row-main"><b>{runLabel(run, runNames)}</b><small>{dateTime(run.created_at)} · {fmt(run.completed_policies)} di {fmt(run.required_policies)} {run.mode === "agent_native" ? "reazioni · persone simulate" : "valutazioni"}</small></span>
                  {runWinners[run.id] !== undefined && <span className="mark-label"><Mark index={runWinners[run.id]} />Vince {markLetter(runWinners[run.id])}</span>}
                  <span className={`badge ${state.tone}`}>{state.label}</span>
                  <ChevronRight size={20} aria-hidden="true" />
                </Link>
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="empty">
          <h2>Nessuna simulazione, per ora</h2>
          <p>La prima che avvii comparirà qui, con il suo stato.</p>
          <Link className="button primary" href="/"><Plus size={18} aria-hidden="true" /> Nuova simulazione</Link>
        </div>
      )}
    </div>
  );
}
