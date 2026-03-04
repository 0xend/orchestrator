from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


class PRCreationError(RuntimeError):
    """Raised when commit/push/PR creation fails."""


@dataclass(slots=True)
class PRCreationResult:
    pr_url: str
    branch_name: str
    commit_sha: str | None


class PRCreator:
    def create_or_update_pr(
        self,
        *,
        worktree_path: str,
        branch_name: str | None,
        base_branch: str,
        title: str,
        body: str,
        draft: bool,
    ) -> PRCreationResult:
        settings = get_settings()
        repo = Path(worktree_path).resolve()

        if not repo.exists():
            raise PRCreationError(f"Worktree path does not exist: {repo}")

        resolved_branch = branch_name or self._resolve_branch_name(repo)

        commit_sha = self._commit_changes_if_needed(
            repo,
            message=f"chore(orchestrator): complete task for {title}",
            author_name=settings.git_author_name,
            author_email=settings.git_author_email,
        )

        self._run(
            ["git", "push", "-u", "origin", resolved_branch],
            cwd=repo,
            error_prefix="Failed to push branch",
        )

        existing_url = self._find_existing_pr_url(repo, resolved_branch, settings.gh_cli_bin)
        if existing_url:
            return PRCreationResult(
                pr_url=existing_url,
                branch_name=resolved_branch,
                commit_sha=commit_sha,
            )

        command = [
            settings.gh_cli_bin,
            "pr",
            "create",
            "--base",
            base_branch,
            "--head",
            resolved_branch,
            "--title",
            title,
            "--body",
            body,
        ]
        if draft:
            command.append("--draft")

        result = self._run(command, cwd=repo, error_prefix="Failed to create pull request")
        pr_url = self._extract_pr_url(result.stdout) or self._extract_pr_url(result.stderr)
        if not pr_url:
            raise PRCreationError("PR created but URL was not found in gh output")

        return PRCreationResult(pr_url=pr_url, branch_name=resolved_branch, commit_sha=commit_sha)

    def _resolve_branch_name(self, repo: Path) -> str:
        result = self._run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo,
            error_prefix="Failed to resolve current branch",
        )
        branch_name = result.stdout.strip()
        if not branch_name:
            raise PRCreationError("Current branch is empty")
        return branch_name

    def _commit_changes_if_needed(
        self,
        repo: Path,
        *,
        message: str,
        author_name: str,
        author_email: str,
    ) -> str | None:
        status = self._run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            error_prefix="Failed to inspect repository status",
        )
        if not status.stdout.strip():
            return None

        self._run(["git", "add", "-A"], cwd=repo, error_prefix="Failed to stage changes")

        # Return code 1 means there are staged changes, 0 means nothing staged.
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(repo),
            check=False,
            capture_output=True,
            text=True,
        )
        if staged.returncode == 0:
            return None
        if staged.returncode not in {0, 1}:
            raise PRCreationError(staged.stderr.strip() or "Failed to inspect staged diff")

        commit_env = os.environ.copy()
        commit_env["GIT_AUTHOR_NAME"] = author_name
        commit_env["GIT_AUTHOR_EMAIL"] = author_email
        commit_env["GIT_COMMITTER_NAME"] = author_name
        commit_env["GIT_COMMITTER_EMAIL"] = author_email

        self._run(
            ["git", "commit", "-m", message],
            cwd=repo,
            env=commit_env,
            error_prefix="Failed to commit changes",
        )

        commit_sha = self._run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            error_prefix="Failed to get commit SHA",
        )
        return commit_sha.stdout.strip() or None

    def _find_existing_pr_url(self, repo: Path, branch_name: str, gh_bin: str) -> str | None:
        view = subprocess.run(
            [gh_bin, "pr", "view", branch_name, "--json", "url", "--jq", ".url"],
            cwd=str(repo),
            check=False,
            capture_output=True,
            text=True,
        )
        if view.returncode != 0:
            return None
        url = view.stdout.strip()
        return url or None

    @staticmethod
    def _extract_pr_url(output: str) -> str | None:
        match = re.search(r"https://github\.com/[^\s]+/pull/\d+", output)
        if not match:
            return None
        return match.group(0)

    @staticmethod
    def _run(
        command: list[str],
        *,
        cwd: Path,
        error_prefix: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
        except FileNotFoundError as exc:
            raise PRCreationError(f"Command not found: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or "Unknown command failure"
            raise PRCreationError(f"{error_prefix}: {detail}") from exc
        return result
