import os
from datetime import UTC, datetime, timedelta

from audience_simulator.cleanup import cleanup
from audience_simulator.config import Settings
from audience_simulator.service import SimulationService


def test_cleanup_dry_run_then_removes_only_expired_logs(tmp_path):
    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art")
    )
    old = service.store.path("old.log")
    old.write_text("debug")
    current = service.store.path("current.log")
    current.write_text("debug")
    raw = service.store.path("immutable.json")
    raw.write_text("{}")
    time = (datetime.now(UTC) - timedelta(days=31)).timestamp()
    os.utime(old, (time, time))
    os.utime(raw, (time, time))
    assert cleanup(service)["expired_logs"] == 1
    assert old.exists()
    cleanup(service, apply=True)
    assert not old.exists()
    assert current.exists() and raw.exists()


def test_cleanup_keeps_snapshot_referenced_policies(tmp_path):
    from audience_simulator.repository import tables
    from sqlalchemy import update

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art")
    )
    for key in ["used", "unused"]:
        service.repo.save_policy(key, {"digest": "test", "response": {}})
    with service.repo.connection() as conn:
        conn.execute(
            update(tables["agent_evaluations"]).values(created_at=datetime.now(UTC) - timedelta(days=40))
        )
    campaign = service.repo.create("campaigns", {"name": "Test"})
    scenario = service.repo.create("scenarios", {"campaign_id": campaign["id"]})
    run = service.repo.create_run(scenario["id"], "test")
    service.store.write_json("runs/test.json", {"policy_snapshot": [{"key": "used"}]})
    service.repo.update_run(
        run["id"], completion_status="complete", status="succeeded", result_key="runs/test.json"
    )
    assert cleanup(service, apply=True)["expired_policies"] == 1
    assert service.repo.get_policy("used") is not None
    assert service.repo.get_policy("unused") is None
