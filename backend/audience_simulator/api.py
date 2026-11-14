import json
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from .cloud import GEMINI_MODELS, save_credentials
from .cloudflare import CLOUDFLARE_MODELS
from .config import settings
from .contracts import SimulationResult, SimulationRun
from .datasets import ASSETS, FILES
from .evidence import ASSUMPTIONS, EVIDENCE
from .reporting import csv_export
from .schemas import (
    CampaignBrief,
    ComparisonRequest,
    CounterfactualRequest,
    Creative,
    ExportRequest,
    PreflightRequest,
    ReactionRequest,
    RuntimeCredentials,
    RuntimeSelection,
    SimulationRequest,
    TargetingAnalyzeRequest,
)
from .service import SimulationService
from .targeting import analyze_targeting


def create_app(service=None):
    svc = service or SimulationService(settings())
    app = FastAPI(
        title="Audience Simulator",
        version="0.1.0",
        description="Laboratorio di campagne con consumatori sintetici; non previsioni demografiche osservate.",
    )
    app.state.service = svc

    @app.middleware("http")
    async def local_origin(request, call_next):
        from urllib.parse import urlparse

        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
            return JSONResponse({"detail": "Origine non consentita"}, status_code=403)
        length = request.headers.get("content-length", "0")
        if not length.isdecimal():
            return JSONResponse({"detail": "Content-Length non valido"}, status_code=400)
        if int(length) > 64 * 1024 * 1024:
            return JSONResponse({"detail": "Upload oltre il limite 64 MB"}, status_code=413)
        return await call_next(request)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Risorsa non trovata"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)[:500]}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]},
            status_code=422,
        )

    @app.get("/api/v1/health")
    def health():
        return {"status": "ok", "local_only": True}

    @app.get("/api/v1/runtime/status")
    def runtime(provider: str = "ollama", model: str | None = None):
        return svc.client(provider, model).status()

    @app.get("/api/v1/runtime/config")
    def runtime_config(provider: str = "gemini"):
        credentials = svc.cloud_credentials(provider)
        models = CLOUDFLARE_MODELS if provider == "cloudflare" else GEMINI_MODELS
        return {
            "provider": provider,
            "configured": bool(credentials["api_key"]),
            "gemini_configured": bool(credentials["api_key"]) if provider == "gemini" else False,
            "account_id": credentials.get("account_id", ""),
            "free_tier_confirmed": credentials["free_tier_confirmed"],
            "requests_per_minute": credentials.get("requests_per_minute", 10),
            "models": [{"id": key, "label": label} for key, label in models.items()],
        }

    @app.post("/api/v1/runtime/config")
    def configure_runtime(request: RuntimeCredentials):
        key = (
            request.api_key.get_secret_value()
            if request.api_key is not None
            else svc.cloud_credentials(request.provider)["api_key"]
        )
        save_credentials(
            svc.cfg.artifact_dir,
            key,
            request.free_tier_confirmed,
            request.requests_per_minute,
            request.provider,
            request.account_id or svc.cloud_credentials(request.provider).get("account_id", ""),
        )
        return runtime_config(request.provider)

    @app.post("/api/v1/runtime/test")
    def test_runtime(request: RuntimeSelection):
        from .agents import evaluation_plan
        from .audience import generate_population

        client = svc.client(request.provider, request.model)
        state = client.status()
        if not state["ready"]:
            raise HTTPException(409, state["error"])
        brief = CampaignBrief(
            name="Prova runtime",
            brand="Brand sintetico",
            product_description="Kit routine di prova, nessun dato riservato",
            vertical="beauty_skincare",
            date_from=date(2026, 11, 16),
            date_to=date(2026, 11, 16),
            creatives=[
                Creative(
                    id="probe",
                    headline="Scopri una routine semplice",
                    primary_text="Un kit di prova per la routine quotidiana.",
                )
            ],
        )
        item = evaluation_plan(brief, generate_population(brief)[:1], state["digest"], client.prompt_version)[
            0
        ]
        response = client.evaluate(item["input"])
        svc.repo.create(
            "llm_benchmark_runs",
            {
                "kind": "single_probe",
                "provider": request.provider,
                "model": client.model,
                "seconds": response["seconds"],
                "prompt_version": client.prompt_version,
                "qualified": False,
            },
        )
        return {
            **response,
            "qualified": False,
            "warning": "Prova tecnica singola con dati sintetici: non dimostra accuratezza delle simulazioni.",
        }

    @app.get("/api/v1/evidence")
    def evidence():
        return {"sources": EVIDENCE, "assumptions": ASSUMPTIONS}

    @app.get("/api/v1/datasets")
    def datasets():
        return svc.repo.list("datasets")

    @app.get("/api/v1/datasets/{resource_id}")
    def dataset(resource_id: str):
        return svc.repo.get("datasets", resource_id)

    @app.post("/api/v1/datasets/bootstrap")
    def bootstrap():
        return svc.import_dataset(svc.cfg.data_dir)

    @app.post("/api/v1/datasets/import")
    async def import_files(files: list[UploadFile]):
        allowed = {Path(f).name: f for f in [*FILES.values(), *ASSETS]}
        if len(files) != 13 or len({f.filename for f in files}) != 13:
            raise HTTPException(422, "Fornisci esattamente i 13 CSV con nomi univoci")
        destination = svc.store.path(f"uploads/{uuid4()}")
        total = 0
        for upload in files:
            filename = upload.filename or ""
            if filename not in allowed:
                raise HTTPException(422, "Nome file non consentito")
            raw = await upload.read(8 * 1024 * 1024 + 1)
            total += len(raw)
            if len(raw) > 8 * 1024 * 1024 or total > 50 * 1024 * 1024:
                raise HTTPException(413, "CSV oltre il limite")
            path = destination / allowed[filename]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        return svc.import_dataset(destination, activate=True)

    @app.get("/api/v1/campaigns")
    def campaigns():
        svc.ensure_kit()
        return svc.repo.list("campaigns")

    @app.post("/api/v1/campaigns", status_code=201)
    def campaign(brief: CampaignBrief):
        return svc.create_scenario(brief.model_dump(mode="json"))

    @app.post("/api/v1/scenarios/{scenario_id}/personas")
    def write_personas(scenario_id: str, request: RuntimeSelection):
        """Write (or reuse from cache) a persona card for every person in the scenario's targeted panel.

        Synchronous: with a hosted model this takes minutes. Progress is cached per person, so a quota error can be resumed."""
        return svc.write_personas(scenario_id, provider=request.provider, model=request.model)

    @app.post("/api/v1/scenarios/{scenario_id}/reactions")
    def run_reactions(scenario_id: str, request: ReactionRequest):
        """Persona reactions to the ad as seen (``agent-reaction-v8``). Synchronous; ``limit`` allows a small smoke test."""
        return svc.run_reactions(
            scenario_id,
            provider=request.provider,
            model=request.model,
            slots=request.slots,
            limit=request.limit,
        )

    @app.post("/api/v1/scenarios/{scenario_id}/quality/counterfactual")
    def counterfactual(scenario_id: str, request: CounterfactualRequest):
        """Metamorphic tests of the reaction prompt: does the decision move when one fact changes? Synchronous."""
        return svc.counterfactuals(
            scenario_id, provider=request.provider, model=request.model, n_pairs=request.n_pairs
        )

    @app.get("/api/v1/simulations/{run_id}/rubric")
    def rubric(run_id: str, n: int = 60, seed: int = 0):
        """Blind rubric CSV for human raters and, apart, the key that maps blind ids back to exposures."""
        if not 1 <= n <= 500:
            raise HTTPException(422, "n deve essere tra 1 e 500")
        return svc.rubric(run_id, n, seed)

    @app.get("/api/v1/targeting/catalog")
    def targeting_catalog():
        """What the targeting form can offer: placements, detailed terms and the person attributes constraints can use."""
        from .meta_catalog import DETAILED_TERMS, PERSONA_ATTRIBUTES, PLACEMENTS

        return {
            "placements": [{"id": k, **v} for k, v in PLACEMENTS.items()],
            "terms": [
                {"id": k, "kind": v["kind"], "label": v["label"], "modelled": bool(v["match"])}
                for k, v in DETAILED_TERMS.items()
            ],
            "attributes": [{"id": k, **v} for k, v in PERSONA_ATTRIBUTES.items()],
        }

    @app.post("/api/v1/targeting/analyze")
    def targeting_analyze(request: TargetingAnalyzeRequest):
        return analyze_targeting(request).model_dump(mode="json")

    @app.get("/api/v1/assets")
    def assets():
        kit = svc.ensure_kit()
        return json.loads(kit["assets"].to_json(orient="records"))

    @app.post("/api/v1/assets", status_code=201)
    def new_asset(creative: Creative):
        return svc.repo.create("assets", creative.model_dump())

    @app.post("/api/v1/scenarios", status_code=201)
    def scenario(brief: CampaignBrief):
        return svc.create_scenario(brief.model_dump(mode="json"))

    @app.get("/api/v1/scenarios/{scenario_id}")
    def get_scenario(scenario_id: str):
        return svc.repo.get("scenarios", scenario_id)

    @app.post("/api/v1/populations/generate")
    def population(request: dict):
        scenario = svc.repo.get("scenarios", request["scenario_id"])
        return svc.repo.get("populations", scenario["population_id"])

    @app.get("/api/v1/populations/{population_id}")
    def get_population(population_id: str):
        return svc.repo.get("populations", population_id)

    @app.post("/api/v1/simulations/preflight")
    def preflight(request: PreflightRequest):
        return svc.preflight(**request.model_dump())

    @app.post("/api/v1/simulations", status_code=202)
    def simulate(request: SimulationRequest):
        scenario = svc.repo.get("scenarios", request.scenario_id)
        if request.mode == "agent_native" and not scenario["brief"].get("targeting"):
            raise HTTPException(422, "La modalità agent_native richiede il targeting nel brief")
        selected = svc.client(request.provider, request.model)
        try:
            run = svc.repo.create_run(
                request.scenario_id,
                request.idempotency_key,
                {
                    "provider": request.provider,
                    "model": selected.model,
                    "mode": request.mode,
                    "slots": request.slots,
                },
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if run["status"] == "queued":
            svc.dispatch(run["id"])
        return run

    @app.get("/api/v1/simulations", response_model=list[SimulationRun])
    def runs():
        return svc.repo.list("simulation_runs")

    @app.get("/api/v1/simulations/{run_id}/status", response_model=SimulationRun)
    def status(run_id: str):
        return svc.repo.get("simulation_runs", run_id)

    @app.post("/api/v1/simulations/{run_id}/cancel")
    def cancel(run_id: str):
        run = svc.repo.get("simulation_runs", run_id)
        if run["completion_status"] == "complete":
            return run
        return svc.repo.update_run(run_id, status="canceled", phase="canceled")

    @app.post("/api/v1/simulations/{run_id}/resume", status_code=202)
    def resume(run_id: str):
        from datetime import UTC, datetime

        run = svc.repo.get("simulation_runs", run_id)
        if run["completion_status"] == "complete":
            return run
        if run["status"] == "running":
            heartbeat = datetime.fromisoformat(run.get("heartbeat_at", run["created_at"]))
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=UTC)
            if (datetime.now(UTC) - heartbeat).total_seconds() < 600:
                raise HTTPException(409, "Simulazione già in corso")
        runtime = svc.client(run.get("provider", "ollama"), run.get("requested_model")).status()
        if run.get("model_digest") and runtime.get("digest") and run["model_digest"] != runtime["digest"]:
            raise HTTPException(409, "Modello cambiato: crea una nuova run")
        svc.repo.update_run(run_id, status="queued", error=None)
        svc.dispatch(run_id)
        return svc.repo.get("simulation_runs", run_id)

    @app.get("/api/v1/predictions", response_model=SimulationResult)
    def predictions(run_id: str):
        try:
            return svc.result(run_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/v1/simulations/{run_id}/agents/{agent_id}")
    def agent(run_id: str, agent_id: str):
        result = svc.result(run_id)
        profile = next((p for p in result["profiles"] if p["agent_id"] == agent_id), None)
        if not profile:
            raise HTTPException(404, "Agente non trovato")
        return {
            "profile": profile,
            "states": [s for s in result.get("behavior", {}).get("states", []) if s["agent_id"] == agent_id],
            "events": [e for e in result.get("behavior", {}).get("events", []) if e["agent_id"] == agent_id],
        }

    @app.post("/api/v1/comparisons")
    def comparison(request: ComparisonRequest):
        result = svc.result(request.run_id)
        if result.get("completion_status") != "complete":
            raise HTTPException(409, "Panel non completo")
        return result["comparison"]

    @app.post("/api/v1/backtests")
    def backtest():
        return svc.backtest()

    @app.get("/api/v1/backtests")
    def backtests():
        return svc.repo.list("validation_runs")

    @app.get("/api/v1/backtests/{report_id}")
    def get_backtest(report_id: str):
        return svc.repo.get("validation_runs", report_id)

    @app.post("/api/v1/official-forecast")
    def official_forecast():
        result = svc.official_forecast()
        svc.store.write_bytes("official/predictions.csv", csv_export(result["predictions"]))
        svc.store.write_bytes("official/age_predictions.csv", csv_export(result["predictions"], age=True))
        return {
            "rows": len(result["predictions"]),
            "completion_status": "preliminary",
            "download_url": "/api/v1/official-forecast/aggregate",
            "age_download_url": "/api/v1/official-forecast/age",
        }

    @app.get("/api/v1/official-forecast/{kind}")
    def download_official(kind: str):
        if kind not in {"aggregate", "age"}:
            raise HTTPException(404, "Export non trovato")
        path = svc.store.path(
            "official/predictions.csv" if kind == "aggregate" else "official/age_predictions.csv"
        )
        if not path.exists():
            raise HTTPException(409, "Genera prima le previsioni")
        return Response(
            path.read_bytes(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
        )

    @app.post("/api/v1/exports", status_code=201)
    def export(request: ExportRequest):
        run = svc.repo.get("simulation_runs", request.run_id)
        if run["completion_status"] != "complete" and not request.allow_preliminary:
            raise HTTPException(409, "Run non completa; export preliminare solo se richiesto esplicitamente")
        result = svc.result(request.run_id)
        export_id = str(uuid4())
        suffix = "json" if request.kind == "report" else "csv"
        key = f"exports/{export_id}.{suffix}"
        raw = (
            json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
            if request.kind == "report"
            else csv_export(result["predictions"], request.kind == "age")
        )
        svc.store.write_bytes(key, raw)
        svc.store.write_json(
            f"exports/{export_id}.meta.json",
            {"key": key, "kind": request.kind, "completion_status": run["completion_status"]},
        )
        return {
            "id": export_id,
            "status": "succeeded",
            "completion_status": run["completion_status"],
            "download_url": f"/api/v1/exports/{export_id}",
        }

    @app.get("/api/v1/exports/{export_id}")
    def download(export_id: str):
        from uuid import UUID

        try:
            UUID(export_id)
            meta = svc.store.read_json(f"exports/{export_id}.meta.json")
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(404, "Export non trovato") from exc
        path = svc.store.path(meta["key"])
        return Response(
            path.read_bytes(),
            media_type="application/json" if meta["kind"] == "report" else "text/csv",
            headers={"Content-Disposition": f'attachment; filename="audience-{export_id}{path.suffix}"'},
        )

    return app


app = create_app()
