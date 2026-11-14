import shutil
from pathlib import Path

import pytest
from audience_simulator.datasets import audit_dataset


@pytest.mark.skipif(not Path("data/storico_giornaliero.csv").exists(), reason="Kit CSV locale richiesto")
def test_non_numeric_budget_is_a_validation_error(tmp_path):
    shutil.copytree("data", tmp_path / "data")
    file = tmp_path / "data/da_prevedere.csv"
    import pandas as pd

    rows = pd.read_csv(file)
    rows["budget_giornaliero_adset"] = rows["budget_giornaliero_adset"].astype(str)
    rows.loc[0, "budget_giornaliero_adset"] = "not-a-number"
    rows.to_csv(file, index=False)
    audit = audit_dataset(tmp_path / "data")
    assert any("numeric" in e for e in audit["errors"])
