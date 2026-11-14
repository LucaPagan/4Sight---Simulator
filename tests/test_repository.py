import pytest
from audience_simulator.repository import ArtifactStore, Repository


def test_resources_versioning_idempotency_and_transaction(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path}/test.db")
    dataset = repo.create("datasets", {"name": "kit", "dataset_hash": "abc", "path": "data"})
    assert repo.get("datasets", dataset["id"])["dataset_hash"] == "abc"
    campaign = repo.create("campaigns", {"name": "Test", "dataset_id": dataset["id"]})
    scenario = repo.create("scenarios", {"campaign_id": campaign["id"], "name": "s"})
    first = repo.create_run(scenario["id"], "same-key")
    assert repo.create_run(scenario["id"], "same-key")["id"] == first["id"]
    repo.save_policy("policy-hash", {"input": {"x": 1}, "response": {"interest": 2}, "digest": "d"})
    assert repo.get_policy("policy-hash")["response"]["interest"] == 2
    repo.update_run(first["id"], status="waiting_for_runtime", progress=5)
    assert repo.get("simulation_runs", first["id"])["status"] == "waiting_for_runtime"


def test_artifact_paths_and_atomic_roundtrip(tmp_path):
    store = ArtifactStore(tmp_path)
    store.write_json("runs/abc.json", {"x": [1, 2]})
    assert store.read_json("runs/abc.json") == {"x": [1, 2]}
    with pytest.raises(ValueError):
        store.write_json("../outside.json", {})
    with pytest.raises(ValueError):
        store.write_json("bad.json", {"x": float("nan")})
