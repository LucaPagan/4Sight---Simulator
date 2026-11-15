import threading
import time

import httpx
from audience_simulator.reaction_execution import run_reaction_plan
from audience_simulator.repository import Repository
from test_reactions import FakeReactor


def plan(n=6):
    return [{"key": str(i), "agent_id": str(i), "creative_id": "A", "input": {"index": i}} for i in range(n)]


def test_bounded_parallelism_persistence_order_and_cache(tmp_path, monkeypatch):
    repo = Repository(f"sqlite:///{tmp_path}/db")
    owner = threading.get_ident()
    save = repo.save_decision

    def coordinator_save(*args):
        assert threading.get_ident() == owner
        save(*args)

    monkeypatch.setattr(repo, "save_decision", coordinator_save)
    lock = threading.Lock()
    active = peak = 0

    def decide(client, payload, attempt=0):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.035 if payload["index"] % 2 == 0 else 0.005)
        with lock:
            active -= 1
        return {"decision": {"index": payload["index"]}, "tokens": 2}

    monkeypatch.setattr("audience_simulator.reaction_execution.decide", decide)
    result = run_reaction_plan(repo, FakeReactor(), plan(), "d", concurrency=2)
    assert peak == 2 and list(result["decisions"]) == [str(i) for i in range(6)]
    assert result["performance"]["calls"] == 6
    again = run_reaction_plan(repo, FakeReactor(), plan(), "d", concurrency=2)
    assert again["performance"]["calls"] == 0 and again["performance"]["cache_hits"] == 6


def test_blocking_error_drains_successes_and_stops_new_work(tmp_path, monkeypatch):
    repo = Repository(f"sqlite:///{tmp_path}/db")
    started = []

    def decide(client, payload, attempt=0):
        started.append(payload["index"])
        if payload["index"] == 0:
            time.sleep(0.01)
            raise httpx.ConnectError("offline")
        time.sleep(0.025)
        return {"decision": {}, "tokens": 1}

    monkeypatch.setattr("audience_simulator.reaction_execution.decide", decide)
    result = run_reaction_plan(repo, FakeReactor(), plan(), "d", concurrency=2)
    assert isinstance(result["error"], httpx.ConnectError)
    assert set(started) == {0, 1} and repo.get_decision("1")
    assert result["performance"]["errors"] == 1


def test_attempt_budget_and_cancellation_do_not_discard_completed_results(tmp_path, monkeypatch):
    repo = Repository(f"sqlite:///{tmp_path}/db")

    def invalid(client, payload, attempt=0):
        raise ValueError("invalid")

    monkeypatch.setattr("audience_simulator.reaction_execution.decide", invalid)
    result = run_reaction_plan(repo, FakeReactor(), plan(), "d", concurrency=2, max_evaluations=3)
    assert result["performance"]["calls"] == 3 and result["error"]
    assert result["performance"]["rejected"] == 3
    canceled = run_reaction_plan(repo, FakeReactor(), plan(), "d", canceled=lambda: True)
    assert canceled["canceled"] and canceled["performance"]["calls"] == 0


def test_cloud_is_sequential_even_when_parallelism_is_requested(tmp_path, monkeypatch):
    repo = Repository(f"sqlite:///{tmp_path}/db")
    client = FakeReactor()
    client.provider = "gemini"
    active = 0

    def decide(*args, **kwargs):
        nonlocal active
        active += 1
        assert active == 1
        time.sleep(0.005)
        active -= 1
        return {"decision": {}}

    monkeypatch.setattr("audience_simulator.reaction_execution.decide", decide)
    result = run_reaction_plan(repo, client, plan(), "d", concurrency=4)
    assert len(result["decisions"]) == 6
