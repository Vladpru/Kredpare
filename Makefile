.PHONY: up down check test

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
