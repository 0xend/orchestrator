from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

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

    result = manager.create_task_container("task-id-1234", "https://github.com/owner/repo")

    assert isinstance(result, ContainerInfo)
    assert result.container_id == "existing-id-123"
    assert result.branch_name == "task/task-id-1234"
    docker_mock.run.assert_not_called()


def test_destroy_container_handles_missing(cm):
    manager, docker_mock = cm

    from python_on_whales import exceptions as docker_exceptions

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
