from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env for local development. Missing file is fine: CI and
# deployments set real environment variables, which take precedence.
_REPO_ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT_ENV, extra="ignore")

    database_url: str
    redis_url: str
    s3_endpoint_url: str | None = None  # None means real AWS S3
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket: str


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from the environment
