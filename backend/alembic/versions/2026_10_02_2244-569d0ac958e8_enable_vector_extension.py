"""enable vector extension

Revision ID: 569d0ac958e8
Revises:
Create Date: 2026-10-02 22:44:49.615256

"""

from collections.abc import Sequence

from alembic import op

revision: str = "569d0ac958e8"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
