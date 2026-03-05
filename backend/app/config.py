from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StartupConfig(BaseModel):
    command: list[str]
    cwd: str = "."
    env: dict[str, str] = Field(default_factory=dict)
    ready_timeout_seconds: int = 180


class PreviewConfig(BaseModel):
    strategy: Literal["fixed_url", "stdout_regex", "healthcheck"] = "fixed_url"
    url: str | None = None
    stdout_regex: str | None = None
    healthcheck_url: str | None = None


class PRConfig(BaseModel):
    base_branch: str = "main"
    draft: bool = True


class RepoConfig(BaseModel):
    name: str
    path: Path
    description: str = ""
    startup: StartupConfig
    preview: PreviewConfig
    pr: PRConfig = Field(default_factory=PRConfig)


class ReposConfig(BaseModel):
    repos: list[RepoConfig] = Field(default_factory=list)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    debug: bool = True
    database_url: str = "sqlite+aiosqlite:///./orchestrator.db"
    repos_config_path: Path = Field(default_factory=lambda: _default_repos_config_path())
    api_auth_required: bool = True
    dev_bearer_token: str = "orchestrator-dev-token"
    git_author_name: str = "Orchestrator Bot"
    git_author_email: str = "orchestrator-bot@example.com"
    gh_cli_bin: str = "gh"

    worker_image: str = "orchestrator-worker:latest"
    docker_network: str = "orchestrator_default"
    container_workspace: str = "/workspace"
    gh_token: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    agent_max_tokens: int = 4096
    agent_max_steps: int = 25


def _default_repos_config_path() -> Path:
    """Find repos.yaml by walking upward from this file, with a stable fallback."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "repos.yaml"
        if candidate.exists():
            return candidate
    return current.parents[2] / "repos.yaml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def load_repos_config() -> ReposConfig:
    settings = get_settings()
    config_path = settings.repos_config_path
    if not config_path.exists():
        return ReposConfig()

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return ReposConfig.model_validate(data)


def get_repo_config(repo_name: str) -> RepoConfig:
    for repo in load_repos_config().repos:
        if repo.name == repo_name:
            return repo
    raise KeyError(f"Unknown repo: {repo_name}")
