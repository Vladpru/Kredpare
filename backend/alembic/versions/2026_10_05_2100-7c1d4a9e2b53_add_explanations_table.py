"""add explanations table

Revision ID: 7c1d4a9e2b53
Revises: e6914e56898a
Create Date: 2026-10-05 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c1d4a9e2b53"
down_revision: str | Sequence[str] | None = "e6914e56898a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explanations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("break_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("wrong_side", sa.Text(), nullable=True),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("level IN ('rule')", name=op.f("ck_explanations_level")),
        sa.CheckConstraint(
            "wrong_side IN ('seller', 'counterparty')", name=op.f("ck_explanations_wrong_side")
        ),
        sa.CheckConstraint(
            "proposal IN ('correction', 'email')", name=op.f("ck_explanations_proposal")
        ),
        sa.ForeignKeyConstraint(
            ["break_id"], ["breaks.id"], name=op.f("fk_explanations_break_id_breaks")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_explanations")),
        sa.UniqueConstraint("break_id", "level", name=op.f("uq_explanations_break_id")),
    )


def downgrade() -> None:
    op.drop_table("explanations")
