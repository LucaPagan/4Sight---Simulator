from pathlib import Path

import pytest
from audience_simulator.config import Settings
from audience_simulator.native_benchmark import benchmark_native
from audience_simulator.service import SimulationService
from test_native_engine import PAYLOAD, FakeAgent


@pytest.fixture
def benchmark_service(tmp_path):
    return SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/operational.db",
            artifact_dir=tmp_path / "art",
            data_dir=Path("data"),
            queue_mode="manual",
        )
    )


def test_isolated_benchmark_freezes_inputs_and_separates_cold_and_cached(benchmark_service):
    svc = benchmark_service
    scenario = svc.create_scenario(PAYLOAD)
    before = svc.repo.get("populations", scenario["population_id"])
    agent = FakeAgent()
    report = benchmark_native(svc, scenario["id"], "fake", "fake-agent", client=agent)
    assert report["status"] == "complete" and report["cases"] == 120
    assert report["cold"]["cards"]["calls"] == 3  # 20 profiles in batches of eight
    assert report["cold"]["reactions"]["calls"] == 120
    assert report["cached"]["cards"]["calls"] == report["cached"]["reactions"]["calls"] == 0
    assert report["cached"]["reactions"]["cache_hits"] == 120
    assert svc.repo.get("populations", scenario["population_id"]) == before
    assert not svc.repo.list("agent_decisions") and not svc.repo.list("persona_cards")
    other = FakeAgent()
    other.model = "other"
    compared = benchmark_native(svc, scenario["id"], "fake", "other", client=other)
    assert compared["fixture_hash"] == report["fixture_hash"]
    assert compared["reference_hash"] == report["reference_hash"]
    assert report["qualified"] is False and Path(report["rubric_path"]).exists()


def test_benchmark_resumes_without_repeating_completed_cases(benchmark_service):
    svc = benchmark_service
    scenario = svc.create_scenario(PAYLOAD)
    first = benchmark_native(svc, scenario["id"], "fake", "fake-agent", client=FakeAgent(quota_at=5))
    assert first["status"] == "partial"
    resumed = FakeAgent()
    report = benchmark_native(svc, scenario["id"], "fake", "fake-agent", client=resumed)
    assert report["status"] == "complete" and resumed.reactions == 116
    assert not resumed.writer.calls
    assert report["cold"]["reactions"]["calls"] == 121  # includes the quota failure


def test_benchmark_rejects_unavailable_provider_and_insufficient_fixture(benchmark_service):
    svc = benchmark_service
    scenario = svc.create_scenario({**PAYLOAD, "creatives": PAYLOAD["creatives"][:1]})
    with pytest.raises(ValueError, match="creativ"):
        benchmark_native(svc, scenario["id"], "fake", "fake-agent", client=FakeAgent())
