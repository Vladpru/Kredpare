.PHONY: up down check test api worker beat

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

worker:
	# Threads pool: macOS starts prefork children with spawn, which breaks Celery's
	# per-process setup. Linux (CI, deploy) forks and can use prefork.
	$(BACKEND) celery -A kredpare.core.worker worker --pool=threads --concurrency=4 --loglevel=info

beat:
	$(BACKEND) celery -A kredpare.core.worker beat --loglevel=info --schedule=/tmp/kredpare-celerybeat-schedule
