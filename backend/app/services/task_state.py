from __future__ import annotations

from fastapi import HTTPException, status

from app.db.models import Task, TaskStatus

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PLANNING: {TaskStatus.PLAN_REVIEW, TaskStatus.FAILED, TaskStatus.CANCELED},
    TaskStatus.PLAN_REVIEW: {TaskStatus.IMPLEMENTING, TaskStatus.FAILED, TaskStatus.CANCELED},
    TaskStatus.IMPLEMENTING: {TaskStatus.CODE_REVIEW, TaskStatus.FAILED, TaskStatus.CANCELED},
    TaskStatus.CODE_REVIEW: {TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELED},
    TaskStatus.COMPLETE: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELED: set(),
}


def ensure_transition(task: Task, target: TaskStatus) -> None:
    allowed = ALLOWED_TRANSITIONS.get(task.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid status transition: {task.status} -> {target}",
        )


def apply_transition(task: Task, target: TaskStatus) -> None:
    ensure_transition(task, target)
    task.status = target
    task.version = (task.version or 0) + 1
