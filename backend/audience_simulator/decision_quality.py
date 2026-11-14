"""Checks on the substance of ``AgentDecision`` records (prompt ``agent-reaction-v8``).

Everything here is lexical, rule based or descriptive. It flags decisions and panels for human review; it does not
prove or disprove that a reaction resembles a real person (``human_validated`` stays False until the blind rubric has
been filled in). Thresholds are declared constants chosen before looking at results; tune them on dev data only.
A record is ``{"key", "agent_id", "creative_id", "slot", "input": payload, "decision": decision}``.
"""

import csv
import hashlib
import io
import re

import numpy as np
from sklearn.metrics import cohen_kappa_score

from .reaction_quality import _repetition, _stem, _tokens

THRESHOLDS = {
    "min_records": 6,
    "cluster_share": 0.5,
    "grounded_share_min": 0.7,
    "invented_share_max": 0.05,
    "inconsistent_share_max": 0.10,
    "marketer_share_max": 0.05,
    "positive_engage_per_100": 20,
    "positive_share_max": 0.35,
    "mean_notice_range": (0.03, 0.60),
    "mean_click_range": (0.05, 10.0),
    "profile_eta2_min": 0.01,
    "profile_min_records": 30,
}
MARKETER = re.compile(
    r"\b(target|conversion\w*|call to action|\bcta\b|brand awareness|engagement|funnel|usp|value proposition|"
    r"creativit\w+|messaggio chiaro|proposta di valore|posizionamento|storytelling|copy|lead|kpi|roi)\b",
    re.I,
)
POSITIVE_ACTIONS = {"like", "save", "share", "comment"}
NEGATIVE_ACTIONS = {"hide", "report"}
PROFILE_DIMENSIONS = (
    "pet_species",
    "household",
    "gender",
    "income_band",
    "age_band",
    "occupation",
    "urbanicity",
    "skincare_routine",
)
DIMENSIONS = ("realism", "profile_consistency", "groundedness")
PER_100 = ("skip", "stop", "engage", "click")


def _numbers(text):
    return {format(float(n.replace(",", ".")), "g") for n in re.findall(r"\d+(?:[.,]\d+)?", str(text))}


def _strings(value):
    if isinstance(value, dict):
        return " ".join(_strings(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_strings(v) for v in value)
    return str(value)


def glance_text(payload):
    return _strings(payload["ad"]["al_primo_sguardo"])


def ad_text(payload):
    ad = payload["ad"]
    return " ".join(_strings(ad[k]) for k in ("al_primo_sguardo", "se_ti_fermi_e_leggi", "dopo_il_click"))


def decision_text(decision):
    return " ".join(
        [decision["first_impression"], decision["detail_cited"], decision["reaction_after_stopping"]]
    )


def references_ad(record):
    """True when the decision reuses content words of the ad it saw. Cited evidence alone is not grounding."""
    seen = {_stem(t) for t in _tokens(ad_text(record["input"]))}
    return any(_stem(t) in seen for t in _tokens(decision_text(record["decision"])))


def marketer_speak(record):
    return bool(MARKETER.search(decision_text(record["decision"])))


def invented_numbers(record):
    """Numbers in the reaction that appear nowhere in the ad, the persona or the situation."""
    payload = record["input"]
    known = (
        _numbers(ad_text(payload))
        | _numbers(_strings(payload["persona"]))
        | _numbers(_strings(payload["situation"]))
    )
    return sorted(_numbers(decision_text(record["decision"])) - known)


def inconsistencies(record):
    d = record["decision"]
    engaged = d["stop_per_100"] + d["engage_per_100"] + d["click_per_100"]
    codes = []
    if d["read_beyond_glance"] and d["skip_per_100"] >= 98:
        codes.append("read_without_stopping")
    if d["reaction_after_stopping"].strip() and engaged == 0:
        codes.append("reaction_after_without_stopping")
    if d["click_per_100"] >= 5 and d["action_if_engaged"] in NEGATIVE_ACTIONS:
        codes.append("clicks_but_hides")
    cited = {_stem(t) for t in _tokens(d["detail_cited"])}
    glance = {_stem(t) for t in _tokens(glance_text(record["input"]))}
    later = {_stem(t) for t in _tokens(_strings(record["input"]["ad"]["se_ti_fermi_e_leggi"]))}
    if cited and not d["read_beyond_glance"] and not cited & glance and cited & later:
        codes.append("cites_text_not_seen_at_a_glance")
    return codes


def eta_squared(values, groups):
    """Share of the variance of ``values`` explained by ``groups`` (0 = the attribute does not matter)."""
    values = np.asarray(values, float)
    total = ((values - values.mean()) ** 2).sum()
    if total <= 1e-12:
        return 0.0
    between = 0.0
    for group in set(groups):
        member = values[[g == group for g in groups]]
        between += len(member) * (member.mean() - values.mean()) ** 2
    return float(between / total)


def _assess(records, profiles):
    n = len(records)
    decisions = [r["decision"] for r in records]
    notice = np.array([1 - d["skip_per_100"] / 100 for d in decisions])
    click = np.array([d["click_per_100"] for d in decisions], float)
    engaged = np.array([d["engage_per_100"] + d["click_per_100"] for d in decisions], float)
    repetition = _repetition([d["first_impression"] for d in decisions])
    grounded = sum(references_ad(r) for r in records) / n
    invented = sum(bool(invented_numbers(r)) for r in records) / n
    marketer = sum(marketer_speak(r) for r in records) / n
    inconsistent = sum(bool(inconsistencies(r)) for r in records) / n
    positive = float((engaged >= THRESHOLDS["positive_engage_per_100"]).mean())
    dependence = {}
    if profiles:
        for dimension in PROFILE_DIMENSIONS:
            groups = [profiles[r["agent_id"]].get(dimension) for r in records]
            if len(set(groups)) > 1 and None not in groups:
                dependence[dimension] = {
                    "notice": eta_squared(notice, groups),
                    "click": eta_squared(click, groups),
                    "groups": len(set(groups)),
                }
    flags, warnings = [], []
    if n >= THRESHOLDS["min_records"]:
        if repetition["largest_cluster_share"] >= THRESHOLDS["cluster_share"]:
            flags.append("conceptual_repetition")
        if grounded < THRESHOLDS["grounded_share_min"]:
            flags.append("weak_grounding")
        if invented > THRESHOLDS["invented_share_max"]:
            flags.append("invented_numbers")
        if inconsistent > THRESHOLDS["inconsistent_share_max"]:
            flags.append("inconsistent_decisions")
        if marketer > THRESHOLDS["marketer_share_max"]:
            flags.append("marketer_language")
        if positive > THRESHOLDS["positive_share_max"]:
            flags.append("positivity_bias")
        if len({tuple(d[f"{k}_per_100"] for k in PER_100) for d in decisions}) == 1:
            flags.append("uniform_decisions")
        low, high = THRESHOLDS["mean_notice_range"]
        if not low <= notice.mean() <= high:
            warnings.append("mean_notice_outside_plausible_range")
        low, high = THRESHOLDS["mean_click_range"]
        if not low <= click.mean() <= high:
            warnings.append("mean_click_outside_plausible_range")
    if (
        dependence
        and n >= THRESHOLDS["profile_min_records"]
        and max(v["notice"] for v in dependence.values()) < THRESHOLDS["profile_eta2_min"]
    ):
        flags.append("insensitive_to_profile")
    return {
        "decisions": n,
        "mean_per_100": {k: float(np.mean([d[f"{k}_per_100"] for d in decisions])) for k in PER_100},
        "mean_notice": float(notice.mean()),
        "positive_share": positive,
        "repetition": repetition,
        "grounded_share": grounded,
        "invented_numbers_share": invented,
        "marketer_language_share": marketer,
        "inconsistent_share": inconsistent,
        "action_mix": {
            "positive": float(np.mean([d["action_if_engaged"] in POSITIVE_ACTIONS for d in decisions])),
            "negative": float(np.mean([d["action_if_engaged"] in NEGATIVE_ACTIONS for d in decisions])),
        },
        "decision_spread": {
            "distinct_vectors": len({tuple(d[f"{k}_per_100"] for k in PER_100) for d in decisions}),
            "click_std": float(click.std()),
        },
        "profile_dependence": dependence,
        "flags": flags,
        "warnings": warnings,
    }


def assess_decisions(records, profiles=None):
    """records as described in the module docstring; profiles: agent_id -> skeleton, for the profile-dependence check."""
    if not records:
        raise ValueError("Nessuna decisione da valutare")
    result = _assess(records, profiles)
    result["by_creative"] = {
        cid: _assess([r for r in records if r["creative_id"] == cid], profiles)
        for cid in sorted({r["creative_id"] for r in records})
    }
    result["thresholds"] = THRESHOLDS
    result["human_validated"] = False
    result["warning"] = (
        "Controlli lessicali e regole sulle risposte del modello. Segnalano decisioni da rivedere; "
        "non dimostrano né escludono somiglianza con persone reali. Le soglie sono dichiarate, non calibrate."
    )
    return result


def _blind_id(seed, key):
    return hashlib.sha256(f"{seed}|{key}".encode()).hexdigest()[:10]


def export_rubric(records, n=60, seed=0):
    """Fixed blind sample for human raters: the ad as seen, the persona's facts and the reaction; no arm, model or flag."""
    chosen = sorted(records, key=lambda r: _blind_id(seed, r["key"]))[:n]
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["blind_id", "ad_seen", "persona", "reaction", *DIMENSIONS])
    writer.writeheader()
    key = {}
    for record in chosen:
        blind = _blind_id(seed, record["key"])
        d, payload = record["decision"], record["input"]
        key[blind] = record["key"]
        writer.writerow(
            {
                "blind_id": blind,
                "ad_seen": glance_text(payload),
                "persona": " ".join(payload["persona"]["fatti"]),
                "reaction": f"{d['first_impression']} {d['reaction_after_stopping']}".strip()
                + f" [su 100: salta {d['skip_per_100']}, si ferma {d['stop_per_100']}, interagisce {d['engage_per_100']}, clicca {d['click_per_100']}]",
            }
        )
    return {
        "csv": out.getvalue(),
        "key": key,
        "rubric": {
            "realism": "0 = non sembra una persona reale, 1 = plausibile, 2 = sembra una persona reale",
            "profile_consistency": "0 = contraddice i fatti della persona, 1 = compatibile, 2 = riflette chiaramente i suoi fatti",
            "groundedness": "0 = non riguarda l'annuncio visto, 1 = in parte, 2 = riguarda chiaramente ciò che si vede",
        },
    }


def _mean(values):
    return float(np.mean(values)) if values else None


def score_rubric(ratings_by_rater, key, records):
    """Human ratings against the automated flags: do raters agree with each other, and with the lexical checks."""
    by_key = {r["key"]: r for r in records}
    by_rater = {
        rater: {row["blind_id"]: {d: int(row[d]) for d in DIMENSIONS} for row in rows}
        for rater, rows in ratings_by_rater.items()
    }
    pooled = {d: [v[d] for rows in by_rater.values() for v in rows.values()] for d in DIMENSIONS}
    agreement = None
    if len(by_rater) >= 2:
        first, second = list(by_rater.values())[:2]
        common = sorted(set(first) & set(second))
        agreement = {}
        for d in DIMENSIONS:
            a, b = [first[i][d] for i in common], [second[i][d] for i in common]
            kappa = None if len(set(a) | set(b)) < 2 else float(cohen_kappa_score(a, b, weights="linear"))
            agreement[d] = {"weighted_kappa": kappa, "items": len(common)}
    flagged, clean, grounded, ungrounded = [], [], [], []
    for rows in by_rater.values():
        for blind, values in rows.items():
            record = by_key[key[blind]]
            bad = marketer_speak(record) or bool(inconsistencies(record))
            (flagged if bad else clean).append(values["realism"])
            (grounded if references_ad(record) else ungrounded).append(values["groundedness"])
    return {
        "raters": len(by_rater),
        "items": len({b for rows in by_rater.values() for b in rows}),
        "mean": {d: _mean(v) for d, v in pooled.items()},
        "agreement": agreement,
        "automated_vs_human": {
            "flagged_mean_realism": _mean(flagged),
            "unflagged_mean_realism": _mean(clean),
            "grounded_mean_groundedness": _mean(grounded),
            "ungrounded_flag_mean_groundedness": _mean(ungrounded),
        },
    }
