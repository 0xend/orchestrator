"""Add model_provider and model_id columns to tasks.

Revision ID: 0003_add_model_provider
Revises: 0002_add_github_url_container
Create Date: 2026-03-05 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_add_model_provider"
down_revision = "0002_add_github_url_container"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("model_provider", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("model_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "model_id")
    op.drop_column("tasks", "model_provider")
