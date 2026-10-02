from fastapi import FastAPI

from kredpare.core.api import health


def create_app() -> FastAPI:
    app = FastAPI(title="Kredpare")
    app.include_router(health.router)
    return app


app = create_app()
