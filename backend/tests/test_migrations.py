from alembic import command
from sqlalchemy import create_engine, text

from tests.conftest import alembic_config


def _vector_installed(url: str) -> bool:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            found = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return found.scalar() is not None
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_on_fresh_database(fresh_database_url: str) -> None:
    config = alembic_config(fresh_database_url)

    assert not _vector_installed(fresh_database_url)

    command.upgrade(config, "head")
    assert _vector_installed(fresh_database_url)

    command.downgrade(config, "base")
    assert not _vector_installed(fresh_database_url)


def test_full_upgrade_downgrade_cycle_with_audit_trigger(fresh_database_url: str) -> None:
    config = alembic_config(fresh_database_url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
