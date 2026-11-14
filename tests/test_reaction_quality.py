import csv
import io

import pytest
from audience_simulator.reaction_quality import (
    assess_panel,
    export_rubric,
    invented_numbers,
    profile_inconsistencies,
    references_creative,
    score_rubric,
)


def record(
    reaction, *, key="k", interest=2, action="defer", clarity=2, credibility=2, evidence=None, **payload
):
    creative = {
        "id": "A",
        "headline": "Crema idratante intensiva",
        "primary_text": "Idratazione per 24 ore con acido ialuronico",
        "offer": "",
        "price_text": "",
        "cta": "Scopri di più",
    }
    creative.update(payload.pop("creative", {}))
    profile = {
        "agent_id": key,
        "age_band": "25-34",
        "purchase_need": 0.5,
        "category_affinity": 0.5,
        "budget_sensitivity": 0.5,
    }
    profile.update(payload.pop("profile", {}))
    campaign = {"price_eur": None, "objective": "vendite", "country": "IT"}
    campaign.update(payload.pop("campaign", {}))
    return {
        "key": key,
        "input": {"creative": creative, "profile": profile, "campaign": campaign},
        "evaluation": {
            "clarity": clarity,
            "interest": interest,
            "credibility": credibility,
            "friction": 2,
            "conditional_action": action,
            "evidence": evidence or ["creative.headline"],
            "conditional_reaction": reaction,
            "frictions": [],
            "unknowns": [],
        },
    }


def test_reaction_that_quotes_the_creative_is_grounded_and_a_generic_one_is_not():
    assert references_creative(record("L'acido ialuronico mi incuriosisce"))
    generic = record("Non so, forse magari", evidence=["profile.age_band"])
    assert not references_creative(generic)


def test_declaring_creative_evidence_is_not_grounding_without_content_in_the_reaction():
    assert not references_creative(record("Mi sembra interessante", evidence=["creative.primary_text"]))


def test_numbers_absent_from_the_input_are_flagged_as_invented():
    assert invented_numbers(record("Con il 30% di sconto lo prenderei")) == ["30"]
    assert invented_numbers(record("24 ore sono poche")) == []
    given = record("A 19,90 € è ok", creative={"price_text": "19,90 €"})
    assert invented_numbers(given) == []


def test_action_must_agree_with_scores_and_profile():
    assert profile_inconsistencies(record("x", interest=0, action="consider_click"))
    assert profile_inconsistencies(record("x", interest=4, action="not_interested"))
    assert profile_inconsistencies(
        record(
            "x",
            interest=2,
            action="not_interested",
            clarity=4,
            credibility=4,
            profile={"purchase_need": 0.95, "category_affinity": 0.95},
        )
    )
    assert not profile_inconsistencies(record("x", interest=3, action="consider_click"))


def panel(reactions, **kwargs):
    return [record(text, key=f"k{i}", **kwargs) for i, text in enumerate(reactions)]


def test_missing_price_is_summarized_as_one_brief_limit_not_as_many_findings():
    records = panel(["Il prezzo non c'è, aspetto"] * 8 + ["L'acido ialuronico mi piace"] * 2)
    result = assess_panel(records)
    assert result["brief_limit"]["price_missing"] is True
    assert result["brief_limit"]["share_mentioning_price"] == 0.8
    assert "brief_limit_dominates" in result["flags"]


def test_price_mentions_are_not_a_limit_when_the_price_is_known():
    records = panel(["Il prezzo è giusto"] * 6, campaign={"price_eur": 20.0})
    result = assess_panel(records)
    assert result["brief_limit"]["price_missing"] is False
    assert "brief_limit_dominates" not in result["flags"]


def test_conceptual_repetition_is_detected_across_different_wording():
    texts = [
        "Non vedo il prezzo e quindi aspetto",
        "Senza il prezzo preferisco aspettare",
        "Aspetto, il prezzo non è indicato",
        "Prezzo non indicato: aspetto prima di decidere",
        "Idratazione per ventiquattro ore, curiosa dell'acido ialuronico",
        "Mi interessa la texture della crema intensiva",
    ]
    result = assess_panel(panel(texts))
    assert result["repetition"]["largest_cluster_share"] >= 0.6
    assert "conceptual_repetition" in result["flags"]


def test_diverse_grounded_panel_has_no_flags():
    texts = [
        "L'acido ialuronico mi incuriosisce per la pelle secca",
        "Idratazione per 24 ore è una promessa forte per l'inverno",
        "La crema intensiva potrebbe sostituire la mia routine",
        "Il titolo parla chiaro: idratante e basta",
        "Scopri di più: vorrei vedere gli ingredienti",
        "Una crema con acido ialuronico la valuterei dopo le recensioni",
    ]
    result = assess_panel(panel(texts, campaign={"price_eur": 20.0}))
    assert result["flags"] == []
    assert result["grounded_share"] == 1.0
    assert result["human_validated"] is False


def test_rubric_export_is_blind_deterministic_and_keeps_the_key_separate():
    records = panel([f"reazione {i} sulla crema idratante" for i in range(30)])
    first = export_rubric(records, n=10, seed=1)
    assert first == export_rubric(list(reversed(records)), n=10, seed=1)
    rows = list(csv.DictReader(io.StringIO(first["csv"])))
    assert len(rows) == 10
    assert set(rows[0]) >= {
        "blind_id",
        "creative",
        "profile",
        "reaction",
        "groundedness",
        "coherence",
        "usefulness",
    }
    assert "agent_id" not in first["csv"] and "conditional_action" not in first["csv"]
    assert set(first["key"]) == {r["blind_id"] for r in rows}


def test_rubric_scoring_reports_agreement_and_checks_automated_flags_against_humans():
    records = panel(
        ["L'acido ialuronico mi incuriosisce"] * 6 + ["Non so, forse magari"] * 6, campaign={"price_eur": 20}
    )
    for r in records[6:]:
        r["input"]["creative"]["headline"] = "Titolo senza parole in comune"
        r["input"]["creative"]["primary_text"] = "Altro testo"
        r["evaluation"]["evidence"] = ["profile.age_band"]
    exported = export_rubric(records, n=12, seed=0)
    rows = list(csv.DictReader(io.StringIO(exported["csv"])))
    texts = {r["blind_id"]: r["reaction"] for r in rows}

    def rate(rater, noise=0):
        out = []
        for row in rows:
            good = "ialuronico" in texts[row["blind_id"]]
            out.append({**row, "groundedness": 2 if good else 0, "coherence": 2, "usefulness": 1 + noise})
        return out

    result = score_rubric({"r1": rate("r1"), "r2": rate("r2")}, exported["key"], records)
    assert result["raters"] == 2
    assert result["agreement"]["groundedness"]["weighted_kappa"] == pytest.approx(1.0)
    assert result["mean"]["groundedness"] == pytest.approx(1.0)
    assert (
        result["automated_vs_human"]["ungrounded_flag_mean_groundedness"]
        < result["automated_vs_human"]["grounded_mean_groundedness"]
    )


def test_rubric_with_one_rater_has_no_agreement_claim():
    records = panel(["reazione crema"] * 4)
    exported = export_rubric(records, n=4, seed=0)
    rows = [
        {**r, "groundedness": 1, "coherence": 1, "usefulness": 1}
        for r in csv.DictReader(io.StringIO(exported["csv"]))
    ]
    result = score_rubric({"r1": rows}, exported["key"], records)
    assert result["agreement"] is None
