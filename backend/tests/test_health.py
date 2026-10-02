from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from kredpare.core.api.app import create_app
from kredpare.core.api.health import Check, get_checks, redis_check
from kredpare.core.settings import get_settings


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_ok_when_all_dependencies_reachable(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok", "s3": "ok"},
    }


def test_health_503_names_the_unreachable_dependency() -> None:
    app = create_app()

    def checks_with_redis_down() -> dict[str, Check]:
        checks = get_checks(get_settings())
        # Port 1 on localhost: nothing listens there, so the connection is refused.
        checks["redis"] = redis_check("redis://localhost:1/0")
        return checks

    app.dependency_overrides[get_checks] = checks_with_redis_down
    with TestClient(app) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["s3"] == "ok"
    assert body["checks"]["redis"].startswith("error: ")
