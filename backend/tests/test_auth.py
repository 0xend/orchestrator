from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_auth_required_rejects_missing_bearer(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "auth.db"
    repos_yaml = tmp_path / "repos.yaml"
    repos_yaml.write_text("repos: []\n", encoding="utf-8")

    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("API_AUTH_REQUIRED", "true")
    monkeypatch.setenv("DEV_BEARER_TOKEN", "secret-token")
    monkeypatch.setenv("REPOS_CONFIG_PATH", str(repos_yaml))

    from app.config import get_settings, load_repos_config

    get_settings.cache_clear()
    load_repos_config.cache_clear()

    from app.main import app

    with TestClient(app) as client:
        unauthorized = client.get("/api/repos")
        assert unauthorized.status_code == 401

        authorized = client.get("/api/repos", headers={"Authorization": "Bearer secret-token"})
        assert authorized.status_code == 200

    get_settings.cache_clear()
    load_repos_config.cache_clear()
