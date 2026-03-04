from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import load_repos_config
from app.security.auth import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/api/repos", tags=["repos"])


@router.get("")
async def list_repositories(_: AuthenticatedUser = Depends(get_current_user)) -> list[dict]:
    repos = load_repos_config().repos
    return [
        {
            "name": repo.name,
            "path": str(repo.path),
            "description": repo.description,
            "startup": repo.startup.model_dump(),
            "preview": repo.preview.model_dump(),
        }
        for repo in repos
    ]
