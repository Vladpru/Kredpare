.PHONY: up down check test api worker beat demo

BACKEND := uv run --directory backend
DATAGEN := uv run --directory datagen

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
	$(DATAGEN) ruff check .
	$(DATAGEN) ruff format --check .
	$(DATAGEN) pyright

test:
	$(BACKEND) pytest
	$(DATAGEN) pytest

api:
	$(BACKEND) uvicorn kredpare.core.api.app:app --reload

worker:
	# Threads pool: macOS starts prefork children with spawn, which breaks Celery's
	# per-process setup. Linux (CI, deploy) forks and can use prefork.
	$(BACKEND) celery -A kredpare.core.worker worker --pool=threads --concurrency=4 --loglevel=info

beat:
	$(BACKEND) celery -A kredpare.core.worker beat --loglevel=info --schedule=/tmp/kredpare-celerybeat-schedule

# Seeds a separate demo database (see scripts/demo.sh), then runs the API and the web app.
demo: up
	./scripts/demo.sh
