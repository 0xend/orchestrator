from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(RuntimeError):
    """Raised when worktree operations fail."""


@dataclass(slots=True)
class WorktreeInfo:
    branch_name: str
    worktree_path: str


class WorktreeManager:
    def create_worktree(self, repo_path: str, task_id: str, *, base_branch: str = "main") -> WorktreeInfo:
        repo = Path(repo_path).resolve()
        if not repo.exists():
            raise WorktreeError(f"Repository does not exist: {repo}")

        branch_name = f"task/{task_id}"
        worktree_path = repo / ".worktrees" / f"task-{task_id}"
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        if worktree_path.exists():
            return WorktreeInfo(branch_name=branch_name, worktree_path=str(worktree_path))

        branch_exists = self._branch_exists(repo, branch_name)
        cmd = ["git", "-C", str(repo), "worktree", "add"]
        if branch_exists:
            cmd.extend([str(worktree_path), branch_name])
        else:
            cmd.extend(["-b", branch_name, str(worktree_path), base_branch])

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise WorktreeError(exc.stderr.strip() or "Failed to create worktree") from exc

        return WorktreeInfo(branch_name=branch_name, worktree_path=str(worktree_path))

    def remove_worktree(self, worktree_path: str) -> None:
        path = Path(worktree_path).resolve()
        if not path.exists():
            return

        try:
            repo_root = self._repo_root_from_worktree(path)
        except subprocess.CalledProcessError as exc:
            raise WorktreeError(exc.stderr.strip() or "Failed to determine repository root") from exc
        try:
            subprocess.run(
                ["git", "-C", str(repo_root), "worktree", "remove", str(path), "--force"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise WorktreeError(exc.stderr.strip() or "Failed to remove worktree") from exc

    def get_diff(self, worktree_path: str) -> str:
        path = Path(worktree_path).resolve()
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "diff", "--no-color"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise WorktreeError(exc.stderr.strip() or "Failed to get diff") from exc
        return result.stdout

    @staticmethod
    def _branch_exists(repo_path: Path, branch_name: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "show-ref", "--verify", f"refs/heads/{branch_name}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    @staticmethod
    def _repo_root_from_worktree(worktree_path: Path) -> Path:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(worktree_path),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        git_common_dir = Path(result.stdout.strip())
        return git_common_dir.parent
