"""One typed, cached conditional evaluation per consumer/creative/calendar regime."""

import hashlib
import json
import re
import time
from collections import Counter
from datetime import timedelta

import httpx

from .context import calendar_regime as calendar_regime
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, model_view
from .schemas import AgentEvaluation, CampaignBrief


def policy_key(payload):
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def evaluation_plan(brief: CampaignBrief, profiles, digest, prompt_version=PROMPT_VERSION):
    regimes = sorted(
        {
            calendar_regime(brief.date_from + timedelta(days=d))
            for d in range((brief.date_to - brief.date_from).days + 1)
        }
    )
    work = []
    for creative in brief.creatives:
        for regime in regimes:
            for profile in profiles:
                payload = {
                    "profile": profile,
                    "creative": creative.model_dump(),
                    "regime": regime,
                    "campaign": {
                        "brand": brief.brand,
                        "product": brief.product_description,
                        "vertical": brief.vertical,
                        "country": brief.country,
                        "objective": brief.objective,
                        "placement": brief.placement,
                        "device": brief.device,
                        "task": brief.browsing_task,
                        "price_eur": brief.price_eur,
                        "date_from": str(brief.date_from),
                        "date_to": str(brief.date_to),
                        "notes": brief.notes,
                    },
                    "model_digest": digest,
                    "prompt_version": prompt_version,
                }
                work.append(
                    {
                        "key": policy_key(payload),
                        "agent_id": profile["agent_id"],
                        "creative_id": creative.id,
                        "regime": regime,
                        "input": payload,
                    }
                )
    return work


def evaluation_schema(payload):
    references = [
        f"{group}.{field}"
        for group in ("creative", "profile", "campaign")
        for field in payload.get(group, {})
    ] + ["assumption.placement", "assumption.age_prior"]
    schema = AgentEvaluation.model_json_schema()
    schema["properties"]["evidence"]["items"] = {"type": "string", "enum": references}
    schema["required"] = list(schema["properties"])
    return schema


def validate_evaluation(raw, payload):
    references = evaluation_schema(payload)["properties"]["evidence"]["items"]["enum"]
    evaluation = AgentEvaluation.model_validate_json(raw)
    normalizations = 0
    for index, reference in enumerate(evaluation.evidence):
        if "." not in reference:
            matches = [r for r in references if r.rsplit(".", 1)[1] == reference]
            if len(matches) == 1:
                evaluation.evidence[index] = matches[0]
                normalizations += 1
    for reference in evaluation.evidence:
        if reference in {"assumption.placement", "assumption.age_prior"}:
            continue
        parts = reference.split(".")
        value = payload
        if parts[0] not in {"creative", "profile", "campaign"}:
            raise ValueError("evidence non consentita")
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                raise ValueError("evidence inesistente")
            value = value[part]
    if payload.get("campaign", {}).get("price_eur") is None and "price_unknown" not in evaluation.frictions:
        evaluation.frictions.append("price_unknown")
    AgentEvaluation.model_validate(evaluation.model_dump())
    return evaluation.model_dump(), normalizations


def policy_diagnostics(records):
    """Measure actual response repetition; lexical variety cannot establish human realism."""
    groups = []
    for creative_id in sorted({r["creative_id"] for r in records}):
        rows = [r for r in records if r["creative_id"] == creative_id]
        values = [r["evaluation"] for r in rows]
        reactions = Counter(
            " ".join(re.findall(r"\w+", v["conditional_reaction"].casefold())) for v in values
        )
        vectors = {tuple(v[k] for k in ("clarity", "interest", "credibility", "friction")) for v in values}
        repetition = reactions.most_common(1)[0][1] / len(values)
        flags = []
        if len(values) >= 6 and repetition >= 0.5:
            flags.append("repetitive_reactions")
        if len(values) >= 6 and len(vectors) == 1:
            flags.append("uniform_scores")
        groups.append(
            {
                "creative_id": creative_id,
                "policies": len(values),
                "profiles": len({r["agent_id"] for r in rows}),
                "distinct_reactions": len(reactions),
                "most_repeated_fraction": repetition,
                "distinct_score_vectors": len(vectors),
                "actions": dict(Counter(v["conditional_action"] for v in values)),
                "flags": flags,
            }
        )
    return {
        "by_creative": groups,
        "human_behavior_validated": False,
        "thresholds": {"minimum_policies": 6, "repetition_fraction": 0.5},
        "warning": "Controlli descrittivi sulle risposte del modello, non osservazioni umane. "
        "Ripetitività e consenso richiedono revisione; non vanno corretti inventando frasi diverse.",
    }


class OllamaClient:
    provider = "ollama"
    prompt_version = PROMPT_VERSION
    # A local model writes slowly: small card batches keep each request well inside the timeout.
    card_batch_size = 2
    generate_timeout = 900

    def __init__(self, base_url="http://127.0.0.1:11434", model="qwen3.5:9b", transport=None):
        self.base_url, self.model = base_url.rstrip("/"), model
        self.http = httpx.Client(base_url=self.base_url, timeout=180, transport=transport, trust_env=False)

    def status(self):
        try:
            response = self.http.get("/api/tags", timeout=3)
            response.raise_for_status()
            models = response.json().get("models", [])
            selected = next((m for m in models if m["name"] == self.model), None)
            return {
                "available": True,
                "ready": selected is not None,
                "selected_model": self.model,
                "digest": selected["digest"] if selected else None,
                "models": [{"name": m["name"], "digest": m["digest"], "size": m.get("size")} for m in models],
                "error": None if selected else "Modello selezionato non installato",
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "available": False,
                "ready": False,
                "selected_model": self.model,
                "digest": None,
                "models": [],
                "error": f"Runtime locale non disponibile: {type(exc).__name__}",
            }

    def evaluate(self, payload):
        start = time.monotonic()
        view = model_view(payload)
        schema = evaluation_schema(view)
        # Ollama 0.30 ignores chat schemas for Qwen with thinking disabled; generate applies them immediately.
        response = self.http.post(
            "/api/generate",
            json={
                "model": self.model,
                "stream": False,
                "think": False,
                "format": schema,
                "system": SYSTEM_PROMPT
                + "\nRestituisci l'oggetto direttamente, senza wrapper. Campi obbligatori: clarity, interest, credibility, friction, conditional_action, evidence, conditional_reaction.\nJSON Schema:\n"
                + json.dumps(schema, ensure_ascii=False)
                + '\nevidence contiene solo nomi di campi dalla enum, senza valori o spiegazioni. Esempio: ["creative.headline", "profile.category_affinity"].',
                "prompt": "Valuta il seguente contesto. Restituisci direttamente clarity, interest, credibility, friction, conditional_action, frictions, evidence, unknowns, conditional_reaction. Dati:\n"
                + json.dumps(view, ensure_ascii=False),
                "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512},
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("done") is not True:
            raise ValueError("Risposta LLM incompleta")
        raw = data["response"]
        evaluation, normalizations = validate_evaluation(raw, view)
        return {
            "evaluation": evaluation,
            "seconds": time.monotonic() - start,
            "tokens": data.get("eval_count", 0),
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "prompt_version": PROMPT_VERSION,
            "thinking_used": bool(data.get("thinking")),
            "evidence_normalizations": normalizations,
        }

    def generate(self, system, user, schema, *, temperature=0.9, seed=None, max_tokens=2048):
        """One schema-constrained generation outside the evaluation flow (persona cards and similar)."""
        start = time.monotonic()
        options = {"temperature": temperature, "num_ctx": 16384, "num_predict": max_tokens}
        if seed is not None:
            options["seed"] = seed
        response = self.http.post(
            "/api/generate",
            json={
                "model": self.model,
                "stream": False,
                "think": False,
                "format": schema,
                "system": system + "\nJSON Schema:\n" + json.dumps(schema, ensure_ascii=False),
                "prompt": user,
                "options": options,
            },
            timeout=self.generate_timeout,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("done") is not True:
            raise ValueError("Risposta LLM incompleta")
        self.last_timing = {
            "prompt_seconds": round(data.get("prompt_eval_duration", 0) / 1e9, 1),
            "output_seconds": round(data.get("eval_duration", 0) / 1e9, 1),
            "load_seconds": round(data.get("load_duration", 0) / 1e9, 1),
        }
        return {
            "raw": data["response"],
            "seconds": time.monotonic() - start,
            "tokens": data.get("eval_count", 0),
            "prompt_tokens": data.get("prompt_eval_count", 0),
            # Ollama reports nanoseconds; a prompt read from the prefix cache shows up as a short read time.
            "prompt_seconds": data.get("prompt_eval_duration", 0) / 1e9,
            "output_seconds": data.get("eval_duration", 0) / 1e9,
            "load_seconds": data.get("load_duration", 0) / 1e9,
            "provider": self.provider,
            "model": self.model,
        }
