"""Diagnosis of a finished agent_native run: why cards fell back to templates, where the time goes, and how much
of the CTR level comes from the per-100 scale. Reads the app database; model calls use a separate cache.
    .venv/bin/python scripts/diagnose_native.py ctr --run <run_id>
    .venv/bin/python scripts/diagnose_native.py cards --run <run_id>      (rewrites the template cards, keeps rejects)
    .venv/bin/python scripts/diagnose_native.py timing --run <run_id>     (a few reactions, two work orders)
Each part is written under its own key in artifacts/validation/native-diagnosis.json.
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
from audience_simulator.agents import OllamaClient
from audience_simulator.persona_cards import PersonaWriter
from audience_simulator.reactions import decide, reaction_plan
from audience_simulator.repository import Repository
from audience_simulator.schemas import CampaignBrief
from audience_simulator.service import effective_brief

parser = argparse.ArgumentParser()
parser.add_argument("part", choices=["ctr", "cards", "timing"])
parser.add_argument("--run", required=True)
parser.add_argument("--model", default="qwen3.5:9b")
parser.add_argument("--people", type=int, default=3)
parser.add_argument("--label", default="")
parser.add_argument("--out", default="artifacts/validation/native-diagnosis.json")
args = parser.parse_args()

app = Repository("sqlite:///artifacts/audience.db")
run = app.get("simulation_runs", args.run)
scenario = app.get("scenarios", run["scenario_id"])
population = app.get("populations", scenario["population_id"])
profiles, cards = population["profiles"], population.get("cards") or {}
brief = effective_brief(CampaignBrief.model_validate(scenario["brief"]), scenario)
out = Path(args.out)
report = json.loads(out.read_text()) if out.exists() else {}


def save(key, value):
    report[key + (f":{args.label}" if args.label else "")] = value
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(value, ensure_ascii=False, indent=1))


if args.part == "ctr":
    result = json.loads(Path("artifacts", run["result_key"]).read_text())
    rows = {}
    for creative in sorted({s["creative_id"] for s in result["decision_snapshot"]}):
        decisions = [s["decision"] for s in result["decision_snapshot"] if s["creative_id"] == creative]
        click = np.array([d["click_per_100"] for d in decisions], dtype=float)
        notice = 100 - np.array([d["skip_per_100"] for d in decisions], dtype=float)
        top = np.sort(click)[::-1][: max(1, len(click) // 10)]
        rows[creative] = {
            "decisions": len(click),
            "click_values": dict(sorted(Counter(int(c) for c in click).items())),
            "mean_click_per_100": round(float(click.mean()), 2),
            "median_click_per_100": float(np.median(click)),
            "share_zero": round(float((click == 0).mean()), 2),
            "share_one": round(float((click == 1).mean()), 2),
            "share_five_or_more": round(float((click >= 5).mean()), 2),
            "share_of_clicks_from_top_10pct": round(float(top.sum() / max(click.sum(), 1)), 2),
            "mean_if_one_means_0.5": round(float(np.where(click == 1, 0.5, click).mean()), 2),
            "mean_if_one_means_0.3": round(float(np.where(click == 1, 0.3, click).mean()), 2),
            "mean_if_capped_at_5": round(float(np.minimum(click, 5).mean()), 2),
            "mean_notice_per_100": round(float(notice.mean()), 1),
            "click_given_notice": round(float(click.sum() / max(notice.sum(), 1)), 3),
            "reference_ctr_pct": next(
                (
                    p.get("reference_forecast", {}).get("ctr_pred")
                    for p in result["predictions"]
                    if p["ad_id"] == creative
                ),
                None,
            ),
        }
    save("ctr", rows)

client = OllamaClient(model=args.model)
digest = client.status()["digest"]
scratch = Repository("sqlite:///artifacts/validation/native-diagnosis.sqlite")

if args.part == "cards":
    target = [p for p in profiles if cards.get(p["agent_id"], {}).get("source") == "template"]
    writer = PersonaWriter(scratch, client, digest, brief.vertical, brief.country, brief.brand)
    start = time.time()
    _, card_report = writer.write(target)
    card_report["wall_seconds"] = round(time.time() - start)
    save(
        "cards",
        {
            "people": len(target),
            "report": card_report,
            "timings": writer.timings,
            "rejected_samples": writer.rejected_samples,
            "facts": {p["agent_id"]: cards[p["agent_id"]]["facts"] for p in target},
        },
    )

if args.part == "timing":
    written = [p for p in profiles if cards.get(p["agent_id"], {}).get("source") == "llm"][: args.people]
    plan = reaction_plan(brief, written, cards, digest, slots=("first",))
    orders = {
        "per_creativita": plan,
        "per_persona": sorted(plan, key=lambda i: [p["agent_id"] for p in written].index(i["agent_id"])),
    }
    table = {}
    for name, order in orders.items():
        calls = []
        for index, item in enumerate(order):
            # A different attempt per order: the answer is regenerated, the prompt is the same.
            record = None
            for retry in range(3):
                try:
                    start = time.monotonic()
                    record = decide(
                        client, item["input"], attempt=10 + retry + (100 if name == "per_persona" else 0)
                    )
                    break
                except ValueError:
                    continue
            raw = client.last_timing if hasattr(client, "last_timing") else {}
            calls.append(
                {
                    "agent": item["agent_id"],
                    "creative": item["creative_id"],
                    "seconds": round(time.monotonic() - start, 1),
                    "prompt_tokens": record and record["prompt_tokens"],
                    "output_tokens": record and record["tokens"],
                    **raw,
                }
            )
        table[name] = {
            "calls": calls,
            "mean_seconds": round(float(np.mean([c["seconds"] for c in calls])), 1),
        }
    save("timing", table)
