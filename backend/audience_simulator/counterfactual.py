"""Metamorphic tests: does the agent's decision move when only one thing about the person or the ad changes?

A persona that ignores its own facts is the main failure of a prompt like this one, and a lexical check cannot see it.
Each test asks the model about the same exposure twice, changing a single thing, and counts how often the decision moves
in the direction a reasonable person would expect. A placebo (same persona, only name and city swapped) measures the
noise of the model at the same temperature; a test counts as sensitive only when it beats that noise. Directions are
hypotheses declared here, not findings, and the results are descriptive of the model, not of real people.
"""

import numpy as np
from scipy.stats import binomtest

from .agents import policy_key
from .audience import stable_seed
from .cloud import CloudQuotaError
from .context import calendar_regime
from .persona_cards import describe_profile, template_card
from .reactions import REACTION_PROMPT_VERSION, build_payload, decide
from .stimulus_view import exposure_placement

MIN_NON_TIES = 8
MIN_SHARE = 0.7
ALPHA = 0.05
TIE = {"notice": 0.005, "click": 0.5}
PLACEBO_STABLE_NOTICE = 0.05
OFF_TOPIC_CREATIVE = {
    "id": "off-topic",
    "headline": "Preventivo assicurazione auto in 2 minuti",
    "primary_text": "Confronta le offerte delle compagnie e risparmia sul rinnovo della polizza auto.",
    "visual_description": "Un'auto grigia parcheggiata davanti a un ufficio",
    "cta": "Richiedi preventivo",
    "offer": "",
    "price_text": "",
    "landing_page_summary": "",
    "format": "immagine",
}
HIGH_PRICE = "129,90 €"
RELEVANT = {
    "pet_ecommerce": lambda p: p["pet_species"] in {"dog", "cat"},
    "beauty_skincare": lambda p: p["skincare_routine"] == "extended",
    "abbigliamento": lambda p: True,
}
REMOVE = {
    "pet_ecommerce": {"pet_species": "none"},
    "beauty_skincare": {"skincare_routine": "none"},
}
TESTS = {
    "relevant_person_vs_not": {
        "metric": "notice",
        "what": "La stessa persona con e senza ciò che rende pertinente la categoria (animale, routine di cura della pelle): "
        "ci si aspetta più attenzione quando è pertinente.",
    },
    "on_topic_vs_off_topic_ad": {
        "metric": "notice",
        "what": "Stessa persona pertinente davanti all'annuncio del brief e a un annuncio di un altro settore: "
        "ci si aspetta più attenzione per quello pertinente.",
    },
    "price_sensitive_vs_not": {
        "metric": "click",
        "what": "Stesso annuncio con un prezzo alto, mostrato a una persona benestante e poco attenta al prezzo e alla stessa "
        "persona con reddito basso e molto attenta al prezzo: ci si aspetta più click dalla prima.",
    },
    "first_vs_saturated": {
        "metric": "notice",
        "what": "Stesso annuncio alla prima vista e dopo molte viste: ci si aspetta meno attenzione dopo molte viste.",
    },
    "placebo": {
        "metric": "notice",
        "what": "Stessa persona con solo nome e città scambiati con quelli di un'altra dello stesso genere: "
        "non ci si aspetta nessuna differenza. Misura il rumore del modello.",
    },
}


def minimal_card(profile, ordinal):
    """A card with only the facts, so a changed attribute cannot be contradicted by free text."""
    return {**template_card(profile, ordinal), "facts": describe_profile(profile)}


def _chosen(profiles, test, vertical, limit):
    ordered = sorted(profiles, key=lambda p: stable_seed(test, p["agent_id"]))
    return ordered[:limit]


def build_pairs(brief, profiles, cards, digest, n_pairs=12):
    vertical, creative = brief.vertical, brief.creatives[0].model_dump()
    regime = calendar_regime(brief.date_from)
    relevant = [p for p in profiles if RELEVANT[vertical](p)]

    def payload(profile, card, ad, slot="first"):
        return build_payload(
            brief,
            profile,
            card,
            ad,
            exposure_placement(profile, brief),
            slot,
            regime,
            digest,
            REACTION_PROMPT_VERSION,
        )

    pairs = []
    if vertical in REMOVE:
        for i, p in enumerate(_chosen(relevant, "person", vertical, n_pairs)):
            flipped = {**p, **REMOVE[vertical]}
            pairs.append(
                {
                    "test": "relevant_person_vs_not",
                    "agent_id": p["agent_id"],
                    "a": payload(p, minimal_card(p, i), creative),
                    "b": payload(p, minimal_card(flipped, i), creative),
                }
            )
    for p in _chosen(relevant, "ad", vertical, n_pairs):
        pairs.append(
            {
                "test": "on_topic_vs_off_topic_ad",
                "agent_id": p["agent_id"],
                "a": payload(p, cards[p["agent_id"]], creative),
                "b": payload(p, cards[p["agent_id"]], OFF_TOPIC_CREATIVE),
            }
        )
    priced = {**creative, "price_text": HIGH_PRICE}
    for i, p in enumerate(_chosen(profiles, "price", vertical, n_pairs)):
        rich = {**p, "income_band": "high", "budget_sensitivity": 0.1}
        poor = {**p, "income_band": "low", "budget_sensitivity": 0.9}
        pairs.append(
            {
                "test": "price_sensitive_vs_not",
                "agent_id": p["agent_id"],
                "a": payload(p, minimal_card(rich, i), priced),
                "b": payload(p, minimal_card(poor, i), priced),
            }
        )
    for p in _chosen(profiles, "frequency", vertical, n_pairs):
        pairs.append(
            {
                "test": "first_vs_saturated",
                "agent_id": p["agent_id"],
                "a": payload(p, cards[p["agent_id"]], creative, "first"),
                "b": payload(p, cards[p["agent_id"]], creative, "saturated"),
            }
        )
    by_gender = {}
    for p in profiles:
        by_gender.setdefault(p["gender"], []).append(p)
    for p in _chosen(profiles, "placebo", vertical, n_pairs):
        others = [q for q in by_gender[p["gender"]] if q["agent_id"] != p["agent_id"]]
        if not others:
            continue
        donor = cards[others[stable_seed("donor", p["agent_id"]) % len(others)]["agent_id"]]
        swapped = {**cards[p["agent_id"]], "name": donor["name"], "city": donor["city"]}
        pairs.append(
            {
                "test": "placebo",
                "agent_id": p["agent_id"],
                "a": payload(p, cards[p["agent_id"]], creative),
                "b": payload(p, swapped, creative),
            }
        )
    return pairs


def _value(decision, metric):
    return decision["gates"]["notice"] if metric == "notice" else float(decision["click_per_100"])


def _answer(client, repo, payload, build=None, temperature=0.7):
    key = policy_key(payload)
    stored = repo.get_decision(key) if repo is not None and build is None else None
    if stored:
        return stored["result"]["decision"]
    record = decide(client, payload, build=build, temperature=temperature)
    if repo is not None and build is None:
        repo.save_decision(key, {"digest": payload["model_digest"], "result": record})
    return record["decision"]


def summarize(name, rows):
    metric = TESTS[name]["metric"]
    deltas = np.array([r[f"{metric}_a"] - r[f"{metric}_b"] for r in rows], float)
    other = "click" if metric == "notice" else "notice"
    other_delta = np.array([r[f"{other}_a"] - r[f"{other}_b"] for r in rows], float)
    result = {
        "test": name,
        "metric": metric,
        "what": TESTS[name]["what"],
        "pairs": len(rows),
        f"mean_delta_{metric}": float(deltas.mean()) if len(deltas) else None,
        f"mean_delta_{other}": float(other_delta.mean()) if len(deltas) else None,
        "mean_abs_delta": float(np.abs(deltas).mean()) if len(deltas) else None,
    }
    if name == "placebo":
        result["stable"] = bool(len(rows) and float(np.abs(deltas).mean()) <= PLACEBO_STABLE_NOTICE)
        return result
    up, down = int((deltas > TIE[metric]).sum()), int((deltas < -TIE[metric]).sum())
    decided = up + down
    result.update(
        {
            "expected_direction": "a_greater",
            "moved_as_expected": up,
            "moved_against": down,
            "ties": len(rows) - decided,
            "share_as_expected": up / decided if decided else None,
            "p_value": float(binomtest(up, decided, 0.5, alternative="greater").pvalue) if decided else None,
        }
    )
    return result


def verdict(result, floor):
    """sensitive / insensitive / inconclusive, against the placebo noise on the same metric."""
    decided = result["moved_as_expected"] + result["moved_against"]
    if result["pairs"] < MIN_NON_TIES:
        return "inconclusive"
    if decided < MIN_NON_TIES:  # enough pairs, almost none moved: the decision ignores the change
        return "insensitive"
    mean_delta = result[f"mean_delta_{result['metric']}"]
    if (
        result["share_as_expected"] >= MIN_SHARE
        and result["p_value"] < ALPHA
        and mean_delta > 0
        and (floor is None or mean_delta > floor)
    ):
        return "sensitive"
    return "insensitive"


def run_counterfactuals(client, brief, profiles, cards, digest, repo=None, n_pairs=12):
    """Ask both variants of every pair. Quota errors propagate; a pair with an invalid answer is dropped and counted."""
    pairs = build_pairs(brief, profiles, cards, digest, n_pairs)
    rows, failed = {name: [] for name in TESTS}, 0
    for pair in pairs:
        try:
            a, b = _answer(client, repo, pair["a"]), _answer(client, repo, pair["b"])
        except CloudQuotaError:
            raise
        except (ValueError, KeyError):
            failed += 1
            continue
        rows[pair["test"]].append(
            {
                "agent_id": pair["agent_id"],
                "notice_a": a["gates"]["notice"],
                "notice_b": b["gates"]["notice"],
                "click_a": float(a["click_per_100"]),
                "click_b": float(b["click_per_100"]),
            }
        )
    results = [summarize(name, rows[name]) for name in TESTS if rows[name] or name == "placebo"]
    placebo = next((r for r in results if r["test"] == "placebo"), None)
    floors = {"notice": placebo["mean_abs_delta"] if placebo and placebo["pairs"] else None}
    placebo_click = (
        float(np.mean([abs(r["click_a"] - r["click_b"]) for r in rows["placebo"]]))
        if rows["placebo"]
        else None
    )
    floors["click"] = placebo_click
    for result in results:
        if result["test"] != "placebo":
            result["verdict"] = verdict(result, floors[result["metric"]])
            result["placebo_floor"] = floors[result["metric"]]
    counts = {
        v: sum(r.get("verdict") == v for r in results) for v in ("sensitive", "insensitive", "inconclusive")
    }
    return {
        "prompt_version": REACTION_PROMPT_VERSION,
        "tests": results,
        "summary": {
            **counts,
            "placebo_stable": placebo["stable"] if placebo and placebo["pairs"] else None,
            "failed_pairs": failed,
            "pairs_asked": len(pairs),
        },
        "thresholds": {
            "min_non_ties": MIN_NON_TIES,
            "min_share_as_expected": MIN_SHARE,
            "alpha": ALPHA,
            "tie": TIE,
            "placebo_stable_notice": PLACEBO_STABLE_NOTICE,
        },
        "evidence": "hypothesis",
        "validated": False,
        "warning": "Le direzioni attese sono ipotesi dichiarate nel codice. Una persona sensibile ai propri fatti non prova che "
        "reagisca come una persona reale: dice che il prompt non ignora la scheda.",
    }
