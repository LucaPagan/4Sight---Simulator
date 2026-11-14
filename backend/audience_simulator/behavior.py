from collections import Counter

import numpy as np
from scipy.special import expit, logit

from .agents import calendar_regime
from .audience import stable_seed
from .schemas import AGES


def reconcile_gates(logits, weights, target):
    logits, weights = np.asarray(logits, float), np.asarray(weights, float)
    if (
        logits.ndim != 2
        or logits.shape[1] != 3
        or len(weights) != len(logits)
        or not np.isfinite(logits).all()
        or not np.isfinite(weights).all()
        or np.any(weights < 0)
        or not np.isclose(weights.sum(), 1)
        or not 0 <= target <= 1
    ):
        raise ValueError("Gate, pesi o target non validi")
    if target in (0, 1):
        return np.full_like(logits, target)
    low, high = -80.0, 80.0
    for _ in range(70):
        mid = (low + high) / 2
        p = np.prod(expit(logits + mid), axis=1) @ weights
        if p < target:
            low = mid
        else:
            high = mid
    return expit(logits + (low + high) / 2)


def raw_logits(profile, evaluation, state, brief):
    def score(name):
        return (evaluation[name] - 2) / 2

    fatigue = state["fatigue"]
    return np.array(
        [
            -1.1
            + 0.7 * profile["category_affinity"]
            - 0.65 * fatigue
            + (0.5 if brief.browsing_task != "casual_scrolling" else 0),
            -0.3 + score("interest") + 0.4 * score("clarity") + profile["purchase_need"],
            -2
            + score("credibility")
            - score("friction")
            - 0.6 * profile["budget_sensitivity"]
            + 0.3 * state["familiarity"],
        ]
    )


def policy_signals(brief, profiles, policy_map, plan, rows):
    lookup = {
        (p["agent_id"], p["creative_id"], p["regime"]): policy_map[p["key"]]
        for p in plan
        if p["key"] in policy_map
    }
    result = []
    for row in rows:
        regime = calendar_regime(row["date"])
        effects = []
        for band in AGES:
            scores = []
            for profile in profiles:
                if profile["age_band"] != band:
                    continue
                e = lookup[(profile["agent_id"], row["ad_id"], regime)]
                scores.append((e["interest"] + e["credibility"] - e["friction"] - 2) / 8)
            effects.append(float(np.mean(scores)))
        effects = np.array(effects)
        result.append((effects - effects.mean()).tolist())
    return result


def simulate_panel(brief, profiles, policy_map, plan, predictions, replicates=1):
    lookup = {
        (p["agent_id"], p["creative_id"], p["regime"]): policy_map[p["key"]]
        for p in plan
        if p["key"] in policy_map
    }
    events, final_states, summaries = [], [], []
    for creative in brief.creatives:
        relevant = sorted([r for r in predictions if r["ad_id"] == creative.id], key=lambda r: r["date"])
        raw_ps = []
        for rep in range(replicates):
            state = {
                p["agent_id"]: {"familiarity": p["brand_familiarity"], "fatigue": 0.0, "exposure_count": 0}
                for p in profiles
            }
            for row in relevant:
                regime = calendar_regime(row["date"])
                for band in AGES:
                    cohort = [p for p in profiles if p["age_band"] == band]
                    evaluations = [lookup[(p["agent_id"], creative.id, regime)] for p in cohort]
                    logits = np.array(
                        [raw_logits(p, e, state[p["agent_id"]], brief) for p, e in zip(cohort, evaluations)]
                    )
                    raw = np.prod(expit(logits), axis=1)
                    target = next(a["ctr_estimate"] / 100 for a in row["ages"] if a["age_band"] == band)
                    gates = reconcile_gates(logits, np.ones(len(cohort)) / len(cohort), target)
                    adjustment = float(logit(gates[0, 0]) - logits[0, 0]) if 0 < target < 1 else None
                    for profile, evaluation, gate, raw_p in zip(cohort, evaluations, gates, raw):
                        aid = profile["agent_id"]
                        # Creative excluded from seed: paired alternatives share uniforms, never memory.
                        rng = np.random.default_rng(stable_seed(brief.seed, aid, row["date"], rep, "gates"))
                        uniform = rng.random(3)
                        noticed = bool(uniform[0] < gate[0])
                        relevant_event = noticed and bool(uniform[1] < gate[1])
                        clicked = relevant_event and bool(uniform[2] < gate[2])
                        event = {
                            "agent_id": aid,
                            "ad_id": creative.id,
                            "date": row["date"],
                            "replicate": rep,
                            "exposure_id": str(stable_seed(brief.seed, aid, creative.id, row["date"], rep)),
                            "noticed": noticed,
                            "relevant": relevant_event,
                            "clicked": clicked,
                            "attention_probability": float(gate[0]),
                            "click_probability": float(np.prod(gate)),
                            "raw_click_probability": float(raw_p),
                            "gate_reconciliation_adjustment": adjustment,
                            "weight": next(
                                a.get("impression_share", profile["population_weight"] * len(cohort))
                                for a in row["ages"]
                                if a["age_band"] == band
                            )
                            / len(cohort),
                            "source_type": "simulation",
                            "evidence_level": "modeled_assumption",
                            "explanation": evaluation["conditional_reaction"] if noticed else None,
                            "explanation_evidence": "conditional_llm_hypothesis"
                            if noticed
                            else "not_available_for_ignored_exposure",
                            "exposure_context": {
                                "placement": brief.placement,
                                "placement_source": "scenario_assumption",
                                "device": "mobile",
                                "task": brief.browsing_task,
                                "calendar_regime": regime,
                                "state_before": dict(state[aid]),
                            },
                        }
                        if len(events) < 10000:
                            events.append(event)
                        raw_ps.append((float(raw_p), event["weight"] * row.get("expected_impressions", 1)))
                        state[aid]["exposure_count"] += 1
                        state[aid]["familiarity"] = min(1.0, state[aid]["familiarity"] + 0.04 * noticed)
                        state[aid]["fatigue"] = min(
                            1.0, state[aid]["fatigue"] * 0.9 + 0.08 * (1 - profile["repeat_tolerance"])
                        )
            final_states.extend(
                {"agent_id": aid, "arm": creative.id, "replicate": rep, **s} for aid, s in state.items()
            )
        numerator = sum(p * w for p, w in raw_ps)
        denominator = sum(w for _, w in raw_ps)
        summaries.append(
            {
                "ad_id": creative.id,
                "raw_panel_ctr": 100 * numerator / denominator if denominator else 0,
                "evidence_level": "modeled_assumption",
                "label": "Probabilità grezze del panel: non accuratezza osservata",
            }
        )
    findings = []
    for creative in brief.creatives:
        for band in AGES:
            ids = {p["agent_id"] for p in profiles if p["age_band"] == band}
            values = [e for (aid, cid, _), e in lookup.items() if aid in ids and cid == creative.id]
            findings.append(
                {
                    "ad_id": creative.id,
                    "age_band": band,
                    "policy_count": len(values),
                    "frictions": dict(Counter(f for e in values for f in e.get("frictions", []))),
                    "scores": {
                        k: float(np.mean([e[k] for e in values]))
                        for k in ("clarity", "interest", "credibility", "friction")
                    },
                    "evidence": sorted({r for e in values for r in e["evidence"]}),
                }
            )
    return {
        "events": events,
        "states": final_states,
        "raw_panel": summaries,
        "policy_findings": findings,
        "trace_limit": 10000,
        "replicates": replicates,
        "warning": "Esposizioni sintetiche campionate; non un evento per ogni impression prevista.",
    }
