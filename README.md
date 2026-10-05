# Kredpare

[![CI](https://github.com/Gideonxqt/Kredpare/actions/workflows/ci.yml/badge.svg)](https://github.com/Gideonxqt/Kredpare/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Daily reconciliation of files exchanged between a company and its counterparties. Kredpare finds money discrepancies ("breaks") and drives each one to closure through a cascade: **rules (code) → workflow (RAG + 1 LLM call) → agent → escalate**, with human approval before anything is applied.

v1 domain: lending (forward flow loan sales). All data in this repository is synthetic.

**Status:** foundation and synthetic data with ground truth are done. Next: an MVP that tests whether rules plus one LLM call can explain most breaks — see [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md), then [`docs/POST_MVP_PLAN.md`](docs/POST_MVP_PLAN.md).

## Stack

- **Backend:** Python 3.12, uv, FastAPI, SQLAlchemy 2 + Alembic, Celery + Beat
- **Storage:** Postgres + pgvector, Redis, S3 (MinIO locally)
- **Frontend:** Next.js, Tailwind CSS, shadcn/ui, pnpm
- **Quality:** ruff, pyright (strict), pytest, import-linter, pre-commit, CodeQL

## Run locally

### Prerequisites

- Docker Desktop (running)
- [uv](https://docs.astral.sh/uv/) — installs Python 3.12 itself if needed
- Node.js (version in [`web/.nvmrc`](web/.nvmrc)) and pnpm
- `make`

### 1. Install dependencies

```bash
uv sync --all-packages                 # backend + datagen, one environment in .venv
(cd web && pnpm install)
.venv/bin/pre-commit install   # optional: git hooks
```

### 2. Configure `.env`

Copy the template and fill in the values for the local containers from `docker-compose.yml`:

```bash
cp .env.example .env
```

```
DATABASE_URL=postgresql+psycopg://kredpare:kredpare@localhost:5433/kredpare
REDIS_URL=redis://localhost:6380/0
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY_ID=kredpare
S3_SECRET_ACCESS_KEY=kredpare-local
S3_BUCKET=kredpare
```

These are throwaway credentials for local containers only. Postgres and Redis use host ports 5433 and 6380 to avoid clashing with other local projects.

### 3. Start infrastructure and migrate

```bash
make up                                          # postgres, redis, minio, mailpit; creates the bucket
uv run --directory backend alembic upgrade head  # database migrations
```

### 4. Run the services

Each in its own terminal:

```bash
make api              # API on http://localhost:8000
make worker           # Celery worker
make beat             # Celery Beat (sends a ping task every minute)
cd web && pnpm dev    # frontend on http://localhost:3000
```

### 5. Check it works

```bash
curl localhost:8000/health
# {"status":"ok","checks":{"database":"ok","redis":"ok","s3":"ok"}}
```

| URL | What |
|---|---|
| http://localhost:8000/health | Health of database, Redis, S3 (503 names the failing one) |
| http://localhost:8000/docs | API docs (Swagger) |
| http://localhost:3000 | Web app |
| http://localhost:9001 | MinIO console (`kredpare` / `kredpare-local`) |
| http://localhost:8025 | Mailpit inbox |

Stop the containers with `make down`.

## Development

```bash
make check   # ruff, ruff format --check, pyright, import-linter
make test    # pytest (needs `make up` and .env)
uv run kredpare-datagen --seed 42 --days 30   # synthetic files + ground_truth.jsonl in data/generated/
uv run --directory backend pytest tests/test_health.py::test_health_ok_when_all_dependencies_reachable   # one test
(cd web && pnpm lint && pnpm typecheck && pnpm build)
```

Every change goes through a branch and a PR; `main` is protected and requires the `backend` CI check.

## Layout

```
backend/src/kredpare/
├── core/          # generic: ingest, mapping, matching, rules, rag, cases, audit, api
└── domains/
    └── lending/   # schemas, break types, rules, tools, prompts
datagen/           # synthetic data, break injector, ground truth
web/               # Next.js
docs/              # plan, ADRs, domain docs, evals
```

`core/` never imports `domains/`; import-linter enforces this in CI. A domain plugs in through `DomainSpec`.

## Docs

- [MVP plan](docs/MVP_PLAN.md) — current scope, steps, success criteria
- [Post-MVP plan](docs/POST_MVP_PLAN.md) — the rest of v1, after the MVP verdict
- [Original implementation plan](docs/IMPLEMENTATION_PLAN.md) — component design reference
- [Glossary](docs/glossary.md) and [domain docs](docs/domain/) — counterparties, canonical schema, break taxonomy
- [Architecture decisions](docs/adr/)
- [Eval results](docs/evals.md)

## License

[MIT](LICENSE)
