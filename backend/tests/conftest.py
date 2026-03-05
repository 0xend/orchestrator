from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "test.db"
    repos_yaml = tmp_path / "repos.yaml"
    repos_yaml.write_text(
        """
repos: []
""".strip()
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("API_AUTH_REQUIRED", "false")
    monkeypatch.setenv("REPOS_CONFIG_PATH", str(repos_yaml))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    from app.config import get_settings, load_repos_config

    get_settings.cache_clear()
    load_repos_config.cache_clear()

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    load_repos_config.cache_clear()
