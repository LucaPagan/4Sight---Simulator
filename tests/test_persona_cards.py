import json
import re
from itertools import count
from pathlib import Path

import httpx
import pytest
from audience_simulator import cloud
from audience_simulator.agents import OllamaClient
from audience_simulator.cloud import CloudQuotaError, CloudRuntimeError, GeminiClient
from audience_simulator.cloudflare import CloudflareClient
from audience_simulator.config import Settings
from audience_simulator.persona_cards import (
    BATCH_SIZE,
    PersonaWriter,
    batch_schema,
    card_omissions,
    describe_profile,
    skeleton_view,
    validate_card,
)
from audience_simulator.persona_model import generate_targeted_population
from audience_simulator.repository import Repository
from audience_simulator.schemas import CampaignBrief, Creative, PersonaCard, TargetingSpec
from audience_simulator.service import SimulationService

FIRST_NAMES = [
    "Giulia", "Marco", "Chiara", "Luca", "Sara", "Andrea", "Elena", "Matteo", "Francesca", "Davide",
    "Valentina", "Simone", "Martina", "Paolo", "Alice", "Giorgio", "Federica", "Stefano", "Silvia", "Roberto",
    "Anna", "Fabio", "Laura", "Nicola", "Irene", "Daniele", "Giada", "Michele", "Elisa", "Riccardo",
    "Paola", "Claudio", "Monica", "Enrico", "Serena", "Massimo", "Barbara", "Alessio", "Cristina", "Tommaso",
]  # fmt: skip
JOBS = [
    "infermiere", "grafica freelance", "magazziniere", "insegnante di scuola primaria", "barista", "geometra",
    "commessa in un negozio", "programmatore", "contabile", "fisioterapista", "cuoco", "autista di furgoni",
    "receptionist", "elettricista", "parrucchiera", "agente immobiliare", "bibliotecaria", "fotografo",
]  # fmt: skip
ADVERBS = ["Ogni", "Dopo", "Da", "Con", "Di", "Quando", "Senza"]
VERBS = ["mattina", "turno", "tanto", "calma", "solito", "puo"]
NOUNS = ["prepara", "controlla", "sistema", "legge", "sceglie"]


def opening(n):
    return f"{ADVERBS[n % 7]} {VERBS[(n // 7) % 6]} {NOUNS[(n // 42) % 5]}"


def facts_of(block):
    text = " ".join(block)
    usage = next((line for line in block if "Usa " in line and "minuti" in line), "")
    return {
        "age": int(re.search(r"Ha (\d+) anni", text).group(1)),
        "gender": "women" if "una donna" in text else "men",
        "household": "alone"
        if "Vive da sol" in text
        else "couple"
        if "Vive in coppia" in text
        else "family"
        if "Vive con la famiglia" in text
        else "shared",
        "children": "no" if "Non ha figli" in text else "yes",
        "pet": "dog"
        if "Ha un cane" in text
        else "cat"
        if "Ha un gatto" in text
        else "other"
        if "né un cane né un gatto" in text
        else "none",
        "os": "ios" if "iPhone" in text else "android",
        "ig": "Instagram" in usage,
        "fb": "Facebook" in usage,
        "job": "student" if "Studia" in text else "retired" if "in pensione" in text else "employed",
    }


class FakeWriter:
    """Stands in for the model: reads the facts in the prompt and writes a coherent, distinct card for each person."""

    provider, model = "fake", "fake-model"

    def __init__(self, mutate=None):
        self.calls, self.mutate, self.serial = [], mutate, count()

    def generate(self, system, user, schema, **options):
        self.calls.append({"system": system, "user": user, "schema": schema, "options": options})
        blocks = re.findall(r"P(\d+)\n((?:- .*\n?)+)", user)
        cards = []
        for ref, block in blocks:
            n = next(self.serial)
            f = facts_of(block.splitlines())
            pet = {
                "dog": "Il suo cane lo porta fuori ogni sera e compra crocchette al supermercato.",
                "cat": "Il suo gatto dorme sul divano e compra scatolette al supermercato.",
                "other": "Il suo criceto vive in una gabbia in salotto e compra mangime al supermercato.",
                "none": "Non ha animali domestici e compra in questa categoria solo regali per amici.",
            }[f["pet"]]
            kids = " Ha dei figli." if f["children"] == "yes" else ""
            platforms = " e ".join(p for p, on in (("Instagram", f["ig"]), ("Facebook", f["fb"])) if on)
            job = {"student": "studente universitario", "retired": "pensionato ex impiegato"}.get(
                f["job"], JOBS[n % len(JOBS)] + f" ({n})"
            )
            card = {
                "ref": f"P{ref}",
                "name": f"{FIRST_NAMES[n % len(FIRST_NAMES)]}{n // len(FIRST_NAMES) or ''} Rossi",
                "city": "Bologna",
                "job": job,
                "bio": f"{opening(n)} "
                + " ".join(f"passione{n * 6 + k}" for k in range(6))
                + f" tra una cosa e l'altra.{kids}",
                "daily_routine": f"Alle sette si sveglia, lavora fino a sera e il numero {n} della giornata è sempre il solito.",
                "category_relationship": pet,
                "social_habits": f"Scorre {platforms} in pausa pranzo e la sera sul divano, senza commentare quasi mai.",
                "ad_reaction_style": "Salta quasi tutto, si ferma solo se vede qualcosa che lo riguarda davvero.",
                "pain_points": ["poco tempo libero"],
                "quirks": ["compra sempre all'ultimo minuto"],
                "budget_eur_month": 30,
                "echo_age": f["age"],
                "echo_gender": f["gender"],
                "echo_household": f["household"],
                "echo_has_children": f["children"],
                "echo_pet_species": f["pet"],
                "echo_device_os": f["os"],
            }
            if self.mutate:
                card = self.mutate(card, n, len(self.calls))
            cards.append(card)
        return {"raw": json.dumps({"cards": cards}), "seconds": 0.01, "tokens": 100, "prompt_tokens": 200}

    def status(self):
        return {"ready": True, "digest": "fake-digest", "error": None}


@pytest.fixture
def repo(tmp_path):
    return Repository(f"sqlite:///{tmp_path}/db.sqlite")


def targeted(size=30, **targeting):
    brief = CampaignBrief(
        name="t",
        brand="B",
        product_description="Cibo per cani",
        vertical="pet_ecommerce",
        creatives=[Creative(id="a", headline="x", primary_text="y")],
        population_size=size,
        targeting=TargetingSpec(**targeting),
    )
    return generate_targeted_population(brief)[0]


def writer(repo, client):
    return PersonaWriter(repo, client, "fake-digest", "pet_ecommerce", "IT", "Marca")


def test_facts_are_plain_italian_with_tendencies_not_raw_numbers():
    profile = targeted(30)[0]
    facts = describe_profile(profile)
    text = " ".join(facts)
    assert f"{profile['age']} anni" in text and "Tendenze" in text
    assert not re.search(r"\d\.\d", text) and "category_affinity" not in text
    assert any(w in text for w in ("cane", "gatto", "animali"))


def test_happy_path_writes_distinct_cards_in_batches_and_reuses_the_cache(repo):
    profiles = targeted(30)
    fake = FakeWriter()
    cards, report = writer(repo, fake).write(profiles)
    assert set(cards) == {p["agent_id"] for p in profiles}
    assert (
        report["written_by_llm"] == 30
        and report["template_fallback"] == 0
        and report["rejected_reasons"] == {}
    )
    assert report["calls"] == len(fake.calls) == -(-30 // BATCH_SIZE)
    assert report["diversity"]["distinct_first_names"] == 30 and report["evidence"] == "hypothesis"
    assert all(c["source"] == "llm" and c["facts"] for c in cards.values())
    # Later batches are told what is already used.
    assert "Già usati" not in fake.calls[0]["user"] and "Giulia" in fake.calls[1]["user"]
    again = FakeWriter()
    cards2, report2 = writer(repo, again).write(profiles)
    assert cards2 == cards and again.calls == [] and report2["from_cache"] == 30 and report2["calls"] == 0


def test_cache_key_changes_with_skeleton_model_and_prompt(repo):
    profile = targeted(30)[0]
    w = writer(repo, FakeWriter())
    other_model = FakeWriter()
    other_model.model = "other"
    assert w.key(profile) == w.key(dict(profile, agent_id="x", population_weight=9))
    assert w.key(profile) != w.key(
        {**profile, "pet_species": "none" if profile["pet_species"] != "none" else "dog"}
    )
    assert w.key(profile) != writer(repo, other_model).key(profile)
    assert "agent_id" not in skeleton_view(profile)


def test_a_card_that_breaks_a_fact_is_rejected_then_regenerated(repo):
    def mutate(card, n, call):
        if call == 1 and n == 2:  # the third person of the first call gets a price and a wrong pet
            card["category_relationship"] += " Spende 40 euro al mese."
        return card

    cards, report = writer(repo, FakeWriter(mutate)).write(targeted(30))
    assert report["rejected_reasons"] == {"prezzo_nel_testo": 1}
    assert report["written_by_llm"] == 30 and report["template_fallback"] == 0
    assert all("euro" not in c["category_relationship"] for c in cards.values())


def test_persistent_failure_falls_back_to_a_labelled_template(repo):
    profiles = targeted(30)
    victim = profiles[3]["agent_id"]

    def mutate(card, n, call):
        if n % 5 == 0:
            card["bio"] += " Spende 40 euro al mese."
        return card

    cards, report = writer(repo, FakeWriter(mutate)).write(profiles)
    assert report["written_by_llm"] + report["template_fallback"] == 30
    assert report["rejected_reasons"]["prezzo_nel_testo"] >= 1
    templates = [c for c in cards.values() if c["source"] == "template"]
    assert len(templates) == report["template_fallback"]
    assert victim in cards and all(t["name"].startswith("Persona ") and t["facts"] for t in templates)


def test_duplicate_names_and_openings_are_regenerated(repo):
    profiles = targeted(30)

    def mutate(card, n, call):
        if n < 2:
            card["name"] = "Giulia Bianchi"
            card["bio"] = (
                "Ogni mattina comincia la giornata con calma e un caffè lungo, poi va al lavoro."
                + (" Ha dei figli." if card["echo_has_children"] == "yes" else "")
            )
        return card

    cards, report = writer(repo, FakeWriter(mutate)).write(profiles[:8])
    assert (
        report["rejected_reasons"].get("nome_duplicato", 0)
        + report["rejected_reasons"].get("apertura_duplicata", 0)
        >= 1
    )
    assert (
        len({c["name"].split()[0] for c in cards.values() if c["source"] == "llm"})
        == report["written_by_llm"]
    )


def test_quota_error_propagates_and_progress_is_kept(repo):
    profiles = targeted(30)

    class Quota(FakeWriter):
        def generate(self, *args, **kwargs):
            if len(self.calls) == 2:
                raise CloudQuotaError()
            return super().generate(*args, **kwargs)

    with pytest.raises(CloudQuotaError):
        writer(repo, Quota()).write(profiles)
    resumed = FakeWriter()
    cards, report = writer(repo, resumed).write(profiles)
    assert report["from_cache"] == 2 * BATCH_SIZE and report["written_by_llm"] == 30 - 2 * BATCH_SIZE
    assert len(cards) == 30


def valid_card_for(profile):
    fake = FakeWriter()
    out = fake.generate("", "P1\n" + "\n".join(f"- {f}" for f in describe_profile(profile)), None)
    return PersonaCard.model_validate(json.loads(out["raw"])["cards"][0])


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"echo_gender": "men"}, "fatto_cambiato:echo_gender"),
        ({"city": "Roma, dove prega in chiesa ogni domenica"}, "attributo_sensibile"),
        ({"category_relationship": "Compra tutto su Amazon da anni, senza guardare altro."}, "marchio_reale"),
        (
            {"bio": "Ha 52 anni e comincia sempre la giornata con calma e con un caffè lungo."},
            "eta_incoerente",
        ),
        ({"budget_eur_month": 5000}, "budget_incoerente"),
    ],
)
def test_validator_catches_each_kind_of_contradiction(change, problem):
    profile = next(
        p for p in targeted(60) if p["uses_instagram"] != p["uses_facebook"] and p["income_band"] == "low"
    )
    card = valid_card_for(profile)
    assert validate_card(card, profile) == []
    broken = card.model_copy(update=change)
    if problem == "eta_incoerente":
        broken = broken.model_copy(update={"bio": broken.bio.replace("52", str(profile["age"] + 7))})
    found = validate_card(broken, profile)
    assert problem.split(":")[0] in " ".join(found) or problem in found


def test_pet_household_and_children_rules_respect_negation():
    profiles = targeted(120)
    no_pet = next(p for p in profiles if p["pet_species"] == "none" and p["has_children"] == "no")
    card = valid_card_for(no_pet)
    assert validate_card(card, no_pet) == []  # "non ha animali domestici" is a negation, not a pet
    with_dog = card.model_copy(
        update={"category_relationship": "Porta il suo cane al parco ogni mattina presto."}
    )
    assert "animale_incoerente" in validate_card(with_dog, no_pet)
    with_kids = card.model_copy(
        update={"bio": "Vive con calma, i suoi figli vengono a trovarlo ogni domenica sera."}
    )
    assert "figli_incoerenti" in validate_card(with_kids, no_pet)
    owner = next(p for p in profiles if p["pet_species"] == "dog" and p["household"] == "alone")
    good = valid_card_for(owner)
    assert validate_card(good, owner) == []
    roommates = good.model_copy(
        update={"bio": "Vive con un coinquilino e il suo cane in un trilocale molto luminoso."}
    )
    assert "nucleo_incoerente" in validate_card(roommates, owner)
    no_dog = good.model_copy(update={"category_relationship": "Compra spesso cose per la casa e per sé."})
    # Leaving a fact out is not a contradiction: it blocks only where the category is about that fact.
    assert validate_card(no_dog, owner) == [] and card_omissions(no_dog, owner) == ["animale_mancante"]
    assert "animale_mancante" in validate_card(no_dog, owner, vertical="pet_ecommerce")
    late_negation = card.model_copy(
        update={"social_habits": "Scorre i social la sera sul divano, i gatti non li ha mai voluti in casa."}
    )
    assert "animale_incoerente" not in validate_card(late_negation, no_pet)
    details = {}
    validate_card(with_dog, no_pet, details=details)
    assert "cane" in details["animale_incoerente"]


def test_echo_facts_come_from_the_skeleton_not_from_the_model(repo):
    profiles = targeted(30)[:8]

    def mutate(card, n, call):
        card["echo_age"], card["echo_has_children"] = 99, "yes"
        return card

    fake = FakeWriter(mutate)
    cards, report = writer(repo, fake).write(profiles)
    assert report["written_by_llm"] == 8 and report["rejected_reasons"] == {}
    assert all(cards[p["agent_id"]]["echo_age"] == p["age"] for p in profiles)
    asked = fake.calls[0]["schema"]["properties"]["cards"]["items"]
    assert not any(k.startswith("echo_") for k in asked["properties"]) and "echo_age" not in asked["required"]


def test_batch_schema_is_flat_and_forces_one_card_per_person():
    schema = batch_schema(3)
    items = schema["properties"]["cards"]["items"]
    assert schema["properties"]["cards"]["minItems"] == 3 == schema["properties"]["cards"]["maxItems"]
    assert items["properties"]["ref"]["enum"] == ["P1", "P2", "P3"]
    assert "$defs" not in json.dumps(schema) and items["additionalProperties"] is False


def test_providers_expose_a_generic_structured_call():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    seen = {}

    def ollama(request):
        seen["ollama"] = json.loads(request.content)
        return httpx.Response(200, json={"response": '{"a":"x"}', "done": True, "eval_count": 5})

    out = OllamaClient(transport=httpx.MockTransport(ollama)).generate(
        "sys", "usr", schema, temperature=0.8, seed=3
    )
    body = seen["ollama"]
    assert out["raw"] == '{"a":"x"}' and body["format"] == schema and body["options"]["temperature"] == 0.8
    assert body["options"]["seed"] == 3 and body["prompt"] == "usr"

    def cloudflare(request):
        seen["cloudflare"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": '{"a":"y"}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    cf = CloudflareClient("t", "a" * 32, free_tier_confirmed=True, transport=httpx.MockTransport(cloudflare))
    out = cf.generate("sys", "usr", schema, temperature=0.7, seed=9)
    body = seen["cloudflare"]
    assert (
        out["raw"] == '{"a":"y"}' and out["tokens"] == 4 and body["seed"] == 9 and body["temperature"] == 0.7
    )
    assert body["response_format"]["json_schema"]["schema"] == schema and body["store"] is False

    def gemini(request):
        seen["gemini"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "steps": [{"type": "model_output", "content": [{"type": "text", "text": '{"a":"z"}'}]}],
                "usage": {},
            },
        )

    g = GeminiClient(
        "k" * 30, free_tier_confirmed=True, transport=httpx.MockTransport(gemini), requests_per_minute=60
    )
    out = g.generate("sys", "usr", schema, temperature=0.6)
    body = seen["gemini"]
    assert (
        out["raw"] == '{"a":"z"}'
        and body["system_instruction"] == "sys"
        and body["generation_config"]["temperature"] == 0.6
    )
    assert body["store"] is False and body["response_format"]["schema"] == schema


@pytest.fixture
def service(tmp_path):
    return SimulationService(
        Settings(
            database_url=f"sqlite:///{tmp_path}/db.sqlite",
            artifact_dir=tmp_path / "artifacts",
            data_dir=Path("data"),
            queue_mode="manual",
            monte_carlo_draws=30,
        )
    )


PAYLOAD = {
    "name": "Cani",
    "brand": "Marca",
    "vertical": "pet_ecommerce",
    "product_description": "Cibo per cani",
    "creatives": [{"id": "A", "headline": "Cibo", "primary_text": "Per il tuo cane"}],
    "population_size": 30,
}


def test_service_stores_cards_on_the_population_and_refuses_untargeted_panels(service):
    scenario = service.create_scenario({**PAYLOAD, "targeting": {"audience_intent": "ha un cane"}})
    result = service.write_personas(scenario["id"], client=FakeWriter())
    population = service.repo.get("populations", scenario["population_id"])
    assert set(population["cards"]) == {p["agent_id"] for p in population["profiles"]}
    assert population["persona_report"]["written_by_llm"] == 30 == result["report"]["written_by_llm"]
    legacy = service.create_scenario(PAYLOAD)
    with pytest.raises(ValueError, match="pannello mirato"):
        service.write_personas(legacy["id"], client=FakeWriter())


def test_local_models_use_small_batches_and_a_timeout_never_fails_the_run(repo):
    profiles = targeted(30)

    class Slow(FakeWriter):
        provider, card_batch_size = "ollama", 2

        def generate(self, *args, **kwargs):
            if len(self.calls) == 0:
                self.calls.append({})
                raise httpx.ReadTimeout("timed out")
            return super().generate(*args, **kwargs)

    slow = Slow()
    seen = []
    cards, report = writer(repo, slow).write(
        profiles[:6], progress=lambda done, total: seen.append((done, total))
    )
    assert report["written_by_llm"] == 6 and report["template_fallback"] == 0
    assert report["rejected_reasons"] == {"risposta_non_valida:ReadTimeout": 2}
    assert all(len(re.findall(r"^P\d+$", c.get("user", ""), re.M)) <= 2 for c in slow.calls)
    assert seen[-1] == (6, 6) and len(seen) >= 3
    assert OllamaClient.card_batch_size == 2 and OllamaClient.generate_timeout >= 600


def test_runtime_disconnection_still_stops_the_writer(repo):
    class Down(FakeWriter):
        def generate(self, *args, **kwargs):
            raise httpx.ConnectError("refused")

    with pytest.raises(httpx.ConnectError):
        writer(repo, Down()).write(targeted(30)[:4])


def test_a_provider_failure_stops_the_writer_instead_of_writing_templates(repo):
    class Down(FakeWriter):
        def generate(self, *args, **kwargs):
            raise CloudRuntimeError("Gemini ha restituito HTTP 400.")

    with pytest.raises(CloudRuntimeError):
        writer(repo, Down()).write(targeted(30)[:4])


def test_cloud_calls_retry_a_passing_overload_and_report_the_wait(monkeypatch):
    monkeypatch.setattr(cloud, "RETRY_DELAYS", (0, 0))
    answers = iter([503, 503, 200])

    def flaky(request):
        status = next(answers)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "high demand"}})
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "steps": [{"type": "model_output", "content": [{"type": "text", "text": '{"a": "b"}'}]}],
            },
        )

    client = GeminiClient(
        "k" * 30, free_tier_confirmed=True, transport=httpx.MockTransport(flaky), requests_per_minute=6000
    )
    assert client.generate("s", "u", {"type": "object"})["raw"] == '{"a": "b"}'

    def exhausted(request):
        return httpx.Response(
            429, json={"error": {"message": "limit: 500 requests per day. Please retry in 38m5s or upgrade"}}
        )

    client = GeminiClient(
        "k" * 30, free_tier_confirmed=True, transport=httpx.MockTransport(exhausted), requests_per_minute=6000
    )
    with pytest.raises(CloudQuotaError) as caught:
        client.generate("s", "u", {"type": "object"})
    assert caught.value.retry_after_seconds == 38 * 60 + 5 and "38 minuti" in str(caught.value)
    assert cloud.retry_seconds("nessuna attesa") is None
