from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.prompts import (
    CODE_REVIEWER_PROMPT,
    IMPLEMENTER_PROMPT,
    PLANNER_PROMPT,
    PLAN_REVIEWER_PROMPT,
)
from app.config import get_repo_config
from app.db.database import get_db
from app.db.models import (
    AgentRole,
    AgentSession,
    AgentSessionStatus,
    IdempotencyKey,
    Message,
    MessageRole,
    Task,
    TaskStatus,
)
from app.security.auth import AuthenticatedUser, get_current_user
from app.services.event_bus import event_bus
from app.services.process_manager import ProcessStartupError, process_manager
from app.services.pr_creator import PRCreationError, PRCreator
from app.services.task_state import apply_transition
from app.services.worktree import WorktreeError, WorktreeManager

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
worktree_manager = WorktreeManager()
pr_creator = PRCreator()


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    repo_name: str = Field(min_length=1, max_length=128)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)


def _task_payload(task: Task) -> dict:
    return {
        "id": task.id,
        "owner_user_id": task.owner_user_id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "repo_name": task.repo_name,
        "worktree_path": task.worktree_path,
        "branch_name": task.branch_name,
        "preview_url": task.preview_url,
        "plan_markdown": task.plan_markdown,
        "pr_url": task.pr_url,
        "version": task.version,
        "last_error": task.last_error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


async def _load_task_for_user(
    db: AsyncSession,
    task_id: str,
    user_id: str,
    *,
    for_update: bool = False,
) -> Task:
    stmt = select(Task).where(Task.id == task_id, Task.owner_user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()

    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


async def _idempotency_lookup(
    db: AsyncSession,
    task_id: str,
    endpoint: str,
    key: str,
) -> IdempotencyKey | None:
    query = select(IdempotencyKey).where(
        IdempotencyKey.task_id == task_id,
        IdempotencyKey.endpoint == endpoint,
        IdempotencyKey.key == key,
    )
    return (await db.execute(query)).scalar_one_or_none()


async def _ensure_active_session(db: AsyncSession, task: Task) -> AgentSession:
    query = (
        select(AgentSession)
        .where(AgentSession.task_id == task.id, AgentSession.status == AgentSessionStatus.ACTIVE)
        .order_by(AgentSession.started_at.desc())
    )
    session = (await db.execute(query)).scalars().first()
    if session:
        return session

    role = AgentRole.PLANNER if task.status == TaskStatus.PLANNING else AgentRole.IMPLEMENTER
    prompt = PLANNER_PROMPT if role == AgentRole.PLANNER else IMPLEMENTER_PROMPT

    session = AgentSession(
        task_id=task.id,
        agent_role=role,
        status=AgentSessionStatus.ACTIVE,
        system_prompt=prompt,
    )
    db.add(session)
    await db.flush()
    return session


@router.get("")
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[dict]:
    tasks = (
        (
            await db.execute(
                select(Task)
                .where(Task.owner_user_id == current_user.id)
                .order_by(Task.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_task_payload(task) for task in tasks]


@router.post("")
async def create_task(
    payload: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    try:
        get_repo_config(payload.repo_name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    generated_plan = (
        f"## Initial Plan\n\n"
        f"1. Explore repository `{payload.repo_name}` for relevant modules.\n"
        f"2. Implement requested changes for: {payload.title}.\n"
        "3. Run verification and prepare review notes.\n"
    )

    task = Task(
        owner_user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        repo_name=payload.repo_name,
        status=TaskStatus.PLANNING,
        plan_markdown=generated_plan,
    )

    session = AgentSession(
        task=task,
        agent_role=AgentRole.PLANNER,
        status=AgentSessionStatus.ACTIVE,
        system_prompt=PLANNER_PROMPT,
    )

    db.add(task)
    db.add(session)
    await db.commit()
    await db.refresh(task)

    await event_bus.publish(task.id, "status_change", {"status": task.status.value})
    await event_bus.publish(task.id, "plan_ready", {"plan": task.plan_markdown})
    return _task_payload(task)


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    query = (
        select(Task)
        .where(Task.id == task_id, Task.owner_user_id == current_user.id)
        .options(selectinload(Task.agent_sessions).selectinload(AgentSession.messages))
    )
    task = (await db.execute(query)).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    payload = _task_payload(task)
    payload["sessions"] = [
        {
            "id": sess.id,
            "agent_role": sess.agent_role.value,
            "status": sess.status.value,
            "started_at": sess.started_at.isoformat() if sess.started_at else None,
            "completed_at": sess.completed_at.isoformat() if sess.completed_at else None,
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role.value,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in sess.messages
            ],
        }
        for sess in task.agent_sessions
    ]
    return payload


@router.post("/{task_id}/messages")
async def send_message(
    task_id: str,
    payload: SendMessageRequest,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    task = await _load_task_for_user(db, task_id, current_user.id, for_update=True)

    if task.status not in {TaskStatus.PLANNING, TaskStatus.IMPLEMENTING}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is not interactive in status '{task.status.value}'",
        )

    session = await _ensure_active_session(db, task)

    user_message = Message(
        session_id=session.id,
        role=MessageRole.USER,
        content={"text": payload.content},
    )
    assistant_message = Message(
        session_id=session.id,
        role=MessageRole.ASSISTANT,
        content={"text": "Message received. Agent execution wiring is active in scaffold mode."},
    )

    db.add(user_message)
    db.add(assistant_message)
    await db.commit()

    await event_bus.publish(task.id, "token", {"text": assistant_message.content["text"]})
    return {"ok": True}


@router.post("/{task_id}/approve-plan")
async def approve_plan(
    task_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    task = await _load_task_for_user(db, task_id, current_user.id, for_update=True)
    existing = await _idempotency_lookup(db, task_id, "approve-plan", idempotency_key)
    if existing:
        return existing.response_json

    if not task.plan_markdown:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Plan must exist before approval",
        )

    apply_transition(task, TaskStatus.PLAN_REVIEW)
    reviewer_session = AgentSession(
        task_id=task.id,
        agent_role=AgentRole.PLAN_REVIEWER,
        status=AgentSessionStatus.COMPLETED,
        system_prompt=PLAN_REVIEWER_PROMPT,
        completed_at=datetime.now(UTC),
    )
    db.add(reviewer_session)

    apply_transition(task, TaskStatus.IMPLEMENTING)
    implementer_session = AgentSession(
        task_id=task.id,
        agent_role=AgentRole.IMPLEMENTER,
        status=AgentSessionStatus.ACTIVE,
        system_prompt=IMPLEMENTER_PROMPT,
    )
    db.add(implementer_session)

    repo = get_repo_config(task.repo_name)

    try:
        if not task.worktree_path:
            info = worktree_manager.create_worktree(str(repo.path), task.id)
            task.worktree_path = info.worktree_path
            task.branch_name = info.branch_name

        task.preview_url = await process_manager.start(task.id, repo, task.worktree_path)
    except (WorktreeError, ProcessStartupError) as exc:
        task.status = TaskStatus.FAILED
        task.last_error = str(exc)
        task.version = (task.version or 0) + 1
        await db.commit()
        await event_bus.publish(task.id, "status_change", {"status": task.status.value, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    response = {
        "task_id": task.id,
        "status": task.status.value,
        "worktree_path": task.worktree_path,
        "branch_name": task.branch_name,
        "preview_url": task.preview_url,
    }

    db.add(
        IdempotencyKey(
            task_id=task.id,
            endpoint="approve-plan",
            key=idempotency_key,
            response_json=response,
        )
    )
    await db.commit()

    await event_bus.publish(
        task.id,
        "status_change",
        {"status": task.status.value, "preview_url": task.preview_url},
    )
    return response


@router.post("/{task_id}/request-review")
async def request_review(
    task_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    task = await _load_task_for_user(db, task_id, current_user.id, for_update=True)
    existing = await _idempotency_lookup(db, task_id, "request-review", idempotency_key)
    if existing:
        return existing.response_json

    repo = get_repo_config(task.repo_name)
    if not task.worktree_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task has no worktree; approve-plan must run first",
        )

    apply_transition(task, TaskStatus.CODE_REVIEW)
    review_session = AgentSession(
        task_id=task.id,
        agent_role=AgentRole.CODE_REVIEWER,
        status=AgentSessionStatus.ACTIVE,
        system_prompt=CODE_REVIEWER_PROMPT,
    )
    db.add(review_session)

    try:
        pr_result = pr_creator.create_or_update_pr(
            worktree_path=task.worktree_path,
            branch_name=task.branch_name,
            base_branch=repo.pr.base_branch,
            title=f"{task.title} ({task.id[:8]})",
            body=(
                "Automated PR created by Orchestrator.\n\n"
                f"- Task ID: `{task.id}`\n"
                f"- Repo: `{task.repo_name}`\n"
                f"- Description: {task.description}\n"
            ),
            draft=repo.pr.draft,
        )
    except PRCreationError as exc:
        task.last_error = str(exc)
        review_session.status = AgentSessionStatus.FAILED
        review_session.completed_at = datetime.now(UTC)
        apply_transition(task, TaskStatus.FAILED)
        await db.commit()
        await event_bus.publish(task.id, "status_change", {"status": task.status.value, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    review_session.status = AgentSessionStatus.COMPLETED
    review_session.completed_at = datetime.now(UTC)
    task.pr_url = pr_result.pr_url
    task.branch_name = pr_result.branch_name
    apply_transition(task, TaskStatus.COMPLETE)

    response = {"task_id": task.id, "status": task.status.value, "pr_url": task.pr_url}

    db.add(
        IdempotencyKey(
            task_id=task.id,
            endpoint="request-review",
            key=idempotency_key,
            response_json=response,
        )
    )
    await db.commit()

    await process_manager.stop(task.id)

    await event_bus.publish(task.id, "review_done", {"pr_url": task.pr_url})
    await event_bus.publish(task.id, "status_change", {"status": task.status.value})
    return response


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    task = await _load_task_for_user(db, task_id, current_user.id, for_update=True)

    if task.status in {
        TaskStatus.PLANNING,
        TaskStatus.PLAN_REVIEW,
        TaskStatus.IMPLEMENTING,
        TaskStatus.CODE_REVIEW,
    }:
        apply_transition(task, TaskStatus.CANCELED)

    if task.worktree_path:
        await process_manager.stop(task.id)
        try:
            worktree_manager.remove_worktree(task.worktree_path)
        except WorktreeError as exc:
            task.last_error = str(exc)

    await db.commit()
    await event_bus.publish(task.id, "status_change", {"status": task.status.value})
    return {"ok": True, "status": task.status.value}
