"""Small controlled contrasts across all MVP sectors; not a human-validity benchmark.

Run: .venv/bin/python scripts/check_consumer_behavior.py --provider gemini
"""

import argparse
import json

import httpx
import numpy as np
from audience_simulator.agents import evaluation_plan, policy_diagnostics, policy_key
from audience_simulator.audience import generate_population
from audience_simulator.cloud import CloudRuntimeError
from audience_simulator.config import settings
from audience_simulator.schemas import VERTICALS, CampaignBrief, Creative
from audience_simulator.service import SimulationService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["ollama", "gemini", "cloudflare"], default="gemini")
    parser.add_argument("--model")
    args = parser.parse_args()
    service = SimulationService(settings())
    client = service.client(args.provider, args.model)
    runtime = client.status()
    if not runtime["ready"]:
        raise ValueError("Runtime non pronto")
    plan = []
    for vertical in VERTICALS:
        asset = (
            service.ensure_kit()["assets"]
            .loc[lambda f: f.vertical == vertical]
            .sort_values("asset_id")
            .iloc[0]
        )
        clear = Creative(
            id=f"{vertical}:clear",
            headline=asset.headline,
            primary_text=asset.testo_principale,
            visual_description=asset.descrizione_visual,
            lever=asset.leva,
            format=asset.formato,
        )
        vague = Creative(
            id=f"{vertical}:vague",
            headline="Scopri qualcosa",
            primary_text="Clicca per saperne di più. Nessuna informazione sul prodotto o sui vantaggi.",
            visual_description="Immagine senza prodotto o informazioni leggibili.",
            lever=asset.leva,
            format=asset.formato,
        )
        brief = CampaignBrief(
            name="Controlled diagnostic",
            brand="Unfamiliar test brand",
            vertical=vertical,
            product_description=f"{asset.headline}. {asset.testo_principale}",
            date_from="2026-11-16",
            date_to="2026-11-16",
            creatives=[clear, vague],
        )
        base = generate_population(brief)[40]
        profiles = []
        for label, value in [("high_need", 0.95), ("low_need", 0.05)]:
            profiles.append(
                {
                    **base,
                    "agent_id": label,
                    "category_affinity": value,
                    "purchase_need": value,
                    "brand_familiarity": 0,
                    "budget_sensitivity": 0.5,
                    "trust": 0.5,
                    "population_weight": 0.5,
                    "category_context": "Controlled hypothetical profile: "
                    + (
                        "current need and strong interest in this product category"
                        if label == "high_need"
                        else "no current need and little interest in this product category"
                    ),
                }
            )
        plan.extend(evaluation_plan(brief, profiles, runtime["digest"], client.prompt_version))
    assert len(plan) == 12 and len({p["key"] for p in plan}) == 12
    assert {p["input"]["campaign"]["vertical"] for p in plan} == set(VERTICALS)
    run_id = policy_key({"method": "controlled-consumer-contrasts-v1", "keys": [p["key"] for p in plan]})
    key = f"validation/behavior-probes/{run_id}.json"
    results, attempts, error = [], 0, None
    for item in plan:
        cached = service.repo.get_policy(item["key"])
        if cached is None:
            attempts += 1
            try:
                response = client.evaluate(item["input"])
            except (CloudRuntimeError, httpx.HTTPError, ValueError) as exc:
                error = str(exc) if isinstance(exc, CloudRuntimeError) else type(exc).__name__
                break
            cached = {
                "input": item["input"],
                "response": response["evaluation"],
                "digest": runtime["digest"],
                "metrics": {k: v for k, v in response.items() if k != "evaluation"},
            }
            service.repo.save_policy(item["key"], cached)
        results.append({**item, "evaluation": cached["response"]})
        service.store.write_json(key, {"status": "partial", "results": results, "required": 12})
    checks = []
    if len(results) == 12:
        for vertical in VERTICALS:
            subset = [r for r in results if r["input"]["campaign"]["vertical"] == vertical]

            def mean_score(field, predicate):
                return float(np.mean([r["evaluation"][field] for r in subset if predicate(r)]))

            checks.append(
                {
                    "vertical": vertical,
                    "clear_minus_vague_clarity": mean_score(
                        "clarity", lambda r: r["creative_id"].endswith(":clear")
                    )
                    - mean_score("clarity", lambda r: r["creative_id"].endswith(":vague")),
                    "high_minus_low_need_interest": mean_score(
                        "interest", lambda r: r["agent_id"] == "high_need"
                    )
                    - mean_score("interest", lambda r: r["agent_id"] == "low_need"),
                }
            )
    report = {
        "status": "complete" if len(results) == 12 else "partial",
        "required": 12,
        "completed": len(results),
        "new_attempts": attempts,
        "error": error,
        "provider": args.provider,
        "model": client.model,
        "results": results,
        "directional_checks": checks,
        "policy_quality": policy_diagnostics(results),
        "human_behavior_validated": False,
        "method": "controlled-consumer-contrasts-v1",
        "warning": "Synthetic controls, two profiles per sector: functional sensitivity only, not human realism or predictive accuracy.",
    }
    service.store.write_json(key, report)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
