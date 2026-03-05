from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from app.services.container_manager import ContainerError
from app.services.pr_creator import PRCreationError, PRCreator


def test_create_pr_uses_existing_url(monkeypatch, tmp_path):
    creator = PRCreator()

    calls: list[list[str]] = []

    def fake_run(command, *, cwd, error_prefix, env=None):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(creator, "_commit_changes_if_needed", lambda *_args, **_kwargs: "abc123")
    monkeypatch.setattr(creator, "_find_existing_pr_url", lambda *args: "https://github.com/o/r/pull/9")
    monkeypatch.setattr(creator, "_run", fake_run)

    result = creator.create_or_update_pr(
        worktree_path=str(tmp_path),
        branch_name="task/123",
        base_branch="main",
        title="Sample",
        body="Body",
        draft=True,
    )

    assert result.pr_url == "https://github.com/o/r/pull/9"
    assert result.commit_sha == "abc123"
    assert any(cmd[:3] == ["git", "push", "-u"] for cmd in calls)
    assert not any(cmd[:3] == ["gh", "pr", "create"] for cmd in calls)


def test_create_pr_resolves_base_branch_from_origin_head(monkeypatch, tmp_path):
    creator = PRCreator()

    calls: list[list[str]] = []

    def fake_run(command, *, cwd, error_prefix, env=None):
        calls.append(command)
        if command[:3] == ["gh", "pr", "create"]:
            return subprocess.CompletedProcess(
                command, 0, stdout="https://github.com/o/r/pull/42\n", stderr=""
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(creator, "_commit_changes_if_needed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(creator, "_find_existing_pr_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(creator, "_resolve_base_branch", lambda *_args, **_kwargs: "develop")
    monkeypatch.setattr(creator, "_run", fake_run)

    result = creator.create_or_update_pr(
        worktree_path=str(tmp_path),
        branch_name="task/123",
        base_branch=None,
        title="Sample",
        body="Body",
        draft=False,
    )

    assert result.pr_url == "https://github.com/o/r/pull/42"
    create_cmd = next(cmd for cmd in calls if cmd[:3] == ["gh", "pr", "create"])
    assert create_cmd[create_cmd.index("--base") + 1] == "develop"


def test_create_pr_in_container_raises_when_commit_fails():
    creator = PRCreator()

    class FailingCommitManager:
        def exec_in_container(self, _container_id, command, *, workdir=None, timeout=60):
            if command[:3] == ["git", "status", "--porcelain"]:
                return SimpleNamespace(exit_code=0, stdout=" M app.py\n", stderr="")
            if command[:2] == ["git", "commit"]:
                raise ContainerError("boom")
            return SimpleNamespace(exit_code=0, stdout="", stderr="")

    with pytest.raises(PRCreationError, match="Failed to commit changes"):
        creator.create_or_update_pr(
            worktree_path="/workspace",
            branch_name="task/123",
            base_branch="main",
            title="Sample",
            body="Body",
            draft=False,
            container_id="container-1",
            container_manager=FailingCommitManager(),
        )
