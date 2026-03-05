from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.agents.definitions import PLANNING_TOOL_DEFINITIONS, TOOL_DEFINITIONS
from app.agents.engine import AgentEvent, run_agent_loop
from app.config import get_settings
from app.db.database import get_session_maker
from app.db.models import (
    AgentRole,
    AgentSession,
    AgentSessionStatus,
    Message,
    MessageRole,
    Task,
)
from app.services.container_manager import ContainerManager
from app.services.event_bus import event_bus

logger = logging.getLogger(__name__)

_running_agents: dict[str, asyncio.Task] = {}
_user_cancelled_tasks: set[str] = set()


def is_agent_running(task_id: str) -> bool:
    task = _running_agents.get(task_id)
    return task is not None and not task.done()


def cancel_agent(task_id: str) -> bool:
    task = _running_agents.pop(task_id, None)
    if task and not task.done():
        _user_cancelled_tasks.add(task_id)
        task.cancel()
        return True
    _user_cancelled_tasks.discard(task_id)
    return False


def launch_agent(task_id: str, session_id: str, user_message: str) -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY not set, skipping agent launch for task %s", task_id)
        return

    if is_agent_running(task_id):
        logger.warning("Agent already running for task %s", task_id)
        return

    bg_task = asyncio.create_task(_run_agent(task_id, session_id, user_message))
    _running_agents[task_id] = bg_task
    bg_task.add_done_callback(lambda _: _running_agents.pop(task_id, None))


async def _run_agent(task_id: str, session_id: str, user_message: str) -> None:
    settings = get_settings()
    session_maker = get_session_maker()
    container_manager = ContainerManager()

    try:
        async with session_maker() as db:
            session = (
                await db.execute(select(AgentSession).where(AgentSession.id == session_id))
            ).scalar_one()
            task = (await db.execute(select(Task).where(Task.id == task_id))).scalar_one()

            use_container_tools = task.container_id is not None

            # Provision isolated workspace container for remote-repo tasks.
            if not task.container_id and task.github_url:
                try:
                    info = await asyncio.to_thread(
                        container_manager.create_task_container,
                        task.id,
                        task.github_url,
                        github_token=settings.gh_token or None,
                    )
                    task.container_id = info.container_id
                    task.worktree_path = info.workspace_path
                    task.branch_name = info.branch_name
                    await db.commit()
                    await event_bus.publish(
                        task_id, "container_ready", {"container_id": info.container_id}
                    )
                    use_container_tools = True
                except Exception as exc:
                    raise RuntimeError(
                        f"Container provisioning failed for task {task_id}: {exc}"
                    ) from exc

            if not task.worktree_path:
                raise RuntimeError(f"Task {task_id} has no workspace path")

            history = await _load_conversation_history(db, session_id)

            tools = (
                PLANNING_TOOL_DEFINITIONS
                if session.agent_role == AgentRole.PLANNER
                else TOOL_DEFINITIONS
            )

            async def on_event(event: AgentEvent) -> None:
                if event.event == "token":
                    db.add(
                        Message(
                            session_id=session_id,
                            role=MessageRole.ASSISTANT,
                            content={"text": event.data["text"]},
                        )
                    )
                    await db.commit()
                elif event.event == "tool_use":
                    db.add(
                        Message(
                            session_id=session_id,
                            role=MessageRole.TOOL_USE,
                            content=event.data,
                        )
                    )
                    await db.commit()
                elif event.event == "tool_result":
                    db.add(
                        Message(
                            session_id=session_id,
                            role=MessageRole.TOOL_RESULT,
                            content=event.data,
                        )
                    )
                    await db.commit()

                await event_bus.publish(task_id, event.event, event.data)

            await run_agent_loop(
                session=session,
                user_message=user_message,
                tools=tools,
                on_event=on_event,
                cwd=task.worktree_path,
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
                max_tokens=settings.agent_max_tokens,
                max_steps=settings.agent_max_steps,
                container_id=task.container_id if use_container_tools else None,
                container_manager=container_manager if use_container_tools else None,
                conversation_history=history,
            )

            # If planner role: save last assistant text as plan
            if session.agent_role == AgentRole.PLANNER:
                last_msg = (
                    await db.execute(
                        select(Message)
                        .where(
                            Message.session_id == session_id,
                            Message.role == MessageRole.ASSISTANT,
                        )
                        .order_by(Message.id.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if last_msg and last_msg.content.get("text"):
                    task.plan_markdown = last_msg.content["text"]
                    await db.commit()
                    await event_bus.publish(task_id, "plan_ready", {"plan": task.plan_markdown})

            session.status = AgentSessionStatus.COMPLETED
            session.completed_at = datetime.now(UTC)
            await db.commit()

            await event_bus.publish(task_id, "agent_done", {"session_id": session_id})

    except asyncio.CancelledError:
        logger.info("Agent cancelled for task %s", task_id)
        if task_id in _user_cancelled_tasks:
            _user_cancelled_tasks.discard(task_id)
            await _mark_session_completed(session_maker, session_id)
        else:
            await _mark_session_failed(session_maker, session_id)
        raise

    except Exception:
        logger.exception("Agent failed for task %s", task_id)
        await _mark_session_failed(session_maker, session_id, task_id=task_id)


async def _mark_session_failed(
    session_maker, session_id: str, *, task_id: str | None = None
) -> None:
    try:
        async with session_maker() as db:
            session = (
                await db.execute(select(AgentSession).where(AgentSession.id == session_id))
            ).scalar_one_or_none()
            if session:
                session.status = AgentSessionStatus.FAILED
                session.completed_at = datetime.now(UTC)

            if task_id:
                task = (
                    await db.execute(select(Task).where(Task.id == task_id))
                ).scalar_one_or_none()
                if task:
                    task.last_error = "Agent execution failed"

            await db.commit()

        if task_id:
            await event_bus.publish(task_id, "error", {"message": "Agent execution failed"})
    except Exception:
        logger.exception("Failed to mark session %s as failed", session_id)


async def _mark_session_completed(session_maker, session_id: str) -> None:
    try:
        async with session_maker() as db:
            session = (
                await db.execute(select(AgentSession).where(AgentSession.id == session_id))
            ).scalar_one_or_none()
            if session:
                session.status = AgentSessionStatus.COMPLETED
                session.completed_at = datetime.now(UTC)
                await db.commit()
    except Exception:
        logger.exception("Failed to mark session %s as completed", session_id)


async def _load_conversation_history(db, session_id: str) -> list[dict]:
    """Convert DB messages to Anthropic API conversation format."""
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.id)
    )
    messages = result.scalars().all()

    if not messages:
        return []

    history: list[dict] = []
    current_assistant_blocks: list[dict] = []

    for msg in messages:
        if msg.role == MessageRole.USER:
            if current_assistant_blocks:
                history.append({"role": "assistant", "content": current_assistant_blocks})
                current_assistant_blocks = []
            history.append({"role": "user", "content": msg.content.get("text", "")})

        elif msg.role == MessageRole.ASSISTANT:
            current_assistant_blocks.append(
                {"type": "text", "text": msg.content.get("text", "")}
            )

        elif msg.role == MessageRole.TOOL_USE:
            current_assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": msg.content.get("id", ""),
                    "name": msg.content.get("tool", ""),
                    "input": msg.content.get("input", {}),
                }
            )

        elif msg.role == MessageRole.TOOL_RESULT:
            if current_assistant_blocks:
                history.append({"role": "assistant", "content": current_assistant_blocks})
                current_assistant_blocks = []
            history.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.content.get("id", ""),
                            "content": msg.content.get("output", ""),
                        }
                    ],
                }
            )

    if current_assistant_blocks:
        history.append({"role": "assistant", "content": current_assistant_blocks})

    return history
