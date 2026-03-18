"""Add languages, influence_score, and sentiment_data columns to persons

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-03-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # languages: JSON list of spoken language strings (e.g. ["English", "Hindi"])
    op.add_column("persons", sa.Column("languages", sa.Text(), nullable=True))
    # influence_score: float 0.0-1.0 from intelligence.py calculate_influence_score
    op.add_column("persons", sa.Column("influence_score", sa.Float(), nullable=True))
    # sentiment_data: JSON blob from intelligence.py analyze_sentiment, cached to avoid recomputation
    op.add_column("persons", sa.Column("sentiment_data", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("persons", "sentiment_data")
    op.drop_column("persons", "influence_score")
    op.drop_column("persons", "languages")
