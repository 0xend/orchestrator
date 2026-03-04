from __future__ import annotations

import subprocess

from app.services.pr_creator import PRCreator


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
