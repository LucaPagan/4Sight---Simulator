"""Compare prompt variants on the same exposures, with paired statistics. For tuning on dev data only.

PROMISE rule 1: prompt, model and parameters are chosen on the ``dev`` split only; the locked test is evaluated once.
This harness therefore refuses ``split="test"`` outright and accepts only ``dev`` (a corpus dev split) or ``synthetic``
(exposures generated for a scenario, never part of a benchmark). Variants see identical exposures, so differences are
paired. Nothing here reads real outcomes; it measures properties of the model's answers (diversity, grounding,
marketer language, positivity), not accuracy.
"""

from dataclasses import dataclass

import numpy as np

from .audience import stable_seed
from .cloud import CloudQuotaError
from .decision_quality import MARKETER, assess_decisions, marketer_speak, references_ad
from .reaction_quality import assess_panel, references_creative
from .reactions import build_prompt, decide

ALLOWED_SPLITS = {"dev", "synthetic"}
EXAMPLES_MARK = "ESEMPI DI FORMA"
CLOSING_MARK = "Rispondi come questa persona"


@dataclass(frozen=True)
class Variant:
    name: str
    build: object
    temperature: float = 0.7


def build_without_examples(payload):
    return build_prompt(payload, examples=False)


BASE_RATE_REMINDER = (
    "COME USI DAVVERO I SOCIAL\nIn una sessione ti passano davanti decine di post sponsorizzati e quasi tutti li scorri senza "
    "fermarti; aprirne uno è raro, anche quando l'argomento ti riguarda. Rispondi per come ti comporti davvero, non per come "
    "saresti se prestassi attenzione a ogni annuncio.\n\n"
)


def build_with_base_rate(payload):
    """v8 plus a reminder of ordinary scrolling behaviour, placed right before the closing instruction. No numbers."""
    system, user = build_prompt(payload)
    end = user.index(CLOSING_MARK)
    return system, user[:end] + BASE_RATE_REMINDER + user[end:]


VARIANTS = {
    "v8": Variant("v8", build_prompt),
    "v8_no_examples": Variant("v8_no_examples", build_without_examples),
    "v8_base_rate": Variant("v8_base_rate", build_with_base_rate),
    "v8_temperature_0": Variant("v8_temperature_0", build_prompt, 0.0),
    "v8_temperature_1": Variant("v8_temperature_1", build_prompt, 1.0),
}


def guard_split(split):
    if split == "test":
        raise ValueError(
            "Il test congelato non si usa per scegliere prompt: solo split dev o dati sintetici (PROMISE, regola 1)"
        )
    if split not in ALLOWED_SPLITS:
        raise ValueError("split deve essere dev o synthetic")


def sample_items(plan, n, seed=0):
    """Deterministic sample of exposures, the same for every variant."""
    return sorted(plan, key=lambda i: stable_seed(seed, i["key"]))[:n]


def run_variant(client, variant, items):
    """Records for the exposures this variant answered, and how many failed. Quota errors propagate."""
    records, failed = [], 0
    for item in items:
        try:
            answer = decide(client, item["input"], build=variant.build, temperature=variant.temperature)
        except CloudQuotaError:
            raise
        except (ValueError, KeyError):
            failed += 1
            continue
        records.append(
            {
                **{k: item[k] for k in ("key", "agent_id", "creative_id", "slot")},
                "input": item["input"],
                "decision": answer["decision"],
            }
        )
    return records, failed


def paired_difference(a, b, seed=0, n_boot=2000):
    """Mean of b - a with a 95% bootstrap interval over exposures. a and b are aligned per exposure."""
    delta = np.asarray(b, float) - np.asarray(a, float)
    if not len(delta):
        return {"mean_difference": None, "interval": None, "n": 0}
    rng = np.random.default_rng(seed)
    means = rng.choice(delta, (n_boot, len(delta)), replace=True).mean(axis=1)
    return {
        "mean_difference": float(delta.mean()),
        "interval": [float(x) for x in np.quantile(means, [0.025, 0.975])],
        "n": int(len(delta)),
    }


def _per_item(records):
    return {
        r["key"]: {
            "notice": r["decision"]["gates"]["notice"],
            "click": float(r["decision"]["click_per_100"]),
            "grounded": float(references_ad(r)),
            "marketer": float(marketer_speak(r)),
        }
        for r in records
    }


def compare_variants(client, variants, plan, profiles, split, n=60, seed=0, baseline="v8"):
    """Run each variant on the same sampled exposures; report quality metrics and paired differences from the baseline."""
    guard_split(split)
    items = sample_items(plan, n, seed)
    profile_map = {p["agent_id"]: p for p in profiles}
    runs = {}
    for name in variants:
        records, failed = run_variant(client, VARIANTS[name], items)
        runs[name] = {"records": records, "failed": failed}
    base = _per_item(runs[baseline]["records"])
    report = {}
    for name, run in runs.items():
        entry = {
            "answered": len(run["records"]),
            "failed": run["failed"],
            "quality": assess_decisions(run["records"], profile_map) if run["records"] else None,
        }
        if name != baseline:
            other = _per_item(run["records"])
            common = sorted(set(base) & set(other))
            entry["paired_vs_baseline"] = {
                metric: paired_difference(
                    [base[k][metric] for k in common], [other[k][metric] for k in common], seed
                )
                for metric in ("notice", "click", "grounded", "marketer")
            }
        report[name] = entry
    return {
        "split": split,
        "exposures": len(items),
        "baseline": baseline,
        "variants": report,
        "evidence": "hypothesis",
        "warning": "Misura proprietà delle risposte (diversità, aderenza, linguaggio da marketing, positività), non accuratezza. "
        "Una differenza appaiata il cui intervallo contiene zero non è una differenza.",
    }


def compare_with_v7(client, brief, profiles, plan, digest, split, n=40, seed=0):
    """The v7 evaluation and the v8 decision on the same persona, creative and day. Only common metrics are compared."""
    from .agents import evaluation_plan

    guard_split(split)
    items = [i for i in sample_items([i for i in plan if i["slot"] == "first"], n, seed)]
    by_agent = {p["agent_id"]: p for p in profiles}
    v8_records, failed_v8 = run_variant(client, VARIANTS["v8"], items)
    v7_records, failed_v7 = [], 0
    for record in v8_records:
        profile = by_agent[record["agent_id"]]
        v7_item = next(
            p for p in evaluation_plan(brief, [profile], digest) if p["creative_id"] == record["creative_id"]
        )
        try:
            evaluation = client.evaluate(v7_item["input"])["evaluation"]
        except CloudQuotaError:
            raise
        except (ValueError, KeyError):
            failed_v7 += 1
            continue
        v7_records.append(
            {
                "key": v7_item["key"],
                "agent_id": record["agent_id"],
                "input": v7_item["input"],
                "evaluation": evaluation,
                "v8_key": record["key"],
            }
        )
    paired = {r["v8_key"] for r in v7_records}
    v8_common = [r for r in v8_records if r["key"] in paired]
    v7_by_key = {r["v8_key"]: r for r in v7_records}
    grounded_v7 = [float(references_creative(v7_by_key[r["key"]])) for r in v8_common]
    marketer_v7 = [
        float(bool(MARKETER.search(v7_by_key[r["key"]]["evaluation"]["conditional_reaction"])))
        for r in v8_common
    ]
    v8 = _per_item(v8_common)
    keys = [r["key"] for r in v8_common]
    quality7 = assess_panel(v7_records) if v7_records else None
    quality8 = assess_decisions(v8_common, {p["agent_id"]: p for p in profiles}) if v8_common else None
    return {
        "split": split,
        "exposures": len(keys),
        "failed": {"v7": failed_v7, "v8": failed_v8},
        "v7": {
            "positive_share": float(
                np.mean([r["evaluation"]["conditional_action"] == "consider_click" for r in v7_records])
            )
            if v7_records
            else None,
            "largest_cluster_share": quality7["repetition"]["largest_cluster_share"] if quality7 else None,
            "grounded_share": quality7["grounded_share"] if quality7 else None,
            "invented_numbers_share": quality7["invented_numbers_share"] if quality7 else None,
            "marketer_language_share": float(np.mean(marketer_v7)) if marketer_v7 else None,
        },
        "v8": {
            "positive_share": quality8["positive_share"] if quality8 else None,
            "largest_cluster_share": quality8["repetition"]["largest_cluster_share"] if quality8 else None,
            "grounded_share": quality8["grounded_share"] if quality8 else None,
            "invented_numbers_share": quality8["invented_numbers_share"] if quality8 else None,
            "marketer_language_share": quality8["marketer_language_share"] if quality8 else None,
        },
        "paired_v8_minus_v7": {
            "grounded": paired_difference(grounded_v7, [v8[k]["grounded"] for k in keys], seed),
            "marketer": paired_difference(marketer_v7, [v8[k]["marketer"] for k in keys], seed),
        },
        "note": "La quota positiva non è confrontabile: in v7 è «considera il click», in v8 almeno 20 interazioni su 100. "
        "v7 riceve la persona come numeri e attributi, v8 con la scheda. Sono confrontabili ripetitività, aderenza, "
        "numeri inventati e linguaggio da marketing.",
        "evidence": "hypothesis",
    }
