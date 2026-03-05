from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.prompts import (
    CODE_REVIEWER_PROMPT,
    IMPLEMENTER_PROMPT,
    PLANNER_PROMPT,
    PLAN_REVIEWER_PROMPT,
)
from app.config import get_repo_config, get_settings
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
from app.services.agent_runner import cancel_agent, is_agent_running, launch_agent
from app.services.container_manager import ContainerError, ContainerManager
from app.services.event_bus import event_bus
from app.services.process_manager import process_manager
from app.services.pr_creator import PRCreationError, PRCreator
from app.services.task_state import apply_transition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
container_manager = ContainerManager()
pr_creator = PRCreator()

_GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


def _parse_github_url(url: str) -> tuple[str, str]:
    m = _GITHUB_URL_RE.match(url)
    if not m:
        raise ValueError(f"Invalid GitHub URL: {url}")
    return m.group("owner"), m.group("repo")


class CreateTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    github_url: str = Field(min_length=1, max_length=512)


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
        "github_url": task.github_url,
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
    settings = get_settings()
    try:
        owner, repo_short = _parse_github_url(payload.github_url)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    repo_name = f"{owner}/{repo_short}"
    has_agent_api_key = bool(settings.anthropic_api_key.strip())
    generated_plan = None
    if not has_agent_api_key:
        generated_plan = (
            f"## Initial Plan\n\n"
            f"1. Explore repository `{repo_name}` for modules relevant to `{payload.title}`.\n"
            f"2. Implement requested changes for: {payload.description}.\n"
            "3. Run verification and prepare PR-ready review notes.\n"
        )

    task = Task(
        owner_user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        repo_name=repo_name,
        github_url=payload.github_url,
        status=TaskStatus.PLANNING,
        plan_markdown=generated_plan,
    )

    session = AgentSession(
        task=task,
        agent_role=AgentRole.PLANNER,
        status=AgentSessionStatus.ACTIVE if has_agent_api_key else AgentSessionStatus.COMPLETED,
        system_prompt=PLANNER_PROMPT,
        completed_at=None if has_agent_api_key else datetime.now(UTC),
    )

    db.add(task)
    db.add(session)
    await db.commit()
    await db.refresh(task)
    await db.refresh(session)

    await event_bus.publish(task.id, "status_change", {"status": task.status.value})

    if not has_agent_api_key:
        await event_bus.publish(task.id, "plan_ready", {"plan": task.plan_markdown})
        return _task_payload(task)

    # Auto-trigger planner agent (container creation happens in background)
    planner_message = f"Plan the implementation for: {task.title}\n\n{task.description}"
    user_msg = Message(
        session_id=session.id,
        role=MessageRole.USER,
        content={"text": planner_message},
    )
    db.add(user_msg)
    await db.commit()
    launch_agent(task.id, session.id, planner_message)

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
    settings = get_settings()
    task = await _load_task_for_user(db, task_id, current_user.id, for_update=True)

    if task.status not in {TaskStatus.PLANNING, TaskStatus.IMPLEMENTING}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is not interactive in status '{task.status.value}'",
        )

    if is_agent_running(task_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Agent is already running for this task",
        )

    if not settings.anthropic_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY is not configured",
        )

    session = await _ensure_active_session(db, task)

    user_message = Message(
        session_id=session.id,
        role=MessageRole.USER,
        content={"text": payload.content},
    )
    db.add(user_message)
    await db.commit()

    launch_agent(task.id, session.id, payload.content)
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

    settings = get_settings()
    try:
        repo_config = get_repo_config(task.repo_name)
    except KeyError:
        repo_config = None

    try:
        if not task.container_id:
            info = container_manager.create_task_container(
                task.id,
                task.github_url,
                github_token=settings.gh_token or None,
            )
            task.container_id = info.container_id
            task.worktree_path = info.workspace_path
            task.branch_name = info.branch_name

        task.preview_url = await process_manager.start_in_container(
            task.id,
            task.container_id,
            container_manager,
            task.worktree_path,
            startup=repo_config.startup if repo_config else None,
            preview=repo_config.preview if repo_config else None,
        )
    except (ContainerError, Exception) as exc:
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

    if not task.worktree_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task has no worktree; approve-plan must run first",
        )

    try:
        repo_config = get_repo_config(task.repo_name)
    except KeyError:
        repo_config = None

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
            base_branch=repo_config.pr.base_branch if repo_config else None,
            title=f"{task.title} ({task.id[:8]})",
            body=(
                "Automated PR created by Orchestrator.\n\n"
                f"- Task ID: `{task.id}`\n"
                f"- Repo: `{task.repo_name}`\n"
                f"- Description: {task.description}\n"
            ),
            draft=repo_config.pr.draft if repo_config else True,
            container_id=task.container_id,
            container_manager=container_manager if task.container_id else None,
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

    # Destroy container after PR creation
    if task.container_id:
        container_manager.destroy_container(task.container_id)

    await process_manager.stop(task.id)

    await event_bus.publish(task.id, "review_done", {"pr_url": task.pr_url})
    await event_bus.publish(task.id, "status_change", {"status": task.status.value})
    return response


@router.post("/{task_id}/stop")
async def stop_agent(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Soft-stop: interrupt the running agent loop without cancelling the task."""
    await _load_task_for_user(db, task_id, current_user.id)

    if not is_agent_running(task_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No agent is currently running for this task",
        )

    cancel_agent(task_id)

    # Mark the active session as COMPLETED so _ensure_active_session creates a fresh one
    active_session_q = (
        select(AgentSession)
        .where(AgentSession.task_id == task_id, AgentSession.status == AgentSessionStatus.ACTIVE)
        .order_by(AgentSession.started_at.desc())
    )
    active_session = (await db.execute(active_session_q)).scalars().first()
    if active_session:
        active_session.status = AgentSessionStatus.COMPLETED
        active_session.completed_at = datetime.now(UTC)
        await db.commit()

    await event_bus.publish(task_id, "agent_stopped", {"task_id": task_id})
    return {"ok": True}


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    task = await _load_task_for_user(db, task_id, current_user.id, for_update=True)

    cancel_agent(task_id)

    if task.status in {
        TaskStatus.PLANNING,
        TaskStatus.PLAN_REVIEW,
        TaskStatus.IMPLEMENTING,
        TaskStatus.CODE_REVIEW,
    }:
        apply_transition(task, TaskStatus.CANCELED)

    if task.container_id:
        container_manager.destroy_container(task.container_id)

    await process_manager.stop(task.id)

    await db.commit()
    await event_bus.publish(task.id, "status_change", {"status": task.status.value})
    return {"ok": True, "status": task.status.value}
