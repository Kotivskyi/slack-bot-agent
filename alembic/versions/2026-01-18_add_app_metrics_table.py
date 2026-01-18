"""Add app_metrics table

Revision ID: 5a8c2f3b1d4e
Revises: 43219e97582e
Create Date: 2026-01-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5a8c2f3b1d4e"
down_revision: str | None = "43219e97582e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_metrics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("app_name", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("installs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("in_app_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ads_revenue", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ua_cost", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id", name=op.f("app_metrics_pkey")),
    )
    op.create_index(op.f("ix_app_metrics_app_name"), "app_metrics", ["app_name"], unique=False)
    op.create_index(op.f("ix_app_metrics_platform"), "app_metrics", ["platform"], unique=False)
    op.create_index(op.f("ix_app_metrics_date"), "app_metrics", ["date"], unique=False)
    op.create_index(op.f("ix_app_metrics_country"), "app_metrics", ["country"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_app_metrics_country"), table_name="app_metrics")
    op.drop_index(op.f("ix_app_metrics_date"), table_name="app_metrics")
    op.drop_index(op.f("ix_app_metrics_platform"), table_name="app_metrics")
    op.drop_index(op.f("ix_app_metrics_app_name"), table_name="app_metrics")
    op.drop_table("app_metrics")
