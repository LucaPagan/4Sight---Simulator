import csv
import io
import json
from collections import Counter

import numpy as np

from .schemas import AGES


def audit_predictions(rows, daily_budget):
    if not rows:
        raise ValueError("Nessuna previsione da pubblicare")
    spending = Counter()
    for row in rows:
        keys = ("ctr_pred", "cpm_pred", "expected_impressions", "expected_clicks", "expected_spend")
        if any(not np.isfinite(row[k]) or row[k] < 0 for k in keys) or row["ctr_pred"] > 100:
            raise ValueError("KPI non validi")
        if not np.isclose(
            row["expected_clicks"], row["expected_impressions"] * row["ctr_pred"] / 100, atol=1e-7
        ):
            raise ValueError("Identità CTR non rispettata")
        ages = row["ages"]
        if sorted(a["age_band"] for a in ages) != sorted(AGES):
            raise ValueError("Fasce età mancanti o duplicate")
        for age_key, total_key in [
            ("expected_impressions", "expected_impressions"),
            ("clicks_estimate", "expected_clicks"),
            ("expected_spend", "expected_spend"),
        ]:
            if any(not np.isfinite(a[age_key]) or a[age_key] < 0 for a in ages) or not np.isclose(
                sum(a[age_key] for a in ages), row[total_key], atol=1e-7, rtol=1e-10
            ):
                raise ValueError("Totali per età non riconciliati")
        spending[row["date"]] += row["expected_spend"]
    if any(value > daily_budget + 0.000001 for value in spending.values()):
        raise ValueError("Spesa oltre il budget giornaliero condiviso")


def csv_export(rows, age=False):
    values = []
    for row in rows:
        base = {k: v for k, v in row.items() if k != "ages"}
        if age:
            values.extend({"date": row["date"], "ad_id": row["ad_id"], **a} for a in row.get("ages", []))
        else:
            values.append(base)
    fields = list(dict.fromkeys(k for r in values for k in r))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in values:
        safe = {}
        for key, value in row.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, allow_nan=False)
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                value = "'" + value
            safe[key] = value
        writer.writerow(safe)
    return stream.getvalue().encode("utf-8-sig")


def compare_predictions(rows, draws):
    ads = list(dict.fromkeys(r["ad_id"] for r in rows))
    summaries = []
    ctr_by_ad = {}
    for ad in ads:
        idx = [i for i, r in enumerate(rows) if r["ad_id"] == ad]
        impressions = draws["impressions"][:, idx].sum(axis=1)
        clicks = (draws["impressions"][:, idx] * draws["p"][:, idx]).sum(axis=1)
        ctr = np.divide(
            clicks * 100, impressions, out=draws["p"][:, idx].mean(axis=1) * 100, where=impressions > 0
        )
        ctr_by_ad[ad] = ctr
        total_i = sum(rows[i]["expected_impressions"] for i in idx)
        total_c = sum(rows[i]["expected_clicks"] for i in idx)
        total_s = sum(rows[i]["expected_spend"] for i in idx)
        summaries.append(
            {
                "ad_id": ad,
                "ctr_pred": total_c / total_i * 100 if total_i else float(ctr.mean()),
                "ctr_interval": np.quantile(ctr, [0.05, 0.95]).tolist(),
                "expected_impressions": total_i,
                "expected_clicks": total_c,
                "expected_spend": total_s,
                "cpm_pred": total_s / total_i * 1000 if total_i else 0,
            }
        )
    pairs = []
    for i, a in enumerate(ads):
        for b in ads[i + 1 :]:
            delta = ctr_by_ad[a] - ctr_by_ad[b]
            p = float(np.mean(delta > 0.1))
            p_reverse = float(np.mean(delta < -0.1))
            tie = float(np.mean(abs(delta) <= 0.1))
            winner = a if p >= 0.95 else b if p_reverse >= 0.95 else None
            pairs.append(
                {
                    "a": a,
                    "b": b,
                    "difference_pp": float(delta.mean()),
                    "difference_interval": np.quantile(delta, [0.05, 0.95]).tolist(),
                    "probability_a_better": p,
                    "probability_b_better": p_reverse,
                    "probability_practical_tie": tie,
                    "winner": winner,
                    "status": "winner_under_model"
                    if winner
                    else "practical_tie"
                    if tie >= 0.8
                    else "uncertain",
                }
            )
    return {
        "creatives": sorted(summaries, key=lambda r: -r["ctr_pred"]),
        "pairwise": pairs,
        "warning": "Probabilità condizionate al modello; non significatività causale. Stesso panel e calendario, budget condiviso.",
    }


def build_report(brief, predictions, behavior, comparison, coverage):
    diagnoses = []
    for creative in brief.creatives:
        # Missing price is injected by input validation, not discovered independently by consumers.
        findings = [
            {**f, "frictions": {k: v for k, v in f["frictions"].items() if k != "price_unknown"}}
            for f in behavior.get("policy_findings", [])
            if f["ad_id"] == creative.id
        ]
        counts = Counter()
        for finding in findings:
            counts.update(finding["frictions"])
        main = counts.most_common(3)
        description = (
            ", ".join(f"{name} ({count} policy)" for name, count in main)
            or "nessuna frizione esplicita nel panel"
        )
        diagnoses.append(
            {
                "creative_id": creative.id,
                "evidence_level": "qualitative_hypothesis",
                "features": sorted({r for f in findings for r in f["evidence"]}),
                "hypothesis": f"Il panel segnala {description}. Verificare queste ipotesi con utenti reali.",
                "evidence": {"frictions": dict(counts), "by_age": findings},
                "claim_status": "verified_by_user" if creative.claim_verified else "claim_unverified",
                "experiment": {
                    "hypothesis": f"Una variante che affronta {main[0][0] if main else 'la chiarezza del messaggio'} può ridurre la frizione segnalata",
                    "metric": "link CTR",
                    "design": "A/B randomizzato, audience e budget comparabili; durata, MDE e stopping rule prestabiliti",
                },
            }
        )
    return {
        "title": brief.name,
        "coverage": coverage,
        "panel_quality": behavior.get("policy_quality"),
        "input_gaps": [
            {
                "field": "price_eur",
                "source": "input_validation",
                "message": "Prezzo non indicato: informazione mancante nel brief.",
            }
        ]
        if brief.price_eur is None
        else [],
        "measurement_status": {
            "certified": False,
            "human_observations": 0,
            "aggregate_kpi_source": "historical_baseline",
            "agents_change_aggregate_kpis": False,
            "stated_action_used_in_gates": False,
            "behavioral_validity": "not_validated_against_human_responses",
            "aggregate_accuracy": "not_validated_on_real_campaigns",
            "agent_contribution": "Ipotesi qualitative, reazioni condizionali e scenario per età.",
            "chart_behavior": "Le stime aggregate sono calcolate prima degli agenti e non si aggiornano con ogni reazione.",
            "completion_meaning": "Copertura delle valutazioni e controlli di coerenza completati; accuratezza predittiva non certificata.",
        },
        "age_accuracy": None,
        "consumer_voice": "Reazioni condizionali del panel sintetico, non testimonianze di persone reali.",
        "analyst_voice": "CTR/CPM ancorati allo storico; decomposizione per età e gate restano ipotesi.",
        "diagnoses": diagnoses,
        "comparison": comparison,
        "limitations": [
            "Dati del kit simulati",
            "Nessuna label individuale o per età",
            f"{brief.population_size} agenti non sono {brief.population_size} osservazioni umane indipendenti",
            "Intervalli condizionati a modello, policy e prior",
            "Ablation panel non ancora dimostrata: forecast aggregato baseline",
        ],
        "stop_go": {
            "agent_coverage": coverage["completed"] == coverage["required"],
            "age_math": True,
            "aggregate_accuracy": "unvalidated",
            "age_mode": "theory_based",
        },
    }
