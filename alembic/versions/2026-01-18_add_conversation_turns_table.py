"""Add conversation_turns table

Revision ID: a1b2c3d4e5f6
Revises: fdef06989e4b
Create Date: 2026-01-18 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "fdef06989e4b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("bot_response", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(50), nullable=False),
        sa.Column("sql_query", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("conversation_turns_pkey")),
    )
    op.create_index(
        op.f("ix_conversation_turns_thread_id"),
        "conversation_turns",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        "idx_conversation_turns_thread_recent",
        "conversation_turns",
        ["thread_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_conversation_turns_thread_recent", table_name="conversation_turns")
    op.drop_index(op.f("ix_conversation_turns_thread_id"), table_name="conversation_turns")
    op.drop_table("conversation_turns")
