from __future__ import annotations

from pathlib import Path


class PathSecurityError(ValueError):
    """Raised when a user-supplied path escapes the worktree root."""


def _ensure_within_root(candidate: Path, root: Path) -> None:
    if not candidate.is_relative_to(root):
        raise PathSecurityError(f"Path escapes worktree: {candidate}")


def resolve_worktree_path(root: Path, user_path: str, *, for_write: bool = False) -> Path:
    """Resolve and validate that a path remains inside the worktree root."""
    resolved_root = root.resolve(strict=True)

    raw = Path(user_path)
    if raw.is_absolute():
        candidate = raw
    else:
        candidate = resolved_root / raw

    candidate = candidate.resolve(strict=False)
    _ensure_within_root(candidate, resolved_root)

    if candidate.exists():
        real_target = candidate.resolve(strict=True)
        _ensure_within_root(real_target, resolved_root)
    elif for_write:
        parent = candidate.parent.resolve(strict=True)
        _ensure_within_root(parent, resolved_root)

    relative = candidate.relative_to(resolved_root)
    if relative.parts and relative.parts[0] == ".git":
        raise PathSecurityError("Access to .git internals is not allowed")

    return candidate
