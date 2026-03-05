from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services import agent_runner


class _CancelOnEnter:
    async def __aenter__(self):
        raise asyncio.CancelledError()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_run_agent_user_cancel_marks_session_completed(monkeypatch):
    monkeypatch.setattr(agent_runner, "get_session_maker", lambda: (lambda: _CancelOnEnter()))
    mark_completed = AsyncMock()
    mark_failed = AsyncMock()
    monkeypatch.setattr(agent_runner, "_mark_session_completed", mark_completed)
    monkeypatch.setattr(agent_runner, "_mark_session_failed", mark_failed)

    agent_runner._user_cancelled_tasks.add("task-user-cancel")

    with pytest.raises(asyncio.CancelledError):
        await agent_runner._run_agent("task-user-cancel", "session-1", "hello")

    mark_completed.assert_awaited_once()
    mark_failed.assert_not_awaited()
    assert "task-user-cancel" not in agent_runner._user_cancelled_tasks


@pytest.mark.asyncio
async def test_run_agent_non_user_cancel_marks_session_failed(monkeypatch):
    monkeypatch.setattr(agent_runner, "get_session_maker", lambda: (lambda: _CancelOnEnter()))
    mark_completed = AsyncMock()
    mark_failed = AsyncMock()
    monkeypatch.setattr(agent_runner, "_mark_session_completed", mark_completed)
    monkeypatch.setattr(agent_runner, "_mark_session_failed", mark_failed)

    with pytest.raises(asyncio.CancelledError):
        await agent_runner._run_agent("task-non-user-cancel", "session-2", "hello")

    mark_failed.assert_awaited_once()
    mark_completed.assert_not_awaited()
