from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIENCE_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///artifacts/audience.db"
    data_dir: Path = Path("data")
    artifact_dir: Path = Path("artifacts")
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"
    queue_mode: str = "local"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = None
    s3_bucket: str = "audience"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    max_evaluations: int = 5000
    monte_carlo_draws: int = 1000


def settings():
    value = Settings()
    value.artifact_dir.mkdir(parents=True, exist_ok=True)
    return value
