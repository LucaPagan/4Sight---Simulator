from .config import settings
from .service import SimulationService


def run(run_id):
    SimulationService(settings()).execute_run(run_id)


if __name__ == "__main__":
    from redis import Redis
    from rq import Worker

    Worker(["default"], connection=Redis.from_url(settings().redis_url)).work()
