import pandas as pd
from audience_simulator.ablation import compare_ablation


def test_ablation_promotes_only_measured_improvements():
    rows = pd.DataFrame({"click": [10, 30], "impression": [1000, 1000]})
    result = compare_ablation(
        rows,
        {"baseline": [0.03, 0.01], "llm_without_persona": [0.08, 0.08], "individual_panel": [0.01, 0.03]},
    )
    assert result["individual_panel"]["promotion_gate"]
    assert not result["llm_without_persona"]["promotion_gate"]
    assert not result["baseline"]["promotion_gate"]


def test_ablation_capacity_resume_reuses_cached_profiles(tmp_path, monkeypatch):
    from audience_simulator.ablation import run_ablation
    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from test_agents_behavior import policy

    service = SimulationService(
        Settings(database_url=f"sqlite:///{tmp_path}/db", artifact_dir=tmp_path / "art", max_evaluations=1)
    )
    assets = pd.DataFrame(
        [
            dict(
                asset_id="NDL-S3",
                headline="Routine",
                testo_principale="Scopri il kit",
                descrizione_visual="",
                vertical="beauty_skincare",
                leva="scarcity",
                formato="immagine",
            )
        ]
    )
    monkeypatch.setattr(service, "ensure_kit", lambda: {"assets": assets})

    class LocalClient:
        calls = 0

        def status(self):
            return {"ready": True, "digest": "fixed"}

        def evaluate(self, payload):
            assert not {"click", "impression", "ctr", "cpm", "spesa"} & set(payload["campaign"])
            self.calls += 1
            return {"evaluation": policy()}

    client = LocalClient()
    assert run_ablation(service, client)["status"] == "partial"
    assert client.calls == 1
    assert run_ablation(service, client)["status"] == "partial"
    assert client.calls == 2
    assert len(service.repo.list("agent_evaluations")) == 2
