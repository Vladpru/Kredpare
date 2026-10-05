# 0007. Make datagen a uv workspace member

- **Status:** Accepted
- **Date:** 2026-10-05
- **Iteration:** 1

## Context

Datagen produces the synthetic files and ground truth that every eval depends on. It must use the same lending schemas and pricing math as the backend, so that generated data and production validation cannot drift apart. It must not ship inside the application. The repo layout in `CLAUDE.md` puts it at `datagen/` beside `backend/`.

## Decision

A virtual uv workspace at the repo root has two members, `backend` (`kredpare`) and `datagen` (`kredpare-datagen`). Datagen depends on `kredpare` as a workspace source and imports `kredpare.domains.lending` for schemas and pricing. The workspace has one `uv.lock` and one `.venv` at the root. `make check` and `make test` run ruff, pyright, and pytest for both members. CI installs with `uv sync --locked --all-packages`. Dependabot watches `/`.

## Alternatives considered

| Option | Why not |
|---|---|
| Module inside the backend (`kredpare.datagen`) | The generator ships with the app, and the core/domain boundary gets a third, unrelated tenant. |
| Separate project with a path dependency | Two lockfiles that can resolve different versions of shared libraries. |
| Duplicate the schemas in datagen | Generated data could pass datagen's checks and fail the backend's. |

## Consequences

- **Positive:** one source of truth for schemas and money math. The CLI installs as `kredpare-datagen`.
- **Negative / cost:** the environment moved from `backend/.venv` to `.venv`. Local setups need `uv sync --all-packages` once, and old `backend/.venv` directories can be deleted.
- **Follow-up:** if datagen ever needs a different Python or dependency version than the backend, split it into its own project.
