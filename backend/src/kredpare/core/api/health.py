from collections.abc import Callable
from typing import TYPE_CHECKING, Annotated

import boto3
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import create_engine, text

from kredpare.core.settings import Settings, get_settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client  # dev-only stubs

TIMEOUT_SECONDS = 2

Check = Callable[[], None]
"""Raises if the dependency is unreachable."""


def database_check(url: str) -> Check:
    def check() -> None:
        engine = create_engine(url, connect_args={"connect_timeout": TIMEOUT_SECONDS})
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()

    return check


def redis_check(url: str) -> Check:
    def check() -> None:
        # redis-py and boto3 type **kwargs as Any; the ignores below are for that gap only.
        client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
            url, socket_timeout=TIMEOUT_SECONDS, socket_connect_timeout=TIMEOUT_SECONDS
        )
        try:
            client.ping()  # pyright: ignore[reportUnknownMemberType]
        finally:
            client.close()

    return check


def s3_check(settings: Settings) -> Check:
    def check() -> None:
        client: S3Client = boto3.client(  # pyright: ignore[reportUnknownMemberType]
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            config=BotoConfig(
                connect_timeout=TIMEOUT_SECONDS,
                read_timeout=TIMEOUT_SECONDS,
                retries={"max_attempts": 1},
            ),
        )
        client.head_bucket(Bucket=settings.s3_bucket)

    return check


def get_checks(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Check]:
    return {
        "database": database_check(settings.database_url),
        "redis": redis_check(settings.redis_url),
        "s3": s3_check(settings),
    }


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str]


router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
def health(
    response: Response, checks: Annotated[dict[str, Check], Depends(get_checks)]
) -> HealthResponse:
    results: dict[str, str] = {}
    for name, check in checks.items():
        try:
            check()
            results[name] = "ok"
        except Exception as exc:
            results[name] = f"error: {type(exc).__name__}"
    healthy = all(result == "ok" for result in results.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "unavailable", checks=results)
