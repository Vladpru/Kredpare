.PHONY: up down check test api

BACKEND := uv run --directory backend

up:
	docker compose up -d --wait
	docker compose run --rm minio-init

down:
	docker compose --profile init down

check:
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(BACKEND) pyright
	$(BACKEND) lint-imports

test:
	$(BACKEND) pytest

api:
	$(BACKEND) uvicorn kredpare.core.api.app:app --reload
