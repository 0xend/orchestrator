from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from python_on_whales import exceptions as docker_exceptions

from app.services.container_manager import ContainerInfo, ContainerManager


@pytest.fixture
def cm(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///test.db")
    monkeypatch.setenv("API_AUTH_REQUIRED", "false")
    from app.config import get_settings

    get_settings.cache_clear()

    with patch("app.services.container_manager.DockerClient") as mock_docker_cls:
        manager = ContainerManager()
        manager._docker = mock_docker_cls.return_value
        yield manager, mock_docker_cls.return_value

    get_settings.cache_clear()


def test_create_task_container_idempotent(cm):
    manager, docker_mock = cm

    # Simulate container already exists
    existing = SimpleNamespace(id="existing-id-123")
    docker_mock.container.inspect.return_value = existing
    manager._is_task_workspace_ready = lambda *_args, **_kwargs: True  # type: ignore[method-assign]

    result = manager.create_task_container("task-id-1234", "https://github.com/owner/repo")

    assert isinstance(result, ContainerInfo)
    assert result.container_id == "existing-id-123"
    assert result.branch_name == "task/task-id-1234"
    docker_mock.run.assert_not_called()


def test_create_task_container_recreates_unready_existing_container(cm):
    manager, docker_mock = cm

    existing = SimpleNamespace(id="existing-id-123")
    docker_mock.container.inspect.return_value = existing
    manager._is_task_workspace_ready = lambda *_args, **_kwargs: False  # type: ignore[method-assign]
    docker_mock.run.return_value = SimpleNamespace(id="new-id-456")
    docker_mock.execute.return_value = "ok"

    result = manager.create_task_container("task-id-1234", "https://github.com/owner/repo")

    assert result.container_id == "new-id-456"
    docker_mock.container.stop.assert_called_once_with("existing-id-123", time=10)
    docker_mock.container.remove.assert_called_once_with("existing-id-123", force=True)
    docker_mock.run.assert_called_once()


def test_create_task_container_does_not_embed_token_in_clone_url(cm):
    manager, docker_mock = cm

    docker_mock.container.inspect.side_effect = docker_exceptions.NoSuchContainer(
        ["orchestrator-task-task-id"], return_code=1
    )
    docker_mock.run.return_value = SimpleNamespace(id="new-id-1")
    docker_mock.execute.return_value = "ok"

    manager.create_task_container(
        "task-id-1234",
        "https://github.com/owner/repo",
        github_token="super-secret-token",
    )

    clone_call = next(
        call for call in docker_mock.execute.call_args_list if "clone" in call.args[1]
    )
    clone_cmd = clone_call.args[1]
    assert "https://github.com/owner/repo" in clone_cmd
    assert not any("super-secret-token" in str(part) for part in clone_cmd)


def test_cleanup_orphaned_containers_scopes_by_network(cm):
    manager, docker_mock = cm
    docker_mock.container.list.return_value = []

    manager.cleanup_orphaned_containers()

    docker_mock.container.list.assert_called_once()
    filters = docker_mock.container.list.call_args.kwargs["filters"]
    assert ("label", "orchestrator.managed=true") in filters
    assert ("label", "orchestrator.network=orchestrator_default") in filters


def test_destroy_container_handles_missing(cm):
    manager, docker_mock = cm

    docker_mock.container.stop.side_effect = docker_exceptions.NoSuchContainer(
        ["orchestrator-task-xxx"], return_code=1
    )

    # Should not raise
    manager.destroy_container("nonexistent-id")


def test_read_file_in_container(cm):
    manager, docker_mock = cm

    docker_mock.execute.return_value = "file content here"
    result = manager.read_file_in_container("ctr-id", "/workspace/test.py")

    assert result == "file content here"


def test_exec_result_fields(cm):
    manager, docker_mock = cm

    docker_mock.execute.return_value = "output text"
    result = manager.exec_in_container("ctr-id", ["echo", "hello"])

    assert result.exit_code == 0
    assert result.stdout == "output text"
    assert result.stderr == ""
