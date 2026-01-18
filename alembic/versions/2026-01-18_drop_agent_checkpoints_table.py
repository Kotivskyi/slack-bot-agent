"""Drop agent_checkpoints table

Revision ID: fdef06989e4b
Revises: 5a8c2f3b1d4e
Create Date: 2026-01-18 16:07:30.170968

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fdef06989e4b"
down_revision: str | None = "5a8c2f3b1d4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("thread_id_idx"), table_name="agent_checkpoints")
    op.drop_table("agent_checkpoints")


def downgrade() -> None:
    op.create_table(
        "agent_checkpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("checkpoint_id", sa.String(255), nullable=False),
        sa.Column("parent_checkpoint_id", sa.String(255), nullable=True),
        sa.Column("checkpoint_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("agent_checkpoints_pkey")),
    )
    op.create_index(op.f("thread_id_idx"), "agent_checkpoints", ["thread_id"], unique=False)
