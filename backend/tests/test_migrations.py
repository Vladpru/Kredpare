import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, make_url, text

from kredpare.core.settings import get_settings

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture
def fresh_database_url() -> Iterator[str]:
    """Create an empty database next to DATABASE_URL and drop it afterwards."""
    base_url = make_url(get_settings().database_url)
    name = f"kredpare_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield base_url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _vector_installed(url: str) -> bool:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            found = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return found.scalar() is not None
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_on_fresh_database(fresh_database_url: str) -> None:
    config = Config(str(ALEMBIC_INI))
    # configparser treats "%" as interpolation.
    config.set_main_option("sqlalchemy.url", fresh_database_url.replace("%", "%%"))

    assert not _vector_installed(fresh_database_url)

    command.upgrade(config, "head")
    assert _vector_installed(fresh_database_url)

    command.downgrade(config, "base")
    assert not _vector_installed(fresh_database_url)
