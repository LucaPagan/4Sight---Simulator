import json
import os
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
tables: dict[str, Table] = {}


def resource_table(name, *columns, constraints=()):
    table = Table(
        name,
        metadata,
        Column("id", String(120), primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)),
        Column("payload", JSON, nullable=False),
        *columns,
        *constraints,
    )
    tables[name] = table
    return table


resource_table("datasets")
resource_table("advertisers", Column("dataset_id", String, ForeignKey("datasets.id"), index=True))
resource_table(
    "campaigns", Column("dataset_id", String, ForeignKey("datasets.id"), nullable=True, index=True)
)
resource_table("campaign_briefs", Column("campaign_id", String, ForeignKey("campaigns.id"), index=True))
resource_table("adsets", Column("campaign_id", String, ForeignKey("campaigns.id"), index=True))
resource_table("assets", Column("dataset_id", String, ForeignKey("datasets.id"), nullable=True, index=True))
resource_table(
    "ads",
    Column("adset_id", String, ForeignKey("adsets.id"), index=True),
    Column("asset_id", String, ForeignKey("assets.id"), index=True),
)
for name in ["daily_observations", "forecast_rows", "budgets", "calendar", "market_benchmarks"]:
    resource_table(name, Column("dataset_id", String, ForeignKey("datasets.id"), index=True))
for name in ["assumptions", "behavioral_evidence", "model_versions", "validation_runs", "llm_benchmark_runs"]:
    resource_table(name)
resource_table(
    "scenarios", Column("campaign_id", String, ForeignKey("campaigns.id"), nullable=True, index=True)
)
resource_table("populations", Column("scenario_id", String, ForeignKey("scenarios.id"), index=True))
resource_table("consumer_profiles", Column("population_id", String, ForeignKey("populations.id"), index=True))
resource_table(
    "simulation_runs",
    Column("scenario_id", String, ForeignKey("scenarios.id"), index=True),
    Column("idempotency_key", String, nullable=False),
    constraints=(UniqueConstraint("scenario_id", "idempotency_key"),),
)
resource_table("agent_evaluations", Column("model_digest", String, index=True))
resource_table("persona_cards", Column("model_digest", String, index=True))
resource_table("agent_decisions", Column("model_digest", String, index=True))
for name in [
    "consumer_states",
    "exposure_events",
    "predictions",
    "age_predictions",
    "prediction_explanations",
    "job_events",
]:
    resource_table(name, Column("run_id", String, ForeignKey("simulation_runs.id"), index=True))


class Repository:
    def __init__(self, url):
        self.local = threading.local()
        if url.startswith("sqlite:///"):
            path = url.removeprefix("sqlite:///")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {},
            pool_pre_ping=True,
        )
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def pragmas(connection, record):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA journal_mode=WAL")

        metadata.create_all(self.engine)

    @contextmanager
    def connection(self):
        current = getattr(self.local, "connection", None)
        if current is not None:
            yield current
        else:
            with self.engine.begin() as conn:
                yield conn

    @contextmanager
    def transaction(self):
        with self.engine.begin() as conn:
            self.local.connection = conn
            try:
                yield
            finally:
                self.local.connection = None

    def create(self, kind, payload, resource_id=None):
        table = tables[kind]
        resource_id = resource_id or str(uuid4())
        columns = {
            c.name: payload[c.name]
            for c in table.columns
            if c.name in payload and c.name not in ["id", "payload", "created_at"]
        }
        with self.connection() as conn:
            conn.execute(insert(table).values(id=resource_id, payload=payload, **columns))
        return {**payload, "id": resource_id}

    def bulk_create(self, kind, rows):
        if not rows:
            return
        table = tables[kind]
        values = []
        for item in rows:
            payload = item["payload"]
            value = {"id": item.get("id", str(uuid4())), "payload": payload}
            value.update(
                {
                    c.name: payload[c.name]
                    for c in table.columns
                    if c.name in payload and c.name not in ["id", "payload", "created_at"]
                }
            )
            values.append(value)
        with self.connection() as conn:
            conn.execute(insert(table), values)

    def get(self, kind, resource_id):
        table = tables[kind]
        with self.connection() as conn:
            row = conn.execute(select(table).where(table.c.id == resource_id)).mappings().first()
        if row is None:
            raise KeyError(resource_id)
        return {**row["payload"], "id": row["id"], "created_at": row["created_at"].isoformat()}

    def list(self, kind, limit=100):
        table = tables[kind]
        with self.connection() as conn:
            rows = (
                conn.execute(select(table).order_by(table.c.created_at.desc()).limit(limit)).mappings().all()
            )
        return [{**r["payload"], "id": r["id"], "created_at": r["created_at"].isoformat()} for r in rows]

    def replace(self, kind, resource_id, payload):
        with self.connection() as conn:
            conn.execute(update(tables[kind]).where(tables[kind].c.id == resource_id).values(payload=payload))
        return self.get(kind, resource_id)

    def create_run(self, scenario_id, key, runtime_selection=None):
        table = tables["simulation_runs"]
        with self.engine.connect() as conn:
            row = conn.execute(
                select(table.c.id).where(table.c.scenario_id == scenario_id, table.c.idempotency_key == key)
            ).first()
        if row:
            existing = self.get("simulation_runs", row[0])
            if runtime_selection and (
                existing.get("provider", "ollama"),
                existing.get("requested_model"),
                existing.get("mode", "history_forecast"),
            ) != (
                runtime_selection["provider"],
                runtime_selection["model"],
                runtime_selection.get("mode", "history_forecast"),
            ):
                raise ValueError("Chiave idempotente già usata con un modello diverso")
            return existing
        try:
            return self.create(
                "simulation_runs",
                {
                    "scenario_id": scenario_id,
                    "idempotency_key": key,
                    "status": "queued",
                    "completion_status": "preliminary",
                    "progress": 0,
                    "completed_policies": 0,
                    "required_policies": 0,
                    "error": None,
                    "phase": "queued",
                    "provider": (runtime_selection or {}).get("provider", "ollama"),
                    "requested_model": (runtime_selection or {}).get("model"),
                    "mode": (runtime_selection or {}).get("mode", "history_forecast"),
                    "slots": (runtime_selection or {}).get("slots"),
                },
            )
        except IntegrityError:
            return self.create_run(scenario_id, key, runtime_selection)

    def update_run(self, run_id, **changes):
        current = self.get("simulation_runs", run_id)
        table = tables["simulation_runs"]
        statement = update(table).where(
            table.c.id == run_id, table.c.payload["completion_status"].as_string() != "complete"
        )
        if set(changes) == {"performance"}:
            # A metrics-only checkpoint must not restore a status changed by cancellation/resume.
            statement = statement.where(table.c.payload["status"].as_string() == current["status"])
        elif changes.get("status") != "queued":
            statement = statement.where(table.c.payload["status"].as_string() != "canceled")
        with self.connection() as conn:
            conn.execute(
                statement.values(
                    payload={**current, **changes, "heartbeat_at": datetime.now(UTC).isoformat()}
                )
            )
        return self.get("simulation_runs", run_id)

    def finish_run(self, run_id, **changes):
        current = self.get("simulation_runs", run_id)
        table = tables["simulation_runs"]
        with self.connection() as conn:
            result = conn.execute(
                update(table)
                .where(table.c.id == run_id, table.c.payload["status"].as_string() == "running")
                .values(payload={**current, **changes})
            )
        return result.rowcount == 1

    def claim_run(self, run_id):
        current = self.get("simulation_runs", run_id)
        table = tables["simulation_runs"]
        with self.engine.begin() as conn:
            claimed = conn.execute(
                update(table)
                .where(
                    table.c.id == run_id,
                    table.c.payload["status"]
                    .as_string()
                    .in_(["queued", "waiting_for_runtime", "waiting_for_capacity", "failed"]),
                )
                .values(
                    payload={**current, "status": "running", "heartbeat_at": datetime.now(UTC).isoformat()}
                )
            )
        return claimed.rowcount == 1

    def get_policy(self, key):
        try:
            return self.get("agent_evaluations", key)
        except KeyError:
            return None

    def save_policy(self, key, payload):
        value = {**payload, "model_digest": payload.get("digest")}
        if self.get_policy(key):
            self.replace("agent_evaluations", key, value)
        else:
            try:
                self.create("agent_evaluations", value, key)
            except IntegrityError:
                pass

    def get_card(self, key):
        try:
            return self.get("persona_cards", key)
        except KeyError:
            return None

    def save_card(self, key, payload):
        value = {**payload, "model_digest": payload.get("digest")}
        if self.get_card(key):
            self.replace("persona_cards", key, value)
        else:
            try:
                self.create("persona_cards", value, key)
            except IntegrityError:
                pass

    def get_decision(self, key):
        try:
            return self.get("agent_decisions", key)
        except KeyError:
            return None

    def save_decision(self, key, payload):
        value = {**payload, "model_digest": payload.get("digest")}
        if self.get_decision(key):
            self.replace("agent_decisions", key, value)
        else:
            try:
                self.create("agent_decisions", value, key)
            except IntegrityError:
                pass


class ArtifactStore:
    def __init__(self, root, s3=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.s3 = s3

    def path(self, key):
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Percorso artefatto non consentito")
        return candidate

    def write_json(self, key, payload):
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.write_bytes(key, raw, "application/json")

    def write_bytes(self, key, raw, content_type="application/octet-stream"):
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + f".{uuid4().hex}.tmp")
        temporary.write_bytes(raw)
        os.replace(temporary, path)
        if self.s3:
            import boto3

            cfg = self.s3
            client = boto3.client(
                "s3",
                endpoint_url=cfg.s3_endpoint,
                aws_access_key_id=cfg.s3_access_key,
                aws_secret_access_key=cfg.s3_secret_key,
            )
            client.put_object(Bucket=cfg.s3_bucket, Key=key, Body=raw, ContentType=content_type)

    def read_json(self, key):
        return json.loads(self.path(key).read_text())
