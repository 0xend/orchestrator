from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agents.tools import ToolContext, bash, read_file, write_file
from app.db.models import AgentRole
from app.security.command_runner import CommandPolicyError
from app.security.path_guard import PathSecurityError


class FakeContainerManager:
    def __init__(self) -> None:
        self.exec_calls: list[dict] = []

    def read_file_in_container(self, _container_id: str, _path: str) -> str:
        return "hello"

    def write_file_in_container(self, _container_id: str, _path: str, _content: str) -> None:
        return None

    def exec_in_container(
        self,
        container_id: str,
        command: list[str],
        *,
        workdir: str | None = None,
        timeout: int = 60,
    ):
        self.exec_calls.append(
            {"container_id": container_id, "command": command, "workdir": workdir, "timeout": timeout}
        )
        return SimpleNamespace(exit_code=0, stdout="ok", stderr="")


def _ctx(cm: FakeContainerManager) -> ToolContext:
    return ToolContext(
        worktree_root=Path("/workspace"),
        role=AgentRole.PLANNER,
        container_id="ctr-1",
        container_manager=cm,
    )


@pytest.mark.asyncio
async def test_container_read_rejects_path_escape():
    with pytest.raises(PathSecurityError):
        await read_file(_ctx(FakeContainerManager()), "../etc/passwd")


@pytest.mark.asyncio
async def test_container_write_rejects_git_internals():
    with pytest.raises(PathSecurityError):
        await write_file(_ctx(FakeContainerManager()), ".git/config", "x")


@pytest.mark.asyncio
async def test_container_bash_executes_directly_without_shell_wrapper():
    cm = FakeContainerManager()
    result = await bash(_ctx(cm), "git status; rm -rf /")

    assert cm.exec_calls, "expected at least one exec call"
    command = cm.exec_calls[0]["command"]
    assert command[0] == "git"
    assert command[:2] != ["sh", "-c"]
    assert result["command"][0] == "git"


@pytest.mark.asyncio
async def test_container_bash_enforces_allowed_commands():
    with pytest.raises(CommandPolicyError):
        await bash(_ctx(FakeContainerManager()), "python -c 'print(1)'")
