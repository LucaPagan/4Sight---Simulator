"""Run the panel (B2) or a single neutral LLM (B1) on corpus stimuli. Inputs only: outcomes are never read.

Features are saved per campaign and per split, and policies are cached like production runs, so a quota
interruption resumes where it stopped. Calibration and scoring then read these features, not the LLM.
"""

import numpy as np

from .agents import policy_key
from .audience import generate_profiles
from .calibration import FEATURES, creative_features
from .cloud import CloudQuotaError, CloudRuntimeError

CONTEXT = "lettori online di notizie negli USA; tratti ipotetici, non osservati"


def _creative(stimulus):
    return {
        "id": stimulus["id"],
        "headline": stimulus.get("headline") or "",
        "primary_text": stimulus.get("primary_text") or "",
        "cta": "",
        "offer": "",
        "price_text": "",
        "landing_page_summary": "",
        "visual_description": "",
    }


def corpus_payloads(campaign, system, panel_size, digest, prompt_version, seed=42):
    domain = campaign["domain"]
    if system == "B2":
        profiles = generate_profiles(seed, "news_headline", "corpus", [1 / 6] * 6, CONTEXT, panel_size)
    elif system == "B1":
        profiles = [{"agent_id": "no-persona", "category_context": CONTEXT}]
    else:
        raise ValueError("Sistema sconosciuto")
    context = {
        "brand": "unknown",
        "product": "articolo online",
        "vertical": domain["kind"],
        "country": domain["country"],
        "objective": domain["objective"],
        "placement": domain["placement"],
        "device": "mobile",
        "task": "casual_scrolling",
        "price_eur": 0.0,
        "date_from": campaign.get("date_from") or "",
        "date_to": campaign.get("date_to") or "",
        "notes": "Titolo letto in un feed; nessun dato di rendimento disponibile.",
    }
    work = []
    for stimulus in campaign["stimuli"]:
        for profile in profiles:
            payload = {
                "profile": profile,
                "creative": _creative(stimulus),
                "regime": "ordinary",
                "campaign": context,
                "model_digest": digest,
                "prompt_version": prompt_version,
            }
            work.append({"key": policy_key(payload), "stimulus_id": stimulus["id"], "input": payload})
    return work


def run_panel(store, repo, client, campaigns, system, split, panel_size=30, max_new=500):
    runtime = client.status()
    if not runtime["ready"]:
        return {"status": "waiting_for_runtime", "error": runtime["error"], "new_calls": 0}
    key = f"validation/panel-features/{system}-{split}.json"
    try:
        features = store.read_json(key)
    except FileNotFoundError:
        features = {}
    new_calls, status, error = 0, "complete", None
    for campaign in campaigns:
        work = corpus_payloads(campaign, system, panel_size, runtime["digest"], client.prompt_version)
        records = {}
        for item in work:
            cached = repo.get_policy(item["key"])
            if cached is None:
                if new_calls >= max_new:
                    status = "partial"
                    break
                try:
                    response = client.evaluate(item["input"])
                except CloudQuotaError as exc:
                    status, error = "waiting_for_capacity", str(exc)
                    break
                except CloudRuntimeError as exc:
                    status, error = "waiting_for_runtime", str(exc)
                    break
                new_calls += 1
                repo.save_policy(
                    item["key"],
                    {
                        "input": item["input"],
                        "response": response["evaluation"],
                        "digest": runtime["digest"],
                        "metrics": {k: v for k, v in response.items() if k != "evaluation"},
                    },
                )
                cached = repo.get_policy(item["key"])
            records.setdefault(item["stimulus_id"], []).append(
                {"input": item["input"], "evaluation": cached["response"]}
            )
        if status != "complete":
            break
        features[campaign["campaign_id"]] = {sid: creative_features(r) for sid, r in records.items()}
    store.write_json(key, features)
    result = {"status": status, "new_calls": new_calls, "campaigns_with_features": len(features)}
    if error:
        result["error"] = error
    return result


def score_with_calibration(store, system, split):
    """Relative arm scores w.f - mean(w.f) from fitted weights and stored features; no outcomes involved."""
    features = store.read_json(f"validation/panel-features/{system}-{split}.json")
    weights = np.array(
        [store.read_json(f"validation/calibration-{system}.json")["weights"][n] for n in FEATURES]
    )
    scores = {}
    for campaign_id, arms in features.items():
        raw = {arm: float(weights @ np.array([f[n] for n in FEATURES])) for arm, f in arms.items()}
        mean = float(np.mean(list(raw.values())))
        scores[campaign_id] = {arm: value - mean for arm, value in raw.items()}
    store.write_json(f"validation/scores/{system}-{split}.json", scores)
    return scores
