from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.services.pr_creator import PRCreationError


def _create_task(client):
    response = client.post(
        "/api/tasks",
        json={"title": "Implement X", "description": "details", "repo_name": "sample-repo"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_approve_plan_is_idempotent(client, monkeypatch):
    from app.routes import tasks as tasks_route

    task = _create_task(client)

    monkeypatch.setattr(
        tasks_route,
        "worktree_manager",
        SimpleNamespace(create_worktree=Mock(return_value=SimpleNamespace(branch_name="task/1", worktree_path="/tmp/wt"))),
    )
    monkeypatch.setattr(
        tasks_route,
        "process_manager",
        SimpleNamespace(start=AsyncMock(return_value="http://localhost:3000"), stop=AsyncMock(return_value=None)),
    )

    headers = {"Idempotency-Key": "same-key"}
    first = client.post(f"/api/tasks/{task['id']}/approve-plan", headers=headers)
    second = client.post(f"/api/tasks/{task['id']}/approve-plan", headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert tasks_route.worktree_manager.create_worktree.call_count == 1


def test_request_review_failure_marks_task_failed(client, monkeypatch):
    from app.routes import tasks as tasks_route

    task = _create_task(client)

    monkeypatch.setattr(
        tasks_route,
        "worktree_manager",
        SimpleNamespace(create_worktree=Mock(return_value=SimpleNamespace(branch_name="task/2", worktree_path="/tmp/wt2"))),
    )
    monkeypatch.setattr(
        tasks_route,
        "process_manager",
        SimpleNamespace(start=AsyncMock(return_value="http://localhost:3000"), stop=AsyncMock(return_value=None)),
    )
    monkeypatch.setattr(
        tasks_route,
        "pr_creator",
        SimpleNamespace(create_or_update_pr=Mock(side_effect=PRCreationError("gh auth failed"))),
    )

    approved = client.post(f"/api/tasks/{task['id']}/approve-plan", headers={"Idempotency-Key": "approve-1"})
    assert approved.status_code == 200, approved.text

    reviewed = client.post(f"/api/tasks/{task['id']}/request-review", headers={"Idempotency-Key": "review-1"})
    assert reviewed.status_code == 500

    task_detail = client.get(f"/api/tasks/{task['id']}")
    assert task_detail.status_code == 200
    payload = task_detail.json()
    assert payload["status"] == "failed"
    assert "gh auth failed" in payload["last_error"]


def test_request_review_is_idempotent_on_success(client, monkeypatch):
    from app.routes import tasks as tasks_route

    task = _create_task(client)

    monkeypatch.setattr(
        tasks_route,
        "worktree_manager",
        SimpleNamespace(
            create_worktree=Mock(
                return_value=SimpleNamespace(branch_name="task/3", worktree_path="/tmp/wt3")
            )
        ),
    )
    stop_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        tasks_route,
        "process_manager",
        SimpleNamespace(start=AsyncMock(return_value="http://localhost:3000"), stop=stop_mock),
    )
    pr_mock = Mock(
        return_value=SimpleNamespace(
            pr_url="https://github.com/example/repo/pull/42", branch_name="task/3", commit_sha="abc"
        )
    )
    monkeypatch.setattr(tasks_route, "pr_creator", SimpleNamespace(create_or_update_pr=pr_mock))

    approved = client.post(f"/api/tasks/{task['id']}/approve-plan", headers={"Idempotency-Key": "approve-3"})
    assert approved.status_code == 200, approved.text

    headers = {"Idempotency-Key": "review-same"}
    first = client.post(f"/api/tasks/{task['id']}/request-review", headers=headers)
    second = client.post(f"/api/tasks/{task['id']}/request-review", headers=headers)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert pr_mock.call_count == 1
    assert stop_mock.await_count == 1
