"""allow workflow explanations

Revision ID: a3f8c1d27e64
Revises: 7c1d4a9e2b53
Create Date: 2026-10-07 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a3f8c1d27e64"
down_revision: str | Sequence[str] | None = "7c1d4a9e2b53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_explanations_level"), "explanations", type_="check")
    op.create_check_constraint(
        op.f("ck_explanations_level"), "explanations", "level IN ('rule', 'workflow')"
    )


def downgrade() -> None:
    op.execute("DELETE FROM explanations WHERE level = 'workflow'")
    op.drop_constraint(op.f("ck_explanations_level"), "explanations", type_="check")
    op.create_check_constraint(op.f("ck_explanations_level"), "explanations", "level IN ('rule')")
