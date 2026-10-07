import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kredpare.core.api import breaks, health
from kredpare.core.api.breaks import ClauseResolver

CORS_ORIGINS_ENV = "KREDPARE_CORS_ORIGINS"
DEFAULT_CORS_ORIGINS = "http://localhost:3000"


def create_app(clause_resolver: ClauseResolver | None = None) -> FastAPI:
    """clause_resolver looks up the text of a cited clause; without one, citations carry no text."""
    app = FastAPI(title="Kredpare")
    app.state.clause_resolver = clause_resolver
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get(CORS_ORIGINS_ENV, DEFAULT_CORS_ORIGINS).split(","),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Reviewer"],
    )
    app.include_router(health.router)
    app.include_router(breaks.router)
    return app


app = create_app()
