"""Live check on a local or hosted model: write persona cards, then compare reaction-prompt variants on the same
exposures (synthetic split, never the benchmark test). Usage:
    .venv/bin/python scripts/live_prompt_check.py --people 10 --variants v8 v8_no_examples v8_base_rate
Results: artifacts/validation/prompt-variants-live.json
"""

import argparse
import json
import time
from pathlib import Path

from audience_simulator.config import settings
from audience_simulator.persona_cards import PersonaWriter
from audience_simulator.persona_model import generate_targeted_population
from audience_simulator.prompt_eval import compare_variants
from audience_simulator.reactions import reaction_plan
from audience_simulator.repository import Repository
from audience_simulator.schemas import CampaignBrief, Creative, TargetingSpec
from audience_simulator.service import SimulationService

parser = argparse.ArgumentParser()
parser.add_argument("--provider", default="ollama", choices=["ollama", "gemini", "cloudflare"])
parser.add_argument("--model", default=None)
parser.add_argument("--people", type=int, default=10)
parser.add_argument("--variants", nargs="+", default=["v8", "v8_no_examples", "v8_base_rate"])
parser.add_argument("--out", default="artifacts/validation/prompt-variants-live.json")
args = parser.parse_args()

brief = CampaignBrief(
    name="live-check",
    brand="Nuvola Derma Lab",
    product_description="Kit routine autunno con detergente, siero e crema.",
    vertical="beauty_skincare",
    date_from="2026-11-16",
    date_to="2026-11-16",
    population_size=30,
    creatives=[
        Creative(
            id="A",
            headline="Edizione limitata: kit routine autunno",
            primary_text="Solo 500 kit numerati. Detergente, siero e crema in un'unica scatola.",
            visual_description="Carosello con il kit, i tre prodotti e le recensioni.",
            format="carosello",
        )
    ],
    targeting=TargetingSpec(
        audience_intent="donne con una routine di cura della pelle", detailed=[{"id": "interest:skincare"}]
    ),
)
profiles, _ = generate_targeted_population(brief)
profiles = profiles[:: max(1, len(profiles) // args.people)][: args.people]
client = SimulationService(settings()).client(args.provider, args.model)
digest = client.status()["digest"]
if not digest:
    raise SystemExit(client.status()["error"])
repo = Repository("sqlite:///artifacts/validation/live-check.sqlite")
out = Path(args.out)
start = time.time()
cards, card_report = PersonaWriter(repo, client, digest, brief.vertical, brief.country, brief.brand).write(
    profiles
)
report = {
    "provider": args.provider,
    "model": client.model,
    "people": len(profiles),
    "cards": card_report,
    "cards_seconds": round(time.time() - start),
}
out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
plan = reaction_plan(brief, profiles, cards, digest, slots=("first",))
start = time.time()
comparison = compare_variants(client, args.variants, plan, profiles, "synthetic", n=len(plan))
report["reactions_seconds"] = round(time.time() - start)
for name, entry in comparison["variants"].items():
    quality = entry.pop("quality") or {}
    entry["summary"] = {
        k: quality.get(k)
        for k in (
            "mean_per_100",
            "mean_notice",
            "positive_share",
            "grounded_share",
            "marketer_language_share",
            "inconsistent_share",
            "invented_numbers_share",
            "flags",
            "warnings",
        )
    }
report["comparison"] = comparison
out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
print(json.dumps(report, ensure_ascii=False, indent=1))
