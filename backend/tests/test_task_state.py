from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.db.models import Task, TaskStatus
from app.services.task_state import apply_transition


def make_task(status: TaskStatus) -> Task:
    return Task(
        owner_user_id="u1",
        title="t",
        description="d",
        status=status,
        repo_name="sample-repo",
    )


def test_apply_transition_allows_valid_edges() -> None:
    task = make_task(TaskStatus.PLANNING)
    apply_transition(task, TaskStatus.PLAN_REVIEW)
    assert task.status == TaskStatus.PLAN_REVIEW


def test_apply_transition_rejects_invalid_edge() -> None:
    task = make_task(TaskStatus.PLANNING)
    with pytest.raises(HTTPException) as exc:
        apply_transition(task, TaskStatus.COMPLETE)
    assert exc.value.status_code == 409
