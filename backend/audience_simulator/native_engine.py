"""Engine ``agent_native``: the personas' own decisions are the click probabilities.

Each persona answered, per creative, regime and frequency slot, how many times out of 100 they would skip, stop, engage
and click (``reactions.py``). Here those answers are mixed over the frequency slots, weighted by the share of the
audience each persona represents (``population_weight``), and applied to the delivery of the reference forecast
(impressions, spend and CPM do not depend on the panel). Nothing is reconciled to the historical CTR: the forecast stays
beside the result as a reference, with a divergence flag. Every number is the model's hypothesis about simulated people:
the mode is not validated against real delivery and is labelled so.
"""

from collections import Counter

import numpy as np

from .audience import stable_seed
from .context import calendar_regime
from .decision_quality import assess_decisions
from .schemas import AGES
from .stimulus_view import SLOTS

ENGINE_VERSION = "agent-native-v1"
# Share of impressions that are a person's 1st, 2nd-3rd and 4th+ view. Declared assumption, replaced by a cap if set.
DEFAULT_SLOT_MIX = {"first": 0.45, "repeat": 0.35, "saturated": 0.20}
DIVERGENCE_FACTOR = 2.0
TRACE_LIMIT = 10000
LOW_SAMPLE = 8
BREAKDOWNS = (
    "age_band",
    "placement",
    "household",
    "pet_species",
    "gender",
    "income_band",
    "urbanicity",
    "device_os",
    "in_ideal_target",
)
OUTCOMES = ("skipped", "stopped", "engaged", "clicked")


def slot_mix(targeting, available):
    """Share of impressions per frequency slot, from the frequency cap if set, else a declared default."""
    cap = targeting.frequency_cap if targeting is not None else None
    if cap is not None:
        k = cap.max_impressions
        mix = {"first": 1 / k, "repeat": (min(k, 3) - 1) / k, "saturated": max(0, k - 3) / k}
        source = "frequency_cap"
    else:
        mix, source = dict(DEFAULT_SLOT_MIX), "assumed_default"
    used = {s: v for s, v in mix.items() if s in available and v > 0}
    if not used:
        raise ValueError("Nessuno slot di frequenza valutato corrisponde al mix di impression")
    total = sum(used.values())
    return {s: v / total for s, v in used.items()}, {
        "source": source,
        "slots_used": sorted(used, key=SLOTS.index),
        "renormalized": abs(total - 1) > 1e-9,
    }


def _ad_ctr_draws(draws, indices):
    impressions = draws["impressions"][:, indices].sum(axis=1)
    clicks = (draws["impressions"][:, indices] * draws["p"][:, indices]).sum(axis=1)
    return np.divide(
        clicks * 100, impressions, out=draws["p"][:, indices].mean(axis=1) * 100, where=impressions > 0
    )


def decision_diagnostics(records):
    """Descriptive checks on the decisions. Not a measure of realism."""
    groups = []
    for creative_id in sorted({r["creative_id"] for r in records}):
        rows = [r["decision"] for r in records if r["creative_id"] == creative_id]
        impressions = Counter(" ".join(d["first_impression"].casefold().split()) for d in rows)
        vectors = {tuple(d[f"{n}_per_100"] for n in ("skip", "stop", "engage", "click")) for d in rows}
        repetition = impressions.most_common(1)[0][1] / len(rows)
        mean_skip = float(np.mean([d["skip_per_100"] for d in rows]))
        flags = []
        if len(rows) >= 6 and repetition >= 0.5:
            flags.append("repetitive_reactions")
        if len(rows) >= 6 and len(vectors) == 1:
            flags.append("uniform_decisions")
        if len(rows) >= 6 and mean_skip < 50:
            flags.append("implausibly_high_attention")
        groups.append(
            {
                "creative_id": creative_id,
                "decisions": len(rows),
                "distinct_first_impressions": len(impressions),
                "most_repeated_fraction": repetition,
                "distinct_decision_vectors": len(vectors),
                "mean_skip_per_100": mean_skip,
                "actions": dict(Counter(d["action_if_engaged"] for d in rows)),
                "flags": flags,
            }
        )
    return {
        "by_creative": groups,
        "human_behavior_validated": False,
        "warning": "Controlli descrittivi sulle risposte del modello, non osservazioni umane.",
    }


def simulate_agent_native(brief, profiles, plan, decisions, predictions, draws):
    """Apply the personas' decisions to the reference delivery. Mutates ``predictions`` and returns the new draws."""
    n = len(profiles)
    agents = [p["agent_id"] for p in profiles]
    index = {a: i for i, a in enumerate(agents)}
    weights = np.array([p["population_weight"] for p in profiles], float)
    weights = weights / weights.sum()
    band_of = np.array([AGES.index(p["age_band"]) for p in profiles])
    band_members = [np.flatnonzero(band_of == b) for b in range(len(AGES))]
    share = np.array([weights[m].sum() for m in band_members])
    available = {item["slot"] for item in plan}
    mix, mix_info = slot_mix(brief.targeting, available)
    lookup = {(i["agent_id"], i["creative_id"], i["regime"], i["slot"]): i["key"] for i in plan}
    placement_of = {i["agent_id"]: i["placement"] for i in plan}
    arrays = {}
    for item in plan:
        weight = mix.get(item["slot"], 0.0)
        if not weight:
            continue
        gates = decisions[item["key"]]["decision"]["gates"]
        slot = arrays.setdefault(
            (item["creative_id"], item["regime"]), {k: np.zeros(n) for k in ("notice", "engage", "click")}
        )
        for name in slot:
            slot[name][index[item["agent_id"]]] += weight * gates[name]
    n_draws = draws["p"].shape[0]
    rng = np.random.default_rng(stable_seed(brief.seed, "agent-native-bootstrap"))
    boots = [rng.integers(0, len(m), (n_draws, len(m))) if len(m) else None for m in band_members]
    cache = {}

    def band_draws(ckey):
        if ckey not in cache:
            click = arrays[ckey]["click"]
            cache[ckey] = [
                click[m][boots[b]].mean(axis=1) if len(m) else np.zeros(n_draws)
                for b, m in enumerate(band_members)
            ]
        return cache[ckey]

    p_draws = np.zeros_like(draws["p"])
    rows_by_ad = {}
    for r, row in enumerate(predictions):
        rows_by_ad.setdefault(row["ad_id"], []).append(r)
        ckey = (row["ad_id"], calendar_regime(row["date"]))
        band_p = band_draws(ckey)
        click = arrays[ckey]["click"]
        band_ctr = np.array([click[m].mean() if len(m) else 0.0 for m in band_members])
        impressions, spend = row["expected_impressions"], row["expected_spend"]
        reference = {
            "ctr_pred": row["ctr_pred"],
            "ctr_interval": row.get("ctr_interval"),
            "expected_clicks": row["expected_clicks"],
        }
        clicks_b = impressions * share * band_ctr
        clicks = float(clicks_b.sum())
        p_draws[:, r] = sum(share[b] * band_p[b] for b in range(len(AGES)))
        row["ctr_pred"] = 100 * clicks / impressions if impressions else float(100 * (share * band_ctr).sum())
        row["expected_clicks"] = clicks
        row["ctr_interval"] = np.quantile(p_draws[:, r] * 100, [0.05, 0.95]).tolist()
        row["reference_forecast"] = reference
        row["confidence_status"] = "unvalidated"
        row["assumptions"] = [
            *row.get("assumptions", []),
            "agent_native_decisions_as_ctr",
            f"slot_mix_{mix_info['source']}",
            "delivery_independent_of_panel",
        ]
        row["ages"] = [
            {
                "age_band": band,
                "impression_share": float(share[b]),
                "expected_impressions": float(impressions * share[b]),
                "clicks_estimate": float(clicks_b[b]),
                "expected_spend": float(spend * share[b]),
                "ctr_estimate": float(100 * band_ctr[b]),
                "ctr_range": np.quantile(band_p[b] * 100, [0.05, 0.95]).tolist(),
                "cpm_pred": None,
                "evidence_level": "modeled_assumption",
                "audience_mode": "agent_native",
                "confidence_status": "unvalidated",
                "assumptions": ["agent_native_decisions_as_ctr", "reach_share_from_targeting"],
                "not_reached_in_scenario": not len(band_members[b]),
                "reason": "Decisioni delle persone simulate nel pannello, condizionate a modello e prompt; non misura demografica."
                if len(band_members[b])
                else "Fascia non raggiunta dal targeting.",
            }
            for b, band in enumerate(AGES)
        ]
    new_draws = {**draws, "p": p_draws, "clicks": draws["impressions"] * p_draws}
    divergence = _divergence(predictions, draws, rows_by_ad)
    events, states = _trace(brief, profiles, predictions, lookup, decisions, mix, placement_of, weights)
    return {
        "draws": new_draws,
        "behavior": _behavior(brief, profiles, plan, decisions, predictions, arrays, weights, events, states),
        "native": {
            "engine_version": ENGINE_VERSION,
            "slot_mix": {**mix, "info": mix_info},
            "breakdowns": _breakdowns(brief, profiles, predictions, arrays, weights, placement_of),
            "divergence": divergence,
            "reach_share_by_age": {band: float(share[b]) for b, band in enumerate(AGES)},
            "validated": False,
            "evidence": "modeled_assumption",
            "uncertainty": "Intervalli: ricampionamento delle persone del pannello. Non includono la variabilità del modello "
            "linguistico, del prompt né l'errore delle ipotesi sul pubblico.",
        },
    }


def _divergence(predictions, reference_draws, rows_by_ad):
    result = []
    for ad, indices in rows_by_ad.items():
        impressions = sum(predictions[i]["expected_impressions"] for i in indices)
        native = (
            100 * sum(predictions[i]["expected_clicks"] for i in indices) / impressions
            if impressions
            else 0.0
        )
        ref_clicks = sum(predictions[i]["reference_forecast"]["expected_clicks"] for i in indices)
        reference = 100 * ref_clicks / impressions if impressions else 0.0
        low, high = np.quantile(_ad_ctr_draws(reference_draws, indices), [0.05, 0.95])
        ratio = native / reference if reference > 0 else None
        flags = []
        if not low <= native <= high:
            flags.append("outside_reference_interval")
        if ratio is not None and not 1 / DIVERGENCE_FACTOR <= ratio <= DIVERGENCE_FACTOR:
            flags.append("more_than_2x_from_reference")
        result.append(
            {
                "ad_id": ad,
                "agent_native_ctr": native,
                "reference_ctr": reference,
                "reference_interval": [float(low), float(high)],
                "ratio": ratio,
                "flags": flags,
                "diverges": bool(flags),
            }
        )
    return result


def _trace(brief, profiles, predictions, lookup, decisions, mix, placement_of, weights):
    slots = list(mix)
    cumulative = np.cumsum([mix[s] for s in slots])
    events, counts = [], Counter()
    for creative in brief.creatives:
        for row in (r for r in predictions if r["ad_id"] == creative.id):
            regime = calendar_regime(row["date"])
            for i, profile in enumerate(profiles):
                aid = profile["agent_id"]
                # The creative is not part of the seed: alternatives share the same uniforms (paired comparison).
                u_slot, u_out = np.random.default_rng(
                    stable_seed(brief.seed, aid, row["date"], "native")
                ).random(2)
                slot = slots[min(int(np.searchsorted(cumulative, u_slot, side="right")), len(slots) - 1)]
                decision = decisions[lookup[(aid, creative.id, regime, slot)]]["decision"]
                probs = [decision[f"{n}_per_100"] / 100 for n in ("skip", "stop", "engage", "click")]
                outcome = OUTCOMES[min(int(np.searchsorted(np.cumsum(probs), u_out, side="right")), 3)]
                counts[(aid, creative.id)] += 1
                if len(events) < TRACE_LIMIT:
                    noticed = outcome != "skipped"
                    events.append(
                        {
                            "agent_id": aid,
                            "ad_id": creative.id,
                            "date": row["date"],
                            "replicate": 0,
                            "exposure_id": str(stable_seed(brief.seed, aid, creative.id, row["date"], 0)),
                            "slot": slot,
                            "outcome": outcome,
                            "noticed": noticed,
                            "relevant": outcome in {"engaged", "clicked"},
                            "clicked": outcome == "clicked",
                            "stated_action": decision["action_if_engaged"],
                            "stated_action_used_in_gates": True,
                            "attention_probability": decision["gates"]["notice"],
                            "click_probability": decision["gates"]["click"],
                            "raw_click_probability": decision["gates"]["click"],
                            "gate_reconciliation_adjustment": None,
                            "weight": float(weights[i]),
                            "source_type": "simulation",
                            "evidence_level": "modeled_assumption",
                            "explanation": decision["first_impression"] if noticed else None,
                            "explanation_evidence": "agent_decision_hypothesis"
                            if noticed
                            else "not_available_for_ignored_exposure",
                            "exposure_context": {
                                "placement": placement_of[aid],
                                "placement_source": "targeting_delivery_assumption",
                                "device": brief.device,
                                "task": brief.browsing_task,
                                "calendar_regime": regime,
                            },
                        }
                    )
    states = [
        {
            "agent_id": a,
            "arm": c,
            "replicate": 0,
            "familiarity": next(p["brand_familiarity"] for p in profiles if p["agent_id"] == a),
            "exposure_count": k,
        }
        for (a, c), k in sorted(counts.items())
    ]
    return events, states


def _behavior(brief, profiles, plan, decisions, predictions, arrays, weights, events, states):
    records = [
        {
            "agent_id": i["agent_id"],
            "creative_id": i["creative_id"],
            "decision": decisions[i["key"]]["decision"],
        }
        for i in plan
    ]
    summaries = []
    for creative in brief.creatives:
        rows = [r for r in predictions if r["ad_id"] == creative.id]
        total = sum(r["expected_impressions"] for r in rows)
        summaries.append(
            {
                "ad_id": creative.id,
                "raw_panel_ctr": 100 * sum(r["expected_clicks"] for r in rows) / total if total else 0.0,
                "evidence_level": "modeled_assumption",
                "label": "CTR dalle decisioni degli agenti: ipotesi non validata, non è ancorato al forecast storico",
            }
        )
    findings = []
    by_agent = {p["agent_id"]: p for p in profiles}
    for creative in brief.creatives:
        for band in AGES:
            rows = [
                r
                for r in records
                if r["creative_id"] == creative.id and by_agent[r["agent_id"]]["age_band"] == band
            ]
            if not rows:
                continue
            decisions_ = [r["decision"] for r in rows]
            findings.append(
                {
                    "ad_id": creative.id,
                    "age_band": band,
                    "policy_count": len(rows),
                    "frictions": dict(Counter(f for d in decisions_ for f in d["frictions"])),
                    "per_100": {
                        name: float(np.mean([d[f"{name}_per_100"] for d in decisions_]))
                        for name in ("skip", "stop", "engage", "click")
                    },
                    "evidence": sorted({e for d in decisions_ for e in d["evidence"]}),
                }
            )
    return {
        "events": events,
        "states": states,
        "raw_panel": summaries,
        "policy_findings": findings,
        "policy_quality": decision_diagnostics(records),
        "reaction_quality": assess_decisions(
            [
                {
                    "key": i["key"],
                    "agent_id": i["agent_id"],
                    "creative_id": i["creative_id"],
                    "slot": i["slot"],
                    "input": i["input"],
                    "decision": decisions[i["key"]]["decision"],
                }
                for i in plan
            ],
            {p["agent_id"]: p for p in profiles},
        ),
        "trace_limit": TRACE_LIMIT,
        "replicates": 1,
        "warning": "Esposizioni sintetiche campionate dalle stime delle persone; non un evento per ogni impression prevista.",
    }


def _breakdowns(brief, profiles, predictions, arrays, weights, placement_of):
    """Weighted rates per segment, impression-weighted over the campaign days. ``low_sample`` flags groups under 8 people."""
    result = []
    for creative in brief.creatives:
        rows = [r for r in predictions if r["ad_id"] == creative.id]
        regime_weight = Counter()
        for row in rows:
            regime_weight[calendar_regime(row["date"])] += row["expected_impressions"] or 1e-9
        total = sum(regime_weight.values())
        person = {
            name: sum(arrays[(creative.id, reg)][name] * w / total for reg, w in regime_weight.items())
            for name in ("notice", "engage", "click")
        }
        segments = {}
        for dimension in BREAKDOWNS:
            groups = {}
            for i, profile in enumerate(profiles):
                value = (
                    placement_of[profile["agent_id"]] if dimension == "placement" else profile.get(dimension)
                )
                if value is None:
                    continue
                groups.setdefault(str(value).lower() if isinstance(value, bool) else str(value), []).append(i)
            segments[dimension] = [
                {
                    "key": key,
                    "personas": len(members),
                    "reach_share": float(weights[members].sum()),
                    "notice_rate": float(np.average(person["notice"][members], weights=weights[members])),
                    "engage_rate": float(np.average(person["engage"][members], weights=weights[members])),
                    "ctr_pct": float(100 * np.average(person["click"][members], weights=weights[members])),
                    "low_sample": len(members) < LOW_SAMPLE,
                }
                for key, members in sorted(groups.items())
            ]
        result.append({"ad_id": creative.id, "segments": segments})
    return result
