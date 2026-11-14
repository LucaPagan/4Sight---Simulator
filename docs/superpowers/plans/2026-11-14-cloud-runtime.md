# Runtime Gemini Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Alternare Ollama locale e Gemini cloud nei test del panel.
**Architecture:** Client HTTP separati con validatore comune e selezione immutabile per run; credenziali private fuori dai dati di simulazione.
**Tech Stack:** Python/httpx/Pydantic esistenti, React/Next esistenti. Nessuna nuova dipendenza.
**Spec:** docs/CLOUD_RUNTIME_DESIGN.md — scelta Gemini confermata dall'utente.

## Global Constraints
Solo modelli con accesso Free Tier documentato; account senza billing confermato dall'utente, poiché la chiave non espone il tier. Nessun fallback o upgrade automatico. Ogni agente usa il modello selezionato. Cloud non qualifica automaticamente qualità o accuratezza. La run locale in corso deve continuare.

## Review Focus
Cache fra provider, ripresa con selezione diversa, credenziali nei log/report, quote 429 e safety/troncamenti, browser non autorizzato.

## Task 1 — Provider e contratto comune
- [ ] Test RED HTTP Gemini (schema/header, token/latency, JSON extra, output assente/quota).
- [ ] Estrarre schema/validazione da agents.py, aggiungere GeminiClient in cloud.py con REST Interactions stateless.
- [ ] Credenziale locale 0600 e flag Free Tier; GET mostra solo presenza della chiave.
- [ ] GREEN tests/test_cloud.py; lint/mypy.

## Task 2 — Selezione fissata per run
- [ ] Contratti RuntimeSelection/PreflightRequest, create_run idempotente con provider/model.
- [ ] Factory client del servizio; worker/resume/preflight seguono la selezione salvata, mai il selettore corrente UI.
- [ ] Test isolamento e quota/ripresa. Aggiornare CLI benchmark per il provider selezionato.

## Task 3 — UI e consegna
- [ ] Selettore Locale/Gemini, modelli consentiti, password e conferma account Free, prova singola con dati sintetici.
- [ ] Passare selezione a preflight e simulazione; indicarla in risultati e storico.
- [ ] OpenAPI/types, README e Compose config. Suite Python, frontend build/typecheck/unit, smoke servizi.
- [ ] Test cloud reale solo dopo inserimento della chiave. Nessuna promessa su velocità senza misure.
