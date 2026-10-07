from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
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

    llm_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    workflow_model: str = "gemini-3.5-flash-lite"
    workflow_confidence_threshold: float = 0.7
    workflow_cache_dir: Path = Path(".cache/workflow")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue]  # values come from the environment
