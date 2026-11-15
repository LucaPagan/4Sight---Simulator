import io
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import joblib
import pandas as pd

from .agents import OllamaClient, evaluation_plan
from .audience import age_predictions, generate_population
from .behavior import policy_signals, simulate_panel
from .calibration import apply_ctr_shifts, creative_features, shifts_for
from .cloud import CloudQuotaError, CloudRuntimeError, GeminiClient, credentials_path, read_credentials
from .cloudflare import CloudflareClient
from .config import Settings
from .counterfactual import run_counterfactuals
from .datasets import audit_dataset, load_dataset
from .decision_quality import assess_decisions
from .decision_quality import export_rubric as export_decision_rubric
from .domain import Domain, assess_domain
from .evidence import ASSUMPTIONS, EVIDENCE
from .forecasting import forecast, forecast_new_campaign, train_model_registry, validate_models
from .native_engine import simulate_agent_native
from .performance import stage_metrics
from .persona_cards import BATCH_SIZE, PersonaWriter
from .persona_model import generate_targeted_population
from .reaction_execution import run_reaction_plan
from .reactions import REACTION_PROMPT_VERSION, reaction_plan
from .reporting import audit_predictions, build_report, compare_predictions
from .repository import ArtifactStore, Repository
from .schemas import CampaignBrief, ReachSummary, TargetingAnalyzeRequest
from .stimulus_view import SLOTS
from .targeting import analyze_targeting

CALIBRATION_KEY = "validation/calibration.json"


def reaction_summary(decisions):
    """Mean of the per-100 answers by creative and slot. Descriptive of the model's hypotheses, not a forecast."""
    groups = {}
    for d in decisions:
        groups.setdefault((d["creative_id"], d["slot"]), []).append(d["result"]["decision"])
    return [
        {
            "creative_id": creative,
            "slot": slot,
            "personas": len(items),
            **{
                name: round(sum(i[f"{name}_per_100"] for i in items) / len(items), 2)
                for name in ("skip", "stop", "engage", "click")
            },
        }
        for (creative, slot), items in sorted(groups.items())
    ]


def effective_brief(brief, scenario):
    """The brief the forecast uses: with a sampled targeting, the age mix is the one the ad would reach."""
    reach = (scenario.get("targeting_report") or {}).get("reach")
    if not reach:
        return brief
    shares = [float(x) for x in reach["age_shares"]]
    return brief.model_copy(update={"age_shares": [x / sum(shares) for x in shares]})


class SimulationService:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.repo = Repository(cfg.database_url)
        self.store = ArtifactStore(cfg.artifact_dir, cfg if cfg.s3_endpoint else None)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audience")
        self.cloud_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="audience-cloud")
        self.lock = threading.RLock()
        self.models = None
        self.kit = None
        active = self.store.path("active-dataset.json")
        if active.exists():
            selected = self.store.read_json("active-dataset.json")
            try:
                entry = self.repo.get("datasets", selected["dataset_id"])
                self.cfg.data_dir = Path(entry["path"])
            except KeyError:
                pass

    def cloud_credentials(self, provider="gemini"):
        if credentials_path(self.cfg.artifact_dir, provider).exists():
            return read_credentials(self.cfg.artifact_dir, provider)
        if provider == "cloudflare":
            return {
                "api_key": self.cfg.cloudflare_api_token.get_secret_value(),
                "account_id": self.cfg.cloudflare_account_id,
                "free_tier_confirmed": self.cfg.cloudflare_free_tier_confirmed,
                "requests_per_minute": self.cfg.cloudflare_requests_per_minute,
            }
        return {
            "api_key": self.cfg.gemini_api_key.get_secret_value(),
            "free_tier_confirmed": self.cfg.gemini_free_tier_confirmed,
            "requests_per_minute": self.cfg.gemini_requests_per_minute,
        }

    def client(self, provider="ollama", model=None):
        if provider == "cloudflare":
            credentials = self.cloud_credentials(provider)
            return CloudflareClient(
                credentials["api_key"],
                credentials.get("account_id", ""),
                model or "@cf/google/gemma-4-26b-a4b-it",
                credentials["free_tier_confirmed"],
                credentials.get("requests_per_minute", 30),
                rate_limit_path=self.store.path(".cloudflare-rate-limit"),
            )
        if provider == "gemini":
            credentials = self.cloud_credentials()
            return GeminiClient(
                credentials["api_key"],
                model or "gemini-3.5-flash-lite",
                credentials["free_tier_confirmed"],
                credentials.get("requests_per_minute", 10),
                rate_limit_path=self.store.path(".gemini-rate-limit"),
            )
        if provider != "ollama":
            raise ValueError("Provider non consentito")
        return OllamaClient(self.cfg.ollama_url, model or self.cfg.ollama_model)

    def import_dataset(self, root, activate=False):
        root = Path(root).resolve()
        audit = audit_dataset(root)
        if audit["errors"]:
            raise ValueError("; ".join(audit["errors"]))
        dataset_id = audit["dataset_hash"]
        try:
            entry = self.repo.get("datasets", dataset_id)
        except KeyError:
            with self.repo.transaction():
                entry = self._persist_dataset(root, audit, dataset_id)
        if not entry.get("snapshot_key"):
            from .datasets import ASSETS, FILES

            entry["snapshot_key"] = f"datasets/{dataset_id}/raw"
            for relative in [*FILES.values(), *ASSETS]:
                self.store.write_bytes(
                    f"{entry['snapshot_key']}/{relative}", (root / relative).read_bytes(), "text/csv"
                )
            entry = self.repo.replace("datasets", dataset_id, entry)
        if activate:
            with self.lock:
                self.cfg.data_dir = root
                self.models = self.kit = None
                self.store.write_json("active-dataset.json", {"dataset_id": dataset_id})
        return entry

    def _persist_dataset(self, root, audit, dataset_id):
        from .datasets import ASSETS, FILES

        kit = load_dataset(root)
        snapshot = f"datasets/{dataset_id}/raw"
        for relative in [*FILES.values(), *ASSETS]:
            self.store.write_bytes(f"{snapshot}/{relative}", (root / relative).read_bytes(), "text/csv")
        entry = self.repo.create(
            "datasets",
            {
                "name": "Wevion BigHack · kit simulato",
                "path": str(root),
                "snapshot_key": snapshot,
                "dataset_hash": dataset_id,
                "audit": audit,
            },
            dataset_id,
        )
        for key, table, idcol in [
            ("advertisers", "advertisers", "inserzionista_id"),
            ("campaigns", "campaigns", "campaign_id"),
            ("adsets", "adsets", "adset_id"),
            ("assets", "assets", "asset_id"),
            ("ads", "ads", "ad_id"),
        ]:
            records = []
            for raw in json.loads(kit[key].to_json(orient="records")):
                scoped = {**raw, "dataset_id": dataset_id}
                if key == "adsets":
                    scoped["campaign_id"] = f"{dataset_id}:{raw['campaign_id']}"
                if key == "ads":
                    scoped["adset_id"] = f"{dataset_id}:{raw['adset_id']}"
                    scoped["asset_id"] = f"{dataset_id}:{raw['asset_id']}"
                records.append({"id": f"{dataset_id}:{raw[idcol]}", "payload": scoped})
            self.repo.bulk_create(table, records)
        for key, table in [
            ("history", "daily_observations"),
            ("future", "forecast_rows"),
            ("budgets", "budgets"),
            ("calendar", "calendar"),
            ("cpm_market", "market_benchmarks"),
            ("weekly_market", "market_benchmarks"),
        ]:
            self.repo.bulk_create(
                table,
                [
                    {"payload": {**r, "dataset_id": dataset_id, "source_table": key}}
                    for r in json.loads(kit[key].to_json(orient="records"))
                ],
            )
        for kind, values in [("behavioral_evidence", EVIDENCE), ("assumptions", ASSUMPTIONS)]:
            if not self.repo.list(kind):
                self.repo.bulk_create(kind, [{"payload": value} for value in values])
        self.store.write_json(f"datasets/{dataset_id}/manifest.json", audit)
        return entry

    def ensure_kit(self):
        with self.lock:
            if self.kit is None:
                self.import_dataset(self.cfg.data_dir)
                self.kit = load_dataset(self.cfg.data_dir, validate=True)
            return self.kit

    def get_models(self):
        with self.lock:
            if self.models is None:
                kit = self.ensure_kit()
                dataset_hash = audit_dataset(self.cfg.data_dir)["dataset_hash"]
                key = f"models/{dataset_hash}/aggregate-v4.joblib"
                if self.store.path(key).exists() and self.store.path(key + ".json").exists():
                    manifest = self.store.read_json(key + ".json")
                    raw = self.store.path(key).read_bytes()
                    import hashlib

                    if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
                        raise ValueError("Artefatto modello non integro")
                    self.models = joblib.load(io.BytesIO(raw))
                else:
                    self.models = train_model_registry(kit)
                    buffer = io.BytesIO()
                    joblib.dump(self.models, buffer)
                    import hashlib

                    self.store.write_bytes(key, buffer.getvalue())
                    self.store.write_json(
                        key + ".json",
                        {
                            "sha256": hashlib.sha256(buffer.getvalue()).hexdigest(),
                            "training_cutoff": self.models.cutoff,
                            "dataset_hash": dataset_hash,
                        },
                    )
                    self.repo.create(
                        "model_versions",
                        {
                            "kind": "aggregate",
                            "version": self.models.version,
                            "recipe": self.models.recipe,
                            "training_cutoff": self.models.cutoff,
                            "dataset_hash": dataset_hash,
                            "artifact": key,
                        },
                    )
            return self.models

    def create_scenario(self, payload):
        brief = CampaignBrief.model_validate(payload)
        if not brief.creatives:
            raise ValueError("Aggiungi almeno una creatività")
        dataset = self.import_dataset(self.cfg.data_dir) if self.cfg.data_dir.exists() else None
        campaign = self.repo.create(
            "campaigns",
            {
                "name": brief.name,
                "brand": brief.brand,
                "vertical": brief.vertical,
                "source_type": "user_input",
            },
        )
        self.repo.create(
            "campaign_briefs", {"campaign_id": campaign["id"], "brief": brief.model_dump(mode="json")}
        )
        scenario = self.repo.create(
            "scenarios",
            {
                "campaign_id": campaign["id"],
                "brief": brief.model_dump(mode="json"),
                "version": 1,
                "audience_mode": "theory_based",
                "dataset_id": dataset["id"] if dataset else None,
                "dataset_path": str(self.cfg.data_dir.resolve()),
                "dataset_snapshot": dataset.get("snapshot_key") if dataset else None,
            },
        )
        reach = None
        if brief.targeting is not None:
            profiles, reach = generate_targeted_population(brief)
        else:
            profiles = generate_population(brief)
        population = self.repo.create(
            "populations",
            {"scenario_id": scenario["id"], "seed": brief.seed, "size": len(profiles), "profiles": profiles},
        )
        self.repo.bulk_create(
            "consumer_profiles", [{"payload": {**p, "population_id": population["id"]}} for p in profiles]
        )
        scenario["population_id"] = population["id"]
        if brief.targeting is not None:
            scenario["targeting_report"] = analyze_targeting(
                TargetingAnalyzeRequest(
                    country=brief.country,
                    vertical=brief.vertical,
                    device=brief.device,
                    targeting=brief.targeting,
                ),
                applied_to_population=True,
                reach=ReachSummary.model_validate(reach),
            ).model_dump(mode="json")
        self.repo.replace("scenarios", scenario["id"], scenario)
        return scenario

    def write_personas(self, scenario_id, client=None, provider="ollama", model=None):
        """Stage 2: persona cards for the scenario's panel. Cached per skeleton, so reruns only write what is missing."""
        scenario = self.repo.get("scenarios", scenario_id)
        brief = CampaignBrief.model_validate(scenario["brief"])
        population = self.repo.get("populations", scenario["population_id"])
        client = client or self.client(provider, model)
        runtime = client.status()
        if not runtime["ready"]:
            raise ValueError(runtime.get("error") or "Runtime non pronto")
        writer = PersonaWriter(
            self.repo, client, runtime["digest"], brief.vertical, brief.country, brief.brand
        )
        state = population.get("writer_state", {})

        def checkpoint(done, total):
            self.repo.replace("populations", population["id"], {**population, "writer_state": state})

        cards, report = writer.write(population["profiles"], progress=checkpoint, state=state)
        self.repo.replace(
            "populations",
            population["id"],
            {**population, "cards": cards, "persona_report": report, "writer_state": state},
        )
        return {"population_id": population["id"], "cards": cards, "report": report}

    def run_reactions(
        self, scenario_id, client=None, provider="ollama", model=None, slots=("first",), limit=None
    ):
        """Stage 3 without the simulation engine: persona reactions (``agent-reaction-v8``), cached per exposure.

        Quota errors propagate and finished reactions stay cached. A reaction that stays invalid after one retry is
        counted as failed, never replaced by an invented one."""
        scenario = self.repo.get("scenarios", scenario_id)
        brief = CampaignBrief.model_validate(scenario["brief"])
        population = self.repo.get("populations", scenario["population_id"])
        if not population.get("cards"):
            raise ValueError("Mancano le schede-persona: scrivile prima di simulare le reazioni")
        client = client or self.client(provider, model)
        runtime = client.status()
        if not runtime["ready"]:
            raise ValueError(runtime.get("error") or "Runtime non pronto")
        writer = PersonaWriter(
            self.repo, client, runtime["digest"], brief.vertical, brief.country, brief.brand
        )
        if not all(
            writer.compatible(population["cards"].get(p["agent_id"], {}), p) for p in population["profiles"]
        ):
            self.write_personas(scenario_id, client=client)
            population = self.repo.get("populations", scenario["population_id"])
        plan = reaction_plan(
            brief, population["profiles"], population["cards"], runtime["digest"], slots=tuple(slots)
        )
        selected = plan[:limit] if limit else plan
        execution = run_reaction_plan(
            self.repo,
            client,
            selected,
            runtime["digest"],
            concurrency=self.cfg.ollama_reaction_concurrency if client.provider == "ollama" else 1,
            max_attempts=2,
            max_evaluations=self.cfg.max_evaluations,
            stop_on_invalid=False,
        )
        if execution["error"]:
            raise execution["error"]
        answered = [item for item in selected if item["key"] in execution["decisions"]]
        decisions = [
            {k: item[k] for k in ("agent_id", "creative_id", "slot", "regime", "placement")}
            | {"result": execution["decisions"][item["key"]]}
            for item in answered
        ]
        failed = len(execution["failed"])
        cached = execution["performance"]["cache_hits"]
        return {
            "required": len(plan),
            "evaluated": len(selected),
            "performance": execution["performance"],
            "from_cache": cached,
            "failed": failed,
            "summary": reaction_summary(decisions),
            "quality": assess_decisions(
                [
                    {
                        "key": item["key"],
                        "agent_id": d["agent_id"],
                        "creative_id": d["creative_id"],
                        "slot": d["slot"],
                        "input": item["input"],
                        "decision": d["result"]["decision"],
                    }
                    for item, d in zip(answered, decisions, strict=True)
                ],
                {p["agent_id"]: p for p in population["profiles"]},
            )
            if decisions
            else None,
            "decisions": decisions,
            "evidence": "hypothesis",
            "validated": False,
        }

    def native_preflight(self, scenario_id, client, provider, slots):
        """Cost of an agent_native run: persona cards still to write plus reactions still to ask for."""
        scenario = self.repo.get("scenarios", scenario_id)
        brief = CampaignBrief.model_validate(scenario["brief"])
        population = self.repo.get("populations", scenario["population_id"])
        profiles = population["profiles"]
        runtime = client.status()
        digest = runtime["digest"] or "pending-runtime"
        writer = PersonaWriter(self.repo, client, digest, brief.vertical, brief.country, brief.brand)
        compatible = {}
        accepted = []
        for profile in profiles:
            stored = self.repo.get_card(writer.key(profile)) if runtime["ready"] else None
            card = stored["card"] if stored else {}
            if writer.compatible(card, profile, accepted):
                compatible[profile["agent_id"]] = card
                if card["source"] == "llm":
                    accepted.append(card)
        cards_missing = len(profiles) - len(compatible)
        if not cards_missing:
            plan = reaction_plan(brief, profiles, compatible, digest, slots=tuple(slots))
            required = len(plan)
            cached = sum(bool(self.repo.get_decision(p["key"])) for p in plan) if runtime["ready"] else 0
        else:
            from datetime import timedelta

            from .context import calendar_regime

            regimes = {
                calendar_regime(brief.date_from + timedelta(days=d))
                for d in range((brief.date_to - brief.date_from).days + 1)
            }
            required, cached = len(profiles) * len(brief.creatives) * len(regimes) * len(slots), 0
        new = required - cached
        card_calls = -(-cards_missing // getattr(client, "card_batch_size", BATCH_SIZE))
        timings = [
            r
            for r in self.repo.list("simulation_runs", 200)
            if r.get("completion_status") == "complete"
            and r.get("mode") == "agent_native"
            and r.get("model_digest") == digest
            and r.get("performance", {}).get("reaction_prompt_version") == REACTION_PROMPT_VERSION
            and r.get("performance", {}).get("writer_version") == writer.version
            and r.get("performance", {}).get("concurrency")
            == (self.cfg.ollama_reaction_concurrency if provider == "ollama" else 1)
        ]
        estimate = None
        if len(timings) >= 3:
            import statistics

            card_rates = [
                r["performance"]["cards"]["seconds"] / r["performance"]["cards"]["attempts"]
                for r in timings
                if r["performance"].get("cards", {}).get("attempts", 0)
            ]
            reaction_rates = [
                r["performance"]["reactions"]["seconds"] / r["performance"]["reactions"]["attempts"]
                for r in timings
                if r["performance"].get("reactions", {}).get("attempts", 0)
            ]
            if (not cards_missing or len(card_rates) >= 3) and (not new or len(reaction_rates) >= 3):
                estimate = (statistics.median(card_rates) * cards_missing if cards_missing else 0) + (
                    statistics.median(reaction_rates) * new if new else 0
                )
        return {
            "mode": "agent_native",
            "runtime": runtime,
            "required_policies": required,
            "cached_policies": cached,
            "new_policies": new,
            "persona_cards_to_write": cards_missing,
            "persona_card_calls": card_calls,
            "max_attempts_with_retry": 3 * new + 3 * cards_missing,
            "within_limit": 3 * new <= self.cfg.max_evaluations,
            "estimated_seconds": estimate,
            "timing_observations": len(timings),
            "estimate_note": "Stima da run compatibili; retry e carico possono cambiare la durata."
            if estimate is not None
            else "Misure compatibili insufficienti per stimare la durata.",
            "population_size": len(profiles),
            "slots": list(slots),
            "model": client.model,
            "provider": provider,
            "daily_free_neurons": runtime.get("daily_free_neurons"),
        }

    def counterfactuals(self, scenario_id, client=None, provider="ollama", model=None, n_pairs=12):
        """Metamorphic tests of the reaction prompt on this scenario's panel (see ``counterfactual.py``)."""
        scenario = self.repo.get("scenarios", scenario_id)
        brief = CampaignBrief.model_validate(scenario["brief"])
        population = self.repo.get("populations", scenario["population_id"])
        if not population.get("cards"):
            raise ValueError("Mancano le schede-persona: scrivile prima di eseguire i test contro-fattuali")
        client = client or self.client(provider, model)
        runtime = client.status()
        if not runtime["ready"]:
            raise ValueError(runtime.get("error") or "Runtime non pronto")
        return run_counterfactuals(
            client, brief, population["profiles"], population["cards"], runtime["digest"], self.repo, n_pairs
        )

    def rubric(self, run_id, n=60, seed=0):
        """Blind sample of an agent_native run for human raters. Keep ``key`` apart from the CSV given to raters."""
        result = self.result(run_id)
        if result.get("mode") != "agent_native":
            raise ValueError("La rubrica riguarda le run agent_native")
        records = [
            {
                **{k: s[k] for k in ("key", "agent_id", "creative_id", "slot")},
                "input": s["input"],
                "decision": s["decision"],
            }
            for s in result["decision_snapshot"]
        ]
        return export_decision_rubric(records, n, seed)

    def preflight(
        self, scenario_id, client=None, provider="ollama", model=None, mode="history_forecast", slots=SLOTS
    ):
        if mode == "agent_native":
            return self.native_preflight(scenario_id, client or self.client(provider, model), provider, slots)
        scenario = self.repo.get("scenarios", scenario_id)
        brief = CampaignBrief.model_validate(scenario["brief"])
        profiles = self.repo.get("populations", scenario["population_id"])["profiles"]
        client = client or self.client(provider, model)
        runtime = client.status()
        plan = evaluation_plan(brief, profiles, runtime["digest"] or "pending-runtime", client.prompt_version)
        cached = sum(bool(self.repo.get_policy(p["key"])) for p in plan) if runtime["ready"] else 0
        import numpy as np

        timings = [
            float(p["metrics"]["seconds"])
            for p in self.repo.list("agent_evaluations", 200)
            if p.get("digest") == runtime.get("digest")
            and p.get("input", {}).get("prompt_version") == client.prompt_version
            and p.get("metrics", {}).get("seconds", 0) > 0
        ]
        timings = [t for t in timings if np.isfinite(t)]
        estimate = float(np.median(timings)) * (len(plan) - cached) if len(timings) >= 3 else None
        if estimate is not None and provider in {"gemini", "cloudflare"}:
            estimate = max(estimate, (len(plan) - cached) * client.interval)
        return {
            "runtime": runtime,
            "required_policies": len(plan),
            "cached_policies": cached,
            "new_policies": len(plan) - cached,
            "max_attempts_with_retry": 2 * (len(plan) - cached),
            "within_limit": 2 * (len(plan) - cached) <= self.cfg.max_evaluations,
            "estimated_seconds": estimate,
            "timing_observations": len(timings),
            "estimate_note": "Mediana delle policy recenti con identico modello/digest/prompt; stima indicativa, esclude retry e variazioni di carico."
            if estimate is not None
            else "Misure locali insufficienti per stimare la durata.",
            "population_size": len(profiles),
            "model": client.model,
            "provider": provider,
            "daily_free_neurons": runtime.get("daily_free_neurons"),
        }

    def dispatch(self, run_id):
        if self.cfg.queue_mode == "manual":
            return
        run = self.repo.get("simulation_runs", run_id)
        if run.get("provider", "ollama") == "ollama" and any(
            r["id"] != run_id and r["status"] == "running" and r.get("provider", "ollama") == "ollama"
            for r in self.repo.list("simulation_runs", 1000)
        ):
            self.repo.update_run(
                run_id,
                status="waiting_for_capacity",
                error="Un’altra simulazione locale è in corso. Riprendi dopo il completamento oppure crea un test con Gemini.",
            )
            return
        if self.cfg.queue_mode == "rq":
            from redis import Redis
            from rq import Queue

            Queue(
                "cloud" if run.get("provider") in {"gemini", "cloudflare"} else "default",
                connection=Redis.from_url(self.cfg.redis_url),
            ).enqueue("audience_simulator.worker.run", run_id, job_timeout=86400, job_id=run_id)
        else:
            executor = (
                self.cloud_executor if run.get("provider") in {"gemini", "cloudflare"} else self.executor
            )
            executor.submit(self.execute_run, run_id)

    def rows_for_brief(self, brief):
        kit = self.ensure_kit()
        assets = []
        for c in brief.creatives:
            assets.append(
                {
                    "asset_id": c.id,
                    "vertical": brief.vertical,
                    "leva": c.lever,
                    "formato": c.format,
                    "headline": c.headline,
                    "testo_principale": c.primary_text,
                    "descrizione_visual": c.visual_description,
                    "data_lancio": str(brief.date_from),
                }
            )
        kit = {
            **kit,
            "assets": pd.concat(
                [
                    kit["assets"].loc[~kit["assets"].asset_id.isin([c.id for c in brief.creatives])],
                    pd.DataFrame(assets),
                ],
                ignore_index=True,
            ),
        }
        rows = [
            {
                "data": str(day.date()),
                "piattaforma": brief.platform,
                "vertical": brief.vertical,
                "campaign_id": "user-campaign",
                "adset_id": "user-adset",
                "ad_id": c.id,
                "asset_id": c.id,
                "leva": c.lever,
                "formato": c.format,
                "budget_giornaliero_adset": brief.daily_adset_budget_eur,
            }
            for day in pd.date_range(brief.date_from, brief.date_to)
            for c in brief.creatives
        ]
        return kit, pd.DataFrame(rows)

    def panel_calibration(self, brief, plan, policies, assessment):
        """Calibrated panel shift per creative, or zeros with the reason it was not applied."""
        zero = dict.fromkeys((c.id for c in brief.creatives), 0.0)
        domain = assessment
        info = {"applied": False, "domain_status": domain.status, "benchmark_id": domain.benchmark_id}
        try:
            artifact = self.store.read_json(CALIBRATION_KEY)
        except FileNotFoundError:
            return zero, {**info, "reason": "Nessuna calibrazione appresa su campagne reali."}
        info["gate"] = artifact["gate"]
        if not artifact["gate"]["passed"]:
            return zero, {**info, "reason": "La calibrazione non ha superato la verifica fuori campione."}
        if not domain.verified:
            return zero, {**info, "reason": domain.reason}
        features = {
            c.id: creative_features(
                [
                    {"input": p["input"], "evaluation": policies[p["key"]]}
                    for p in plan
                    if p["creative_id"] == c.id and p["key"] in policies
                ]
            )
            for c in brief.creatives
        }
        shifts = shifts_for(artifact, features)
        return shifts, {
            **info,
            "applied": True,
            "reason": "Spostamento relativo calibrato su campagne escluse.",
        }

    def predict_brief(self, brief, signal_effects=None, ctr_shifts=None):
        kit, frame = self.rows_for_brief(brief)
        predictions, draws = forecast_new_campaign(
            kit, self.get_models(), frame, seed=brief.seed, n_draws=self.cfg.monte_carlo_draws
        )
        # Country/objective adjustment is a benchmark scenario, never a measured demographic auction.
        market = kit["cpm_market"]
        market = market.loc[
            (market.piattaforma == brief.platform) & (market.mese < self.get_models().cutoff[:7])
        ]
        baseline = (
            market.loc[(market.paese == "IT") & (market.obiettivo == "vendite")].sort_values("mese").tail(1)
        )
        target = (
            market.loc[(market.paese == brief.country) & (market.obiettivo == brief.objective)]
            .sort_values("mese")
            .tail(1)
        )
        ratio = (
            float(target.cpm_mediano.iloc[0] / baseline.cpm_mediano.iloc[0])
            if len(target) and len(baseline)
            else 1.0
        )
        if ratio != 1:
            draws["cpm"] *= ratio
            draws["impressions"] /= ratio
            draws["clicks"] /= ratio
            for r in predictions:
                r["cpm_pred"] *= ratio
                r["cpm_interval"] = [x * ratio for x in r["cpm_interval"]]
                r["expected_impressions"] /= ratio
                r["expected_clicks"] /= ratio
                r["assumptions"].append("market_context_ratio_unvalidated")
        if ctr_shifts:
            apply_ctr_shifts(predictions, draws, ctr_shifts)
        ages = age_predictions(
            draws,
            brief.seed,
            brief.age_shares,
            brief.age_effects,
            brief.prior_strength,
            brief.sensitivity_profile,
            signal_effects,
        )
        for r, age in zip(predictions, ages):
            r["ages"] = age
            r["assumptions"] = [a for a in r["assumptions"] if a != "country_IT_assumed"] + [
                f"country_{brief.country}_user_scenario"
            ]
        return predictions, draws

    def result(self, run_id):
        run = self.repo.get("simulation_runs", run_id)
        key = run.get("result_key")
        if not key:
            raise ValueError("Risultati non ancora disponibili")
        return self.store.read_json(key)

    def execute_run(self, run_id, client=None):
        run = self.repo.get("simulation_runs", run_id)
        scenario = self.repo.get("scenarios", run["scenario_id"])
        if scenario.get("dataset_snapshot"):
            source = self.store.path(scenario["dataset_snapshot"])
            scoped = SimulationService(self.cfg.model_copy())
            scoped.cfg.data_dir = source
            try:
                return scoped._execute_run(run_id, client)
            finally:
                scoped.executor.shutdown(wait=False)
                scoped.cloud_executor.shutdown(wait=False)
                scoped.repo.engine.dispose()
        return self._execute_run(run_id, client)

    def _execute_run(self, run_id, client=None):
        run = self.repo.get("simulation_runs", run_id)
        if run["completion_status"] == "complete" or run["status"] == "canceled":
            return
        if not self.repo.claim_run(run_id):
            return
        client = client or self.client(run.get("provider", "ollama"), run.get("requested_model"))
        scenario = self.repo.get("scenarios", run["scenario_id"])
        brief = effective_brief(CampaignBrief.model_validate(scenario["brief"]), scenario)
        if run.get("mode") == "agent_native":
            return self._execute_native_run(run_id, run, client, scenario, brief)
        profiles = self.repo.get("populations", scenario["population_id"])["profiles"]
        try:
            self.repo.update_run(
                run_id, status="running", phase="baseline", progress=max(run["progress"], 3), error=None
            )
            predictions, draws = self.predict_brief(brief)
            self.store.write_json(
                f"runs/{run_id}.preliminary.json",
                {
                    "profiles": profiles,
                    "predictions": predictions,
                    "completion_status": "preliminary",
                    "warning": "Baseline e scenari teorici: valutazioni consumatori non completate.",
                },
            )
            self.repo.update_run(run_id, result_key=f"runs/{run_id}.preliminary.json")
            runtime = client.status()
            if not runtime["ready"]:
                self.repo.update_run(
                    run_id,
                    status="waiting_for_runtime",
                    phase="agents",
                    error=runtime["error"],
                    completion_status="preliminary",
                )
                return
            if run.get("model_digest") and run["model_digest"] != runtime["digest"]:
                self.repo.update_run(
                    run_id,
                    status="failed",
                    error="Digest modello cambiato: crea una nuova run",
                    phase="agents",
                )
                return
            plan = evaluation_plan(brief, profiles, runtime["digest"], client.prompt_version)
            self.repo.update_run(
                run_id,
                model_digest=runtime["digest"],
                model_name=client.model,
                required_policies=len(plan),
                completion_status="partial",
                phase="agents",
            )
            policies = {}
            attempts = 0
            for item in plan:
                if self.repo.get("simulation_runs", run_id)["status"] == "canceled":
                    return
                cached = self.repo.get_policy(item["key"])
                if cached:
                    policies[item["key"]] = cached["response"]
                    continue
                if attempts >= self.cfg.max_evaluations:
                    self.repo.update_run(
                        run_id,
                        status="waiting_for_capacity",
                        error="Limite valutazioni raggiunto. Riprendi per completare le policy mancanti.",
                        completed_policies=len(policies),
                    )
                    return
                last_error = None
                for _ in range(2):
                    if attempts >= self.cfg.max_evaluations:
                        break
                    attempts += 1
                    try:
                        response = client.evaluate(item["input"])
                        self.repo.save_policy(
                            item["key"],
                            {
                                "input": item["input"],
                                "response": response["evaluation"],
                                "digest": runtime["digest"],
                                "metrics": {k: v for k, v in response.items() if k != "evaluation"},
                            },
                        )
                        policies[item["key"]] = response["evaluation"]
                        last_error = None
                        break
                    except CloudQuotaError as exc:
                        self.repo.update_run(
                            run_id,
                            status="waiting_for_capacity",
                            error=str(exc),
                            retry_after_seconds=exc.retry_after_seconds,
                            completed_policies=len(policies),
                        )
                        return
                    except CloudRuntimeError as exc:
                        self.repo.update_run(
                            run_id,
                            status="waiting_for_runtime",
                            error=str(exc),
                            completed_policies=len(policies),
                        )
                        return
                    except httpx.ConnectError:
                        self.repo.update_run(
                            run_id,
                            status="waiting_for_runtime",
                            error="Ollama disconnesso; le policy salvate restano disponibili.",
                            completed_policies=len(policies),
                        )
                        return
                    except (httpx.HTTPError, ValueError, KeyError) as exc:
                        last_error = (
                            f"Valutazione {item['agent_id']}/{item['creative_id']}: {type(exc).__name__}"
                        )
                if last_error:
                    self.repo.update_run(
                        run_id,
                        status="waiting_for_capacity",
                        error=last_error,
                        completed_policies=len(policies),
                    )
                    return
                self.repo.update_run(
                    run_id,
                    completed_policies=len(policies),
                    progress=10 + int(70 * len(policies) / len(plan)),
                )
            if len(policies) != len(plan):
                raise ValueError("Copertura panel incompleta")
            self.repo.update_run(run_id, completed_policies=len(policies), phase="behavior", progress=85)
            signals = policy_signals(brief, profiles, policies, plan, predictions)
            assessment = assess_domain(
                Domain.from_brief(brief),
                getattr(client, "prompt_version", None),
                getattr(client, "model", None),
            )
            shifts, panel_calibration = self.panel_calibration(brief, plan, policies, assessment)
            predictions, draws = self.predict_brief(brief, signals, shifts)
            behavior = simulate_panel(brief, profiles, policies, plan, predictions)
            comparison = compare_predictions(predictions, draws, assessment)
            coverage = {
                "required": len(plan),
                "completed": len(policies),
                "ratio": 1.0,
                "profiles": len(profiles),
            }
            report = build_report(brief, predictions, behavior, comparison, coverage, panel_calibration)
            audit_predictions(predictions, brief.daily_adset_budget_eur)
            result = {
                "run_id": run_id,
                "brief": brief.model_dump(mode="json"),
                "profiles": profiles,
                "predictions": predictions,
                "behavior": behavior,
                "comparison": comparison,
                "report": report,
                "coverage": coverage,
                "completion_status": "complete",
                "quantitative_source": "historical_baseline_with_calibrated_panel_shift"
                if panel_calibration["applied"]
                else "historical_baseline_with_age_reconciliation",
                "panel_calibration": panel_calibration,
                "model": {
                    "name": client.model,
                    "digest": runtime["digest"],
                    "provider": getattr(client, "provider", "ollama"),
                    "digest_is_weights_hash": runtime.get("digest_is_weights_hash", True),
                    "prompt_version": client.prompt_version,
                },
                "provenance": {
                    "dataset_id": scenario.get("dataset_id"),
                    "seed": brief.seed,
                    "profile_version": profiles[0]["profile_version"],
                    "aggregate_model": self.get_models().version,
                    "training_cutoff": self.get_models().cutoff,
                },
                "uncertainty": "Condizionata alle policy LLM e ai prior; non copre tutti i bias del modello.",
                "evidence": EVIDENCE,
                "assumptions": ASSUMPTIONS,
                "policy_snapshot": [
                    {"key": item["key"], "input": item["input"], "evaluation": policies[item["key"]]}
                    for item in plan
                ],
            }
            self._publish(run_id, result, predictions, behavior, report)
        except Exception as exc:
            self.repo.update_run(
                run_id, status="failed", phase="error", error=f"{type(exc).__name__}: {str(exc)[:300]}"
            )

    def _publish(self, run_id, result, predictions, behavior, report):
        key = f"runs/{run_id}.json"
        self.store.write_json(key, result)
        with self.repo.transaction():
            if not self.repo.finish_run(
                run_id,
                status="succeeded",
                phase="complete",
                completion_status="complete",
                progress=100,
                result_key=key,
                error=None,
            ):
                return
            self.repo.bulk_create("predictions", [{"payload": {"run_id": run_id, **r}} for r in predictions])
            self.repo.bulk_create(
                "age_predictions",
                [
                    {"payload": {"run_id": run_id, "ad_id": r["ad_id"], "date": r["date"], **a}}
                    for r in predictions
                    for a in r["ages"]
                ],
            )
            self.repo.bulk_create(
                "consumer_states", [{"payload": {"run_id": run_id, **s}} for s in behavior["states"]]
            )
            self.repo.bulk_create(
                "exposure_events", [{"payload": {"run_id": run_id, **e}} for e in behavior["events"]]
            )
            self.repo.bulk_create(
                "prediction_explanations",
                [{"payload": {"run_id": run_id, **d}} for d in report["diagnoses"]],
            )

    def _execute_native_run(self, run_id, run, client, scenario, brief):
        """agent_native: baseline forecast as reference, persona cards, one reaction per exposure, then the engine."""
        population = self.repo.get("populations", scenario["population_id"])
        profiles = population["profiles"]
        slots = tuple(run.get("slots") or SLOTS)

        def pause(status, error, **extra):
            self.repo.update_run(run_id, status=status, error=error, **extra)

        try:
            self.repo.update_run(
                run_id, status="running", phase="baseline", progress=max(run["progress"], 3), error=None
            )
            predictions, draws = self.predict_brief(brief)
            self.store.write_json(
                f"runs/{run_id}.preliminary.json",
                {
                    "profiles": profiles,
                    "predictions": predictions,
                    "completion_status": "preliminary",
                    "warning": "Solo forecast storico di riferimento: le decisioni degli agenti non sono ancora complete.",
                },
            )
            self.repo.update_run(run_id, result_key=f"runs/{run_id}.preliminary.json")
            runtime = client.status()
            if not runtime["ready"]:
                self.repo.update_run(
                    run_id,
                    status="waiting_for_runtime",
                    phase="agents",
                    error=runtime["error"],
                    completion_status="preliminary",
                )
                return
            if run.get("model_digest") and run["model_digest"] != runtime["digest"]:
                self.repo.update_run(
                    run_id,
                    status="failed",
                    error="Digest modello cambiato: crea una nuova run",
                    phase="agents",
                )
                return
            performance = run.get("performance") or {}
            performance.update(
                writer_version=PersonaWriter.version,
                reaction_prompt_version=REACTION_PROMPT_VERSION,
                concurrency=self.cfg.ollama_reaction_concurrency if client.provider == "ollama" else 1,
            )
            performance.setdefault("cards", stage_metrics())
            performance.setdefault("reactions", stage_metrics())
            self.repo.update_run(
                run_id, phase="personas", progress=max(run["progress"], 8), model_digest=runtime["digest"]
            )
            writer = PersonaWriter(
                self.repo, client, runtime["digest"], brief.vertical, brief.country, brief.brand
            )
            state = population.get("writer_state", {})

            def card_progress(done, total):
                performance["cards"] = dict(writer.performance)
                self.repo.replace("populations", population["id"], {**population, "writer_state": state})
                if self.repo.get("simulation_runs", run_id)["status"] == "canceled":
                    self.repo.update_run(run_id, performance=performance)
                    raise InterruptedError("Simulazione annullata")
                self.repo.update_run(
                    run_id,
                    persona_cards_done=done,
                    persona_cards_total=total,
                    progress=max(run["progress"], 3 + int(7 * done / total)),
                    performance=performance,
                )

            try:
                cards, persona_report = writer.write(
                    profiles, progress=card_progress, performance=performance["cards"], state=state
                )
            except CloudQuotaError as exc:
                pause("waiting_for_capacity", str(exc), retry_after_seconds=exc.retry_after_seconds)
                return
            except CloudRuntimeError as exc:
                pause("waiting_for_runtime", str(exc))
                return
            except httpx.ConnectError:
                pause("waiting_for_runtime", "Runtime disconnesso; le schede salvate restano disponibili.")
                return
            population = {
                **population,
                "cards": cards,
                "persona_report": persona_report,
                "writer_state": state,
            }
            self.repo.replace("populations", population["id"], population)
            plan = reaction_plan(brief, profiles, population["cards"], runtime["digest"], slots=slots)
            self.repo.update_run(
                run_id,
                model_digest=runtime["digest"],
                model_name=client.model,
                required_policies=len(plan),
                completion_status="partial",
                phase="agents",
            )

            def reaction_progress(completed, metrics):
                performance["reactions"] = dict(metrics)
                if self.repo.get("simulation_runs", run_id)["status"] == "canceled":
                    self.repo.update_run(run_id, performance=performance)
                else:
                    self.repo.update_run(
                        run_id,
                        completed_policies=len(completed),
                        progress=max(run["progress"], 10 + int(70 * len(completed) / len(plan))),
                        performance=performance,
                    )

            execution = run_reaction_plan(
                self.repo,
                client,
                plan,
                runtime["digest"],
                concurrency=performance["concurrency"],
                max_evaluations=self.cfg.max_evaluations,
                performance=performance["reactions"],
                progress=reaction_progress,
                canceled=lambda: self.repo.get("simulation_runs", run_id)["status"] == "canceled",
            )
            decisions = execution["decisions"]
            if execution["canceled"]:
                return
            exc = execution["error"]
            if exc:
                if isinstance(exc, CloudQuotaError):
                    pause(
                        "waiting_for_capacity",
                        str(exc),
                        retry_after_seconds=exc.retry_after_seconds,
                        completed_policies=len(decisions),
                    )
                elif isinstance(exc, (CloudRuntimeError, httpx.ConnectError)):
                    pause("waiting_for_runtime", str(exc), completed_policies=len(decisions))
                else:
                    pause("waiting_for_capacity", str(exc), completed_policies=len(decisions))
                return
            if len(decisions) != len(plan):
                raise ValueError("Copertura panel incompleta")
            self.repo.update_run(run_id, completed_policies=len(decisions), phase="behavior", progress=85)
            native = simulate_agent_native(brief, profiles, plan, decisions, predictions, draws)
            assessment = assess_domain(Domain.from_brief(brief), REACTION_PROMPT_VERSION, client.model)
            behavior = native["behavior"]
            comparison = compare_predictions(predictions, native["draws"], assessment)
            coverage = {
                "required": len(plan),
                "completed": len(decisions),
                "ratio": 1.0,
                "profiles": len(profiles),
            }
            calibration = {
                "applied": False,
                "reason": "agent_native: nessuna riconciliazione sul CTR storico.",
            }
            report = build_report(
                brief, predictions, behavior, comparison, coverage, calibration, native=native["native"]
            )
            audit_predictions(predictions, brief.daily_adset_budget_eur)
            result = {
                "run_id": run_id,
                "mode": "agent_native",
                "brief": brief.model_dump(mode="json"),
                "profiles": profiles,
                "cards": population["cards"],
                "persona_report": population.get("persona_report"),
                "performance": performance,
                "predictions": predictions,
                "behavior": behavior,
                "comparison": comparison,
                "report": report,
                "coverage": coverage,
                "completion_status": "complete",
                "quantitative_source": "agent_native_decisions",
                "panel_calibration": calibration,
                "model": {
                    "name": client.model,
                    "digest": runtime["digest"],
                    "provider": getattr(client, "provider", "ollama"),
                    "digest_is_weights_hash": runtime.get("digest_is_weights_hash", True),
                    "prompt_version": REACTION_PROMPT_VERSION,
                },
                "provenance": {
                    "dataset_id": scenario.get("dataset_id"),
                    "seed": brief.seed,
                    "profile_version": profiles[0]["profile_version"],
                    "aggregate_model": self.get_models().version,
                    "training_cutoff": self.get_models().cutoff,
                    "engine_version": native["native"]["engine_version"],
                },
                "validated": False,
                "uncertainty": native["native"]["uncertainty"],
                "evidence": EVIDENCE,
                "assumptions": ASSUMPTIONS,
                "decision_snapshot": [
                    {
                        "key": i["key"],
                        "agent_id": i["agent_id"],
                        "creative_id": i["creative_id"],
                        "slot": i["slot"],
                        "regime": i["regime"],
                        "placement": i["placement"],
                        "input": i["input"],
                        "decision": decisions[i["key"]]["decision"],
                    }
                    for i in plan
                ],
            }
            self._publish(run_id, result, predictions, behavior, report)
        except Exception as exc:
            if self.repo.get("simulation_runs", run_id)["status"] == "canceled":
                return
            self.repo.update_run(
                run_id, status="failed", phase="error", error=f"{type(exc).__name__}: {str(exc)[:300]}"
            )

    def backtest(self):
        with self.lock:
            report = validate_models(self.ensure_kit(), self.get_models(), n_draws=self.cfg.monte_carlo_draws)
            if self.store.path("validation/ablation.json").exists():
                ablation = self.store.read_json("validation/ablation.json")
                if ablation["dataset_hash"] == self.import_dataset(self.cfg.data_dir)["id"]:
                    report["ablation"] = ablation
            self.repo.create("validation_runs", report)
            self.store.write_json("validation/latest.json", report)
            return report

    def official_forecast(self):
        with self.lock:
            kit = self.ensure_kit()
            rows, draws = forecast(kit, self.get_models(), kit["future"], n_draws=self.cfg.monte_carlo_draws)
            ages = age_predictions(draws)
            for row, age in zip(rows, ages):
                row["ages"] = age
            result = {
                "predictions": rows,
                "completion_status": "preliminary",
                "quantitative_source": "historical_baseline",
                "warning": "699 previsioni baseline con decomposizione teorica. Non una simulazione completa degli agenti LLM.",
            }
            self.store.write_json("official/forecast.json", result)
            return result
