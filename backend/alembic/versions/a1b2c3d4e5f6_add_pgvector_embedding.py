"""Add pgvector embedding column to persons

Revision ID: a1b2c3d4e5f6
Revises: 82ce633b332f
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "82ce633b332f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension (no-op if already enabled)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "persons",
        sa.Column("embedding", Vector(1536), nullable=True),
    )

    # IVFFlat index for approximate nearest-neighbour search (cosine distance).
    # lists=100 is a reasonable default for up to ~1 million rows.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_persons_embedding "
        "ON persons USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_persons_embedding")
    op.drop_column("persons", "embedding")
