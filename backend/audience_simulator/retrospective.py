"""Public Meta campaign replay: ordinal panel preference, never a calibrated CTR forecast."""

import hashlib
import io
import json
import math

import httpx
import numpy as np
import pandas as pd
from pydantic import Field
from scipy.stats import norm

from .agents import PROMPT_VERSION, policy_key, validate_evaluation
from .audience import generate_profiles
from .cloud import CloudQuotaError, CloudRuntimeError
from .schemas import StrictModel

SOURCE_COMMIT = "5c97d539590e08cc5d3a8f3e10a270eb7f00e611"
SOURCE_URL = (
    f"https://raw.githubusercontent.com/daaronr/eamt_data_analysis/{SOURCE_COMMIT}/"
    "gwwc/gg_raw_data_shareable/gg_campaign_by_ad_by_text.csv"
)
SOURCE_SHA256 = "9d4df9370cf144fcc4b010b93b60440d712ca9de20969c7ae799fe1a016fa296"
ROOT = "validation/public-meta"
METHOD = "ordinal-panel-replay-v1"


class PublicContext(StrictModel):
    brand: str
    product: str
    vertical: str
    country: str
    objective: str
    placement: str
    task: str
    price_eur: float
    date_from: str
    date_to: str
    notes: str


class PublicCreative(StrictModel):
    id: str
    primary_text: str = Field(min_length=1, max_length=5000)
    visual_description: str


class PublicCase(StrictModel):
    context: PublicContext
    creatives: list[PublicCreative] = Field(min_length=2, max_length=2)
    seed: int = 42


def _identifier(value):
    if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Identificatore non valido")
    return value


def _count(value, nullable=False):
    if pd.isna(value) and nullable:
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError("Conteggio osservato non valido")
    return int(number)


def build_case(frame):
    rows = frame.loc[
        (frame["Campaign name"] == "Giving Guide 2021 - Emotional")
        & (frame["Ad name"] == "Animal Welfare (Emotional)")
    ]
    texts = rows.Text.tolist()
    if any(not isinstance(t, str) or not t.strip() for t in texts):
        raise ValueError("Testo mancante")
    if len(texts) != len(set(texts)):
        raise ValueError("Celle duplicate: impossibile distinguere annunci o aggregazioni")
    selected = sorted(texts, key=lambda t: hashlib.sha256(t.encode()).hexdigest())[:2]
    creatives, observations = [], []
    for text in selected:
        row = rows.loc[rows.Text == text].iloc[0]
        arm_id = hashlib.sha256(text.encode()).hexdigest()[:12]
        impressions, clicks = _count(row.Impressions), _count(row["Link clicks"], nullable=True)
        spend = float(row["Amount spent (USD)"])
        if (
            not impressions
            or (clicks is not None and clicks > impressions)
            or not math.isfinite(spend)
            or spend < 0
        ):
            raise ValueError("Metriche osservate non valide")
        creatives.append(
            {
                "id": arm_id,
                "primary_text": text,
                "visual_description": "Animal welfare video, 16 seconds: care about animals, effective charities, download giving guide. "
                "Description from campaign authors; video not inspected. Same ad group for both texts.",
            }
        )
        observations.append({"id": arm_id, "impressions": impressions, "clicks": clicks, "spend_usd": spend})
    context = dict(
        brand="Giving What We Can",
        product="Free Effective Giving Guide, email required to download",
        vertical="charitable_giving",
        country="unknown_in_public_export",
        objective="guide_leads",
        placement="Facebook, exact placement unknown",
        task="casual_scrolling",
        price_eur=0.0,
        date_from="2021-11-30",
        date_to="2021-12-20",
        notes="Animal welfare interest audience. English copy. Do not look up or recall campaign results. "
        "Recipient traits, ages, country and prior familiarity are unknown; profile traits are hypothetical.",
    )
    case = PublicCase(context=PublicContext(**context), creatives=creatives).model_dump()
    return case, {"arms": observations, "currency": "USD", "metric": "link_clicks_per_impression"}


def prepare_public_campaign(service, transport=None):
    with httpx.Client(timeout=30, transport=transport, follow_redirects=True) as http:
        response = http.get(SOURCE_URL)
        response.raise_for_status()
    raw = response.content
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Fonte modificata: checksum non corrispondente")
    case, observations = build_case(pd.read_csv(io.BytesIO(raw)))
    case_id = policy_key(case)
    root = f"{ROOT}/cases/{case_id}"
    provenance = {
        "url": SOURCE_URL,
        "commit": SOURCE_COMMIT,
        "sha256": SOURCE_SHA256,
        "selection": "Fixed campaign/ad, first two texts by SHA-256, no outcome-based selection",
        "source_type": "real_public_campaign_export",
        "license": "not_specified_do_not_redistribute",
    }
    service.store.write_bytes(f"{root}/source.csv", raw)
    service.store.write_json(f"{root}/case.json", case)
    service.store.write_json(f"{root}/observations.json", observations)
    service.store.write_json(f"{root}/provenance.json", provenance)
    return {
        "case_id": case_id,
        "case_key": f"{root}/case.json",
        "policies_required": 240,
        "source": provenance,
        "status": "prepared_no_ai_calls",
    }


def run_public_campaign(service, case_id, client, max_new=240):
    if not 1 <= max_new <= 240:
        raise ValueError("max_new deve essere tra 1 e 240")
    case_key = f"{ROOT}/cases/{_identifier(case_id)}/case.json"
    case = PublicCase.model_validate(service.store.read_json(case_key)).model_dump()
    if policy_key(case) != case_id:
        raise ValueError("Integrità input non valida")
    runtime = client.status()
    if not runtime.get("ready") or not runtime.get("digest"):
        raise ValueError("Runtime non pronto")
    profiles = generate_profiles(
        case["seed"],
        case["context"]["vertical"],
        case["context"]["brand"],
        [1 / 6] * 6,
        "Hypothetical charitable giving and animal welfare interest; traits not observed in real recipients",
    )
    prompt = getattr(client, "prompt_version", PROMPT_VERSION)
    payloads = [
        {
            "profile": p,
            "creative": c,
            "campaign": case["context"],
            "regime": "ordinary",
            "model_digest": runtime["digest"],
            "prompt_version": prompt,
        }
        for c in case["creatives"]
        for p in profiles
    ]
    manifest = {
        "case_id": case_id,
        "case_hash": policy_key(case),
        "method": METHOD,
        "provider": client.provider,
        "model": client.model,
        "model_digest": runtime["digest"],
        "prompt_version": prompt,
        "policy_keys": [policy_key(p) for p in payloads],
        "profiles": 120,
        "required": len(payloads),
    }
    evaluation_id = policy_key(manifest)
    root = f"{ROOT}/evaluations/{evaluation_id}"
    service.store.write_json(f"{root}/manifest.json", manifest)
    evaluations, attempts, cached_count = [], 0, 0
    error = None
    error_message = None
    for payload in payloads:
        key = policy_key(payload)
        cached = service.repo.get_policy(key)
        if cached is None:
            if attempts >= max_new:
                break
            attempts += 1
            try:
                result = client.evaluate(payload)
                evaluation, _ = validate_evaluation(json.dumps(result["evaluation"]), payload)
            except (CloudQuotaError, CloudRuntimeError, httpx.HTTPError, ValueError) as exc:
                error = type(exc).__name__
                # Our cloud adapter supplies sanitized reasons; arbitrary transport/validation text may expose inputs.
                error_message = str(exc) if isinstance(exc, CloudRuntimeError) else error
                break
            cached = {
                "input": payload,
                "response": evaluation,
                "digest": runtime["digest"],
                "metrics": {k: v for k, v in result.items() if k != "evaluation"},
            }
            service.repo.save_policy(key, cached)
        else:
            cached_count += 1
        evaluation, _ = validate_evaluation(json.dumps(cached["response"]), payload)
        evaluations.append({"key": key, "input": payload, "response": evaluation})
        service.store.write_json(f"{root}/progress.json", {"completed": len(evaluations), "required": 240})
    complete = len(evaluations) == len(payloads)
    result = {
        "status": "complete" if complete else "partial",
        "evaluation_id": evaluation_id,
        "case_id": case_id,
        "required": len(payloads),
        "completed": len(evaluations),
        "new_attempts": attempts,
        "cached": cached_count,
        "error": error,
        "error_message": error_message,
        "snapshot_key": f"{root}/snapshot.json",
    }
    snapshot = {"manifest": manifest, "evaluations": evaluations, "status": result["status"]}
    service.store.write_json(result["snapshot_key"], snapshot)
    # This commitment precedes any reading of observations; integrity evidence is not third-party certification.
    service.store.write_json(f"{root}/commitment.json", {"snapshot_sha256": policy_key(snapshot)})
    service.store.write_json(f"{root}/status.json", result)
    return result


def score_public_campaign(service, evaluation_id):
    root = f"{ROOT}/evaluations/{_identifier(evaluation_id)}"
    snapshot = service.store.read_json(f"{root}/snapshot.json")
    commitment = service.store.read_json(f"{root}/commitment.json")
    manifest = snapshot["manifest"]
    if policy_key(snapshot) != commitment["snapshot_sha256"] or policy_key(manifest) != evaluation_id:
        raise ValueError("Integrità della valutazione non valida")
    evaluations = snapshot["evaluations"]
    if snapshot["status"] != "complete" or len(evaluations) != manifest["required"]:
        raise ValueError("Valutazione incompleta: riprendere prima del confronto")
    if [e["key"] for e in evaluations] != manifest["policy_keys"] or any(
        policy_key(e["input"]) != e["key"] for e in evaluations
    ):
        raise ValueError("Integrità delle policy non valida")
    panel = []
    for creative_id in dict.fromkeys(e["input"]["creative"]["id"] for e in evaluations):
        items = [e for e in evaluations if e["input"]["creative"]["id"] == creative_id]
        weights = np.array([e["input"]["profile"]["population_weight"] for e in items])
        panel.append(
            {
                "id": creative_id,
                "policy_count": len(items),
                "scores": {
                    k: float(np.average([e["response"][k] for e in items], weights=weights))
                    for k in ("clarity", "interest", "credibility", "friction")
                },
                "consider_click_share": float(
                    np.average(
                        [e["response"]["conditional_action"] == "consider_click" for e in items],
                        weights=weights,
                    )
                ),
            }
        )
    # Predeclared primary endpoint: weighted ordinal interest; never interpret it as a probability of click.
    a, b = panel
    preference = (
        a["id"]
        if a["scores"]["interest"] > b["scores"]["interest"]
        else (b["id"] if b["scores"]["interest"] > a["scores"]["interest"] else None)
    )
    case_root = f"{ROOT}/cases/{_identifier(manifest['case_id'])}"
    raw = service.store.path(f"{case_root}/source.csv").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("Integrità della fonte non valida")
    original_case, original_observations = build_case(pd.read_csv(io.BytesIO(raw)))
    observations = service.store.read_json(f"{case_root}/observations.json")
    if policy_key(original_case) != manifest["case_id"] or observations != original_observations:
        raise ValueError("Integrità degli esiti o del caso non valida")
    observed = observations["arms"]
    if {r["id"] for r in observed} != {p["id"] for p in panel} or len(observed) != 2:
        raise ValueError("Creatività ed esiti non corrispondenti")
    for row in observed:
        n, c, spend = (
            _count(row["impressions"]),
            _count(row["clicks"], nullable=True),
            float(row["spend_usd"]),
        )
        if not n or (c is not None and c > n) or not math.isfinite(spend) or spend < 0:
            raise ValueError("Metriche osservate non valide")
        row["ctr_observed_pct"] = 100 * c / n if c is not None else None
        row["cpm_observed_usd"] = 1000 * spend / n
    oa, ob = observed
    comparable = all(o["ctr_observed_pct"] is not None for o in observed)
    difference, interval, observed_higher = None, None, None
    if comparable:
        pa, pb = oa["clicks"] / oa["impressions"], ob["clicks"] / ob["impressions"]
        difference = (pa - pb) * 100

        # Newcombe interval based on Wilson bounds; handles rare and zero clicks without zero-width certainty.
        def wilson(p, n):
            z = norm.ppf(0.975)
            center = (p + z * z / (2 * n)) / (1 + z * z / n)
            width = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
            return center - width, center + width

        la, ua = wilson(pa, oa["impressions"])
        lb, ub = wilson(pb, ob["impressions"])
        interval = [
            100 * (pa - pb - math.hypot(pa - la, ub - pb)),
            100 * (pa - pb + math.hypot(ua - pa, pb - lb)),
        ]
        observed_higher = oa["id"] if difference > 0 else ob["id"] if difference < 0 else None
    resolved = bool(interval[0] > 0 or interval[1] < 0) if interval is not None else None
    conclusion = (
        "not_evaluable_missing_outcomes"
        if not comparable
        else "no_panel_preference"
        if preference is None
        else "inconclusive_observed_difference"
        if not resolved
        else "descriptive_point_ranking_agrees"
        if preference == observed_higher
        else "descriptive_point_ranking_disagrees"
    )
    report = {
        "status": "scored" if comparable else "not_evaluable_missing_outcomes",
        "evaluation_id": evaluation_id,
        "source_type": "real_public_meta_campaign",
        "panel": panel,
        "panel_preference": preference,
        "predeclared_endpoint": "weighted_mean_ordinal_interest",
        "observed": observed,
        "observed_higher_ctr": observed_higher,
        "observed_difference_pp": difference,
        "descriptive_difference_interval_95_pp": interval,
        "observed_difference_resolved": resolved,
        "comparison_conclusion": conclusion,
        "ranking_agrees": preference == observed_higher if preference and observed_higher else None,
        "certified": False,
        "aggregate_ctr_accuracy": None,
        "cpm_prediction_accuracy": None,
        "limitations": [
            "One descriptive comparison, not an accuracy estimate or causal lift",
            "Facebook optimized delivery; recipients are not exchangeable randomized arms",
            "Hypothetical profiles with equal age shares, not observed campaign participants",
            "Only text and author video description evaluated; actual video not inspected",
            "Public campaign may be present in model training; outcomes omitted from prompts only",
            "Charity lead generation is outside production ecommerce training domain",
            "Ordinal interest and consider-click share are not CTR forecasts",
            "Hash commitment is local integrity evidence, not independent certification",
        ],
    }
    service.store.write_json(f"{root}/report.json", report)
    return report
