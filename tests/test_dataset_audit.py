import shutil
from pathlib import Path

import pytest
from audience_simulator.datasets import audit_dataset, load_dataset


def test_kit_audit_preserves_raw_and_reports_known_anomalies():
    result = audit_dataset(Path("data"))
    assert result["counts"]["storico_giornaliero.csv"] == 1879
    assert result["counts"]["da_prevedere.csv"] == 699
    assert result["split_counts"] == {"addestramento": 1435, "validazione": 444}
    assert result["cpc_missing_zero_click"] == 9
    assert result["budget_period_mismatches"] == 168
    assert len(result["overspend"]) == 2
    assert result["errors"] == []
    assert result["overspend"][0]["adset_id"] == "FGR-AS1"
    assert result["overspend"][0]["severity"] == "error"
    assert (
        load_dataset(Path("data"))["history"]
        .loc[lambda x: (x.data == "2026-10-21") & (x.adset_id == "FGR-AS1"), "spesa"]
        .iloc[0]
        == 397.55
    )


def test_duplicate_target_and_missing_foreign_key_are_rejected(tmp_path):
    shutil.copytree("data", tmp_path / "kit")
    target = tmp_path / "kit/da_prevedere.csv"
    lines = target.read_text().splitlines()
    target.write_text("\n".join(lines + [lines[1]]) + "\n")
    result = audit_dataset(tmp_path / "kit")
    assert any("duplicate" in e for e in result["errors"])
    with pytest.raises(ValueError):
        load_dataset(tmp_path / "kit", validate=True)


def test_manifest_hash_changes_when_input_changes(tmp_path):
    shutil.copytree("data", tmp_path / "kit")
    before = audit_dataset(tmp_path / "kit")["dataset_hash"]
    path = tmp_path / "kit/inserzionisti.csv"
    path.write_text(path.read_text().replace("Nuvola", "Nuvola nuova"))
    assert audit_dataset(tmp_path / "kit")["dataset_hash"] != before
