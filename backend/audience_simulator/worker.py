from .config import settings
from .service import SimulationService


def run(run_id):
    SimulationService(settings()).execute_run(run_id)


if __name__ == "__main__":
    from redis import Redis
    from rq import Worker

    cfg = settings()
    Worker([cfg.worker_queue], connection=Redis.from_url(cfg.redis_url)).work()
