"""Run inside the API container; verifies persistence, RQ and S3 without LLM calls."""

import json
import time
import urllib.request

import boto3
from audience_simulator.config import settings
from audience_simulator.service import SimulationService
from redis import Redis
from rq import Queue

cfg = settings()
service = SimulationService(cfg)
assert service.repo.engine.dialect.name == "postgresql"
entry = service.import_dataset(cfg.data_dir)
assert not entry["audit"]["errors"]
redis = Redis.from_url(cfg.redis_url)
assert redis.ping()
for queue in ["default", "cloud"]:
    job = Queue(queue, connection=redis).enqueue("math.sqrt", 16)
    for _ in range(20):
        if job.is_finished:
            break
        time.sleep(0.5)
    assert job.result == 4, (queue, job.get_status())
service.store.write_json("smoke/storage-check.json", {"ok": True})
s3 = boto3.client(
    "s3",
    endpoint_url=cfg.s3_endpoint,
    aws_access_key_id=cfg.s3_access_key,
    aws_secret_access_key=cfg.s3_secret_key,
)
assert json.loads(s3.get_object(Bucket=cfg.s3_bucket, Key="smoke/storage-check.json")["Body"].read()) == {
    "ok": True
}
with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health") as response:
    assert json.load(response)["status"] == "ok"
print(
    json.dumps(
        {
            "postgresql": "pass",
            "import_dataset": "pass",
            "redis_rq_workers_default_and_cloud": "pass",
            "s3_read_write": "pass",
            "api_health": "pass",
            "ollama_ready": service.client().status()["ready"],
        }
    )
)
