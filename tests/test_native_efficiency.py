import json

import pytest
from audience_simulator.persona_cards import PersonaWriter, user_prompt
from audience_simulator.repository import Repository
from test_persona_cards import FakeWriter, targeted, writer


def test_prompt_makes_budget_and_occupation_constraints_explicit():
    profile = {**targeted()[0], "income_band": "low", "occupation": "student"}
    prompt = user_prompt([profile], "pet_ecommerce", {"names": [], "jobs": [], "openings": []})
    assert "250" in prompt and "budget_eur_month" in prompt
    assert "job" in prompt and "studente" in prompt


def test_budget_only_failure_is_repaired_without_rewriting_valid_fields(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path}/cards.db")
    profile = {**targeted()[0], "income_band": "low"}

    class Repair(FakeWriter):
        def generate(self, system, user, schema, **options):
            if "cards" not in schema["properties"]:
                self.calls.append({"schema": schema, "user": user})
                assert set(schema["properties"]) == {"budget_eur_month"}
                assert schema["properties"]["budget_eur_month"]["maximum"] == 250
                return {"raw": json.dumps({"budget_eur_month": 40}), "tokens": 5}
            return super().generate(system, user, schema, **options)

    fake = Repair(lambda card, *_: {**card, "budget_eur_month": 251})
    w = writer(repo, fake)
    cards, report = w.write([profile])
    card = cards[profile["agent_id"]]
    assert card["source"] == "llm" and card["budget_eur_month"] == 40
    assert len(fake.calls) == 2 and report["corrections"] == 1
    assert report["attempts"] == 2 and report["rejected"] == 1


def test_failed_generations_are_counted_and_progress_is_reported(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path}/cards.db")

    class Broken(FakeWriter):
        def generate(self, *args, **kwargs):
            return {"raw": "{", "tokens": 11, "prompt_tokens": 20, "pacing_seconds": 2}

    w = writer(repo, Broken())
    progress = []
    _, report = w.write(targeted()[:2], progress=lambda *p: progress.append(p))
    assert report["calls"] == 3 and report["attempts"] == 6
    assert report["tokens"] == 33 and report["pacing_seconds"] == 6
    assert report["rejected"] == 6 and report["errors"] == 3
    assert progress[-1] == (2, 2) and len(progress) >= 4


def test_card_cache_includes_brand_and_revalidates_corrupted_entries(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path}/cards.db")
    profile = targeted()[0]
    fake = FakeWriter()
    w = writer(repo, fake)
    cards, _ = w.write([profile])
    assert w.key(profile) != PersonaWriter(repo, fake, "fake-digest", "pet_ecommerce", brand="Other").key(
        profile
    )
    stored = repo.get_card(w.key(profile))
    stored["card"]["budget_eur_month"] = 5000
    repo.save_card(w.key(profile), stored)
    fresh = FakeWriter()
    _, report = writer(repo, fresh).write([profile])
    assert fresh.calls and report["from_cache"] == 0


def test_template_cache_is_reused_and_retry_state_survives_restart(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path}/cards.db")
    profile = targeted()[0]
    state = {}

    class Broken(FakeWriter):
        def generate(self, *args, **kwargs):
            return {"raw": "{"}

    w = writer(repo, Broken())
    cards, report = w.write([profile], state=state)
    assert report["attempts"] == 3
    again = FakeWriter()
    cached, report = writer(repo, again).write([profile], state=state)
    assert cached == cards and not again.calls and report["from_cache"] == 1


def test_occupation_patch_is_revalidated_and_uses_only_three_attempts(tmp_path):
    repo = Repository(f"sqlite:///{tmp_path}/cards.db")
    profile = {**targeted()[0], "occupation": "retired"}

    class Repair(FakeWriter):
        def generate(self, system, user, schema, **options):
            if "cards" not in schema["properties"]:
                assert set(schema["properties"]) == {"job", "bio"}
                self.calls.append({"schema": schema})
                return {
                    "raw": json.dumps(
                        {"job": "pensionato", "bio": "Ha un cane e compra su Amazon ogni giorno con calma."}
                    )
                }
            return super().generate(system, user, schema, **options)

    fake = Repair(
        lambda card, *_: {
            **card,
            "job": "insegnante",
            "bio": "Ogni mattina prepara le lezioni per i ragazzi della scuola.",
        }
    )
    _, report = writer(repo, fake).write([profile])
    assert report["corrections"] == 1 and report["attempts"] == 3
    assert report["rejected_reasons"]["marchio_reale"] == 1
    assert report["template_fallback"] == 1


def test_materialized_cards_do_not_bypass_runtime_compatibility(tmp_path):
    from pathlib import Path

    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from test_native_engine import PAYLOAD, FakeAgent

    svc = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db",
            artifact_dir=tmp_path / "art",
            data_dir=Path("data"),
            queue_mode="manual",
            monte_carlo_draws=20,
        )
    )
    scenario = svc.create_scenario(PAYLOAD)
    old = FakeAgent()
    svc.write_personas(scenario["id"], client=old)
    changed = FakeAgent()
    changed.model = "another-model"
    run = svc.repo.create_run(
        scenario["id"], "new-model", {"provider": "fake", "mode": "agent_native", "slots": ["first"]}
    )
    svc.execute_run(run["id"], client=changed)
    assert changed.writer.calls
    final = svc.repo.get("simulation_runs", run["id"])
    assert final["completion_status"] == "complete"
    assert final["performance"]["cards"]["calls"] > 0
    assert final["performance"]["reactions"]["calls"] == 60


def test_cancel_during_personas_stops_after_current_batch_and_preserves_progress(tmp_path):
    from pathlib import Path

    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from test_native_engine import PAYLOAD, FakeAgent

    svc = SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db",
            artifact_dir=tmp_path / "art",
            data_dir=Path("data"),
            queue_mode="manual",
            monte_carlo_draws=20,
        )
    )
    scenario = svc.create_scenario(PAYLOAD)
    run = svc.repo.create_run(
        scenario["id"], "cancel-cards", {"provider": "fake", "mode": "agent_native", "slots": ["first"]}
    )

    class Cancel(FakeAgent):
        def generate(self, *args, **kwargs):
            result = super().generate(*args, **kwargs)
            svc.repo.update_run(run["id"], status="canceled", phase="canceled")
            return result

    client = Cancel()
    svc.execute_run(run["id"], client=client)
    final = svc.repo.get("simulation_runs", run["id"])
    assert final["status"] == "canceled" and final["phase"] == "canceled"
    assert len(client.writer.calls) == 1 and client.reactions == 0
    assert final["performance"]["cards"]["calls"] == 1
    assert svc.repo.list("persona_cards")


def test_performance_contract_is_optional_and_preserves_typed_counters():
    from audience_simulator.contracts import SimulationRun

    base = dict(
        id="r",
        scenario_id="s",
        status="running",
        phase="personas",
        completion_status="partial",
        progress=3,
        completed_policies=0,
        required_policies=720,
    )
    assert SimulationRun(**base).performance is None
    record = SimulationRun(**base, performance={"cards": {"attempts": 4, "rejected": 2}})
    assert record.performance.cards.attempts == 4
    with pytest.raises(ValueError):
        SimulationRun(**base, performance={"cards": {"calls": -1}})


def test_full_120_person_native_run_resumes_only_missing_reactions(tmp_path):
    from pathlib import Path

    from audience_simulator.config import Settings
    from audience_simulator.service import SimulationService
    from test_native_engine import PAYLOAD, FakeAgent

    cfg = Settings(
        database_url=f"sqlite:///{tmp_path}/db",
        artifact_dir=tmp_path / "art",
        data_dir=Path("data"),
        queue_mode="manual",
        monte_carlo_draws=20,
        max_evaluations=5,
        ollama_reaction_concurrency=2,
    )
    svc = SimulationService(cfg)
    scenario = svc.create_scenario({**PAYLOAD, "population_size": 120})
    run = svc.repo.create_run(
        scenario["id"],
        "120-resume",
        {"provider": "ollama", "mode": "agent_native", "slots": ["first", "repeat", "saturated"]},
    )
    first = FakeAgent()
    first.provider = "ollama"
    svc.execute_run(run["id"], first)
    paused = svc.repo.get("simulation_runs", run["id"])
    assert paused["status"] == "waiting_for_capacity" and paused["completed_policies"] == 5
    cfg.max_evaluations = 1000
    second = FakeAgent()
    second.provider = "ollama"
    svc.execute_run(run["id"], second)
    final = svc.repo.get("simulation_runs", run["id"])
    assert final["completion_status"] == "complete" and final["completed_policies"] == 720
    assert second.reactions == 715 and not second.writer.calls
    assert final["performance"]["reactions"]["calls"] == 720
    assert final["performance"]["reactions"]["cache_hits"] == 5
    assert len(svc.result(run["id"])["profiles"]) == 120
