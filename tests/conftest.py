from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_credentials_key(tmp_path_factory, monkeypatch):
    # I test non devono mai creare o leggere la vera chiave di cifratura in ~/.audience-simulator.
    monkeypatch.setenv("AUDIENCE_CREDENTIALS_KEY_FILE", str(tmp_path_factory.mktemp("keys") / "credentials.key"))


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
        "test_agent_decisions_are_the_ctr_and_the_forecast_is_only_a_reference",
        "test_each_persona_decision_moves_the_result_and_segments_show_why",
        "test_frequency_slots_are_mixed_by_the_assumed_impression_shares",
        "test_trace_events_share_uniforms_across_creatives_and_carry_the_decision",
        "test_resume_after_quota_reuses_cards_and_finished_reactions",
        "test_full_run_on_a_targeted_panel_skips_bands_that_are_not_reached",
        "test_agent_native_run_reports_real_reaction_quality_and_exports_a_rubric",
    }
    for item in items:
        if Path(str(item.fspath)).name in kit_modules or item.originalname in kit_tests:
            item.add_marker(
                pytest.mark.skip(
                    reason="Kit CSV non distribuito: materializzare data/ per l'integrazione completa"
                )
            )
