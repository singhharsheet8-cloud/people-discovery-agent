"""Add LinkedIn rich profile fields: skills, projects, recommendations, followers_count, blog_url

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("persons", sa.Column("skills", sa.Text(), nullable=True))
    op.add_column("persons", sa.Column("projects", sa.Text(), nullable=True))
    op.add_column("persons", sa.Column("recommendations", sa.Text(), nullable=True))
    op.add_column("persons", sa.Column("followers_count", sa.Integer(), nullable=True))
    op.add_column("persons", sa.Column("blog_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("persons", "blog_url")
    op.drop_column("persons", "followers_count")
    op.drop_column("persons", "recommendations")
    op.drop_column("persons", "projects")
    op.drop_column("persons", "skills")
