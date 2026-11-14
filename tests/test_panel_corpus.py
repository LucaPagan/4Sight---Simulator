import json

import httpx
import pytest
from audience_simulator.agents import OllamaClient
from audience_simulator.calibration import FEATURES
from audience_simulator.panel_corpus import corpus_payloads, run_panel, score_with_calibration


class MemoryRepo:
    def __init__(self):
        self.policies = {}

    def get_policy(self, key):
        return self.policies.get(key)

    def save_policy(self, key, value):
        self.policies[key] = value


class MemoryStore:
    def __init__(self):
        self.files = {}

    def write_json(self, key, value):
        self.files[key] = json.loads(json.dumps(value))

    def read_json(self, key):
        if key not in self.files:
            raise FileNotFoundError(key)
        return self.files[key]


def inputs(campaign_id, headlines):
    return {
        "campaign_id": campaign_id,
        "domain": {
            "kind": "news_headline",
            "platform": "p",
            "country": "US",
            "language": "en",
            "objective": "click_through",
            "placement": "unknown",
        },
        "date_from": "2014-03-01",
        "date_to": "2014-03-02",
        "stimuli": [
            {"id": f"{campaign_id}-{i}", "headline": h, "primary_text": ""} for i, h in enumerate(headlines)
        ],
    }


class Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self, request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b", "digest": "d", "size": 1}]})
        self.calls += 1
        text = json.loads(request.content)["prompt"]
        interest = 4 if "Amazing" in text else 1
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {
                        "clarity": 2,
                        "interest": interest,
                        "credibility": 2,
                        "friction": 2,
                        "conditional_action": "consider_click" if interest > 2 else "defer",
                        "frictions": [],
                        "evidence": ["creative.headline"],
                        "unknowns": [],
                        "conditional_reaction": "Il titolo racconta qualcosa di concreto.",
                    }
                ),
                "done": True,
                "eval_count": 5,
            },
        )


def client():
    handler = Counter()
    return OllamaClient(transport=httpx.MockTransport(handler)), handler


def test_payload_has_no_outcomes_and_a_neutral_profile_for_b1():
    campaign = inputs("c1", ["Amazing news", "Plain news"])
    panel = corpus_payloads(campaign, system="B2", panel_size=30, digest="d", prompt_version="v")
    b1 = corpus_payloads(campaign, system="B1", panel_size=30, digest="d", prompt_version="v")
    assert len(panel) == 2 * 30 and len(b1) == 2
    assert b1[0]["input"]["profile"]["agent_id"] == "no-persona"
    flat = json.dumps(panel[0]["input"])
    assert "impressions" not in flat and "clicks" not in flat
    assert panel[0]["input"]["creative"]["headline"] == "Amazing news"
    assert panel[0]["input"]["campaign"]["price_eur"] == 0.0
    assert len({p["key"] for p in panel}) == 60


def test_run_panel_is_resumable_and_writes_features_only_for_complete_campaigns():
    store, repo = MemoryStore(), MemoryRepo()
    llm, handler = client()
    campaigns = [inputs("c1", ["Amazing news", "Plain news"]), inputs("c2", ["Amazing b", "Plain b"])]
    first = run_panel(store, repo, llm, campaigns, "B2", "dev", panel_size=30, max_new=70)
    assert first["status"] == "partial" and handler.calls == 70
    saved = store.read_json("validation/panel-features/B2-dev.json")
    assert set(saved) == {"c1"} or set(saved) == set()
    second = run_panel(store, repo, llm, campaigns, "B2", "dev", panel_size=30, max_new=500)
    assert second["status"] == "complete" and handler.calls == 120
    features = store.read_json("validation/panel-features/B2-dev.json")
    assert set(features) == {"c1", "c2"}
    assert set(features["c1"]["c1-0"]) == set(FEATURES)
    assert features["c1"]["c1-0"]["interest"] > features["c1"]["c1-1"]["interest"]
    third = run_panel(store, repo, llm, campaigns, "B2", "dev", panel_size=30, max_new=500)
    assert handler.calls == 120 and third["new_calls"] == 0


def test_scores_use_fitted_weights_and_need_no_outcomes():
    store = MemoryStore()
    features = {
        "c1": {"a": dict.fromkeys(FEATURES, 0.0) | {"interest": 0.5}, "b": dict.fromkeys(FEATURES, 0.0)},
    }
    store.write_json("validation/panel-features/B2-test.json", features)
    store.write_json(
        "validation/calibration-B2.json",
        {"weights": dict.fromkeys(FEATURES, 0.0) | {"interest": 2.0}, "beta": 0.0},
    )
    scores = score_with_calibration(store, "B2", "test")
    assert scores["c1"]["a"] > scores["c1"]["b"]
    assert sum(scores["c1"].values()) == pytest.approx(0)
    assert store.read_json("validation/scores/B2-test.json") == scores
