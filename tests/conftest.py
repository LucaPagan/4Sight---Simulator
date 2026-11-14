from pathlib import Path

import pytest


def pytest_collection_modifyitems(items):
    if Path("data/storico_giornaliero.csv").exists():
        return
    # The challenge kit is intentionally not redistributed; pure numerical/agent tests still run in CI.
    kit_modules = {"test_dataset_audit.py", "test_forecasting.py"}
    kit_tests = {
        "test_full_120_agent_simulation_and_resume_uses_snapshot",
        "test_capacity_resume_only_evaluates_missing_policy",
        "test_cli_audit_works_without_network",
        "test_imported_dataset_applies_to_new_scenarios_but_old_snapshot_stays",
        "test_cancel_during_behavior_cannot_be_overwritten_by_publication",
        "test_cpm_calibration_matches_ridge_when_ctr_smoothing_wins",
    }
    for item in items:
        if Path(str(item.fspath)).name in kit_modules or item.originalname in kit_tests:
            item.add_marker(
                pytest.mark.skip(
                    reason="Kit CSV non distribuito: materializzare data/ per l'integrazione completa"
                )
            )
