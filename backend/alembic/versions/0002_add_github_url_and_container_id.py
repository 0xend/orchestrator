"""Add github_url and container_id columns to tasks.

Revision ID: 0002_add_github_url_container
Revises: 0001_initial_schema
Create Date: 2026-03-04 16:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_github_url_container"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("github_url", sa.String(length=512), nullable=False, server_default=""))
    op.add_column("tasks", sa.Column("container_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "container_id")
    op.drop_column("tasks", "github_url")
