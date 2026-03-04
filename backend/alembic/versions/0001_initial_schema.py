"""Initial orchestrator schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-04 14:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    task_status = sa.Enum(
        "planning",
        "plan_review",
        "implementing",
        "code_review",
        "complete",
        "failed",
        "canceled",
        name="task_status",
        native_enum=False,
    )
    agent_role = sa.Enum(
        "planner",
        "plan_reviewer",
        "implementer",
        "code_reviewer",
        name="agent_role",
        native_enum=False,
    )
    agent_session_status = sa.Enum(
        "active",
        "paused",
        "completed",
        "failed",
        name="agent_session_status",
        native_enum=False,
    )
    message_role = sa.Enum(
        "user",
        "assistant",
        "tool_use",
        "tool_result",
        name="message_role",
        native_enum=False,
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_user_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("repo_name", sa.String(length=128), nullable=False),
        sa.Column("worktree_path", sa.Text(), nullable=True),
        sa.Column("branch_name", sa.String(length=255), nullable=True),
        sa.Column("preview_url", sa.Text(), nullable=True),
        sa.Column("plan_markdown", sa.Text(), nullable=True),
        sa.Column("pr_url", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_tasks_owner_user_id", "tasks", ["owner_user_id"], unique=False)
    op.create_index("ix_tasks_repo_name", "tasks", ["repo_name"], unique=False)
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)

    op.create_table(
        "agent_sessions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_role", agent_role, nullable=False),
        sa.Column("status", agent_session_status, nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_sessions_task_id", "agent_sessions", ["task_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=36), sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"], unique=False)

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(length=36), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.String(length=128), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("task_id", "endpoint", "key", name="uq_task_endpoint_key"),
    )
    op.create_index("ix_idempotency_keys_task_id", "idempotency_keys", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_task_id", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_agent_sessions_task_id", table_name="agent_sessions")
    op.drop_table("agent_sessions")

    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_index("ix_tasks_repo_name", table_name="tasks")
    op.drop_index("ix_tasks_owner_user_id", table_name="tasks")
    op.drop_table("tasks")
