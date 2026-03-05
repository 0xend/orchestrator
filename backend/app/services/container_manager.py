from __future__ import annotations

import logging
import shlex
from dataclasses import dataclass

from python_on_whales import DockerClient, exceptions as docker_exceptions

from app.config import get_settings

logger = logging.getLogger(__name__)


class ContainerError(RuntimeError):
    """Raised when container operations fail."""


@dataclass(slots=True)
class ContainerInfo:
    container_id: str
    branch_name: str
    workspace_path: str


@dataclass(slots=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str


class ContainerManager:
    def __init__(self) -> None:
        self._docker = DockerClient()

    def create_task_container(
        self,
        task_id: str,
        github_url: str,
        *,
        base_branch: str = "main",
        github_token: str | None = None,
    ) -> ContainerInfo:
        settings = get_settings()
        container_name = f"orchestrator-task-{task_id[:12]}"
        workspace = settings.container_workspace
        branch_name = f"task/{task_id}"

        # Idempotent: if container already exists, return its info
        try:
            existing = self._docker.container.inspect(container_name)
            if self._is_task_workspace_ready(existing.id, workspace, branch_name):
                return ContainerInfo(
                    container_id=existing.id,
                    branch_name=branch_name,
                    workspace_path=workspace,
                )
            logger.warning(
                "Existing container %s is not ready for task %s; recreating",
                existing.id,
                task_id,
            )
            self.destroy_container(existing.id)
        except docker_exceptions.NoSuchContainer:
            pass
        except Exception as exc:
            raise ContainerError(f"Failed to inspect existing container: {exc}") from exc

        env_vars: dict[str, str] = {
            "GIT_AUTHOR_NAME": settings.git_author_name,
            "GIT_AUTHOR_EMAIL": settings.git_author_email,
            "GIT_COMMITTER_NAME": settings.git_author_name,
            "GIT_COMMITTER_EMAIL": settings.git_author_email,
        }
        if github_token:
            env_vars["GH_TOKEN"] = github_token

        try:
            container = self._docker.run(
                settings.worker_image,
                name=container_name,
                detach=True,
                envs=env_vars,
                networks=[settings.docker_network],
                labels={
                    "orchestrator.managed": "true",
                    "orchestrator.network": settings.docker_network,
                    "orchestrator.task_id": task_id,
                },
            )
        except Exception as exc:
            raise ContainerError(f"Failed to create container: {exc}") from exc

        container_id = container.id if hasattr(container, "id") else str(container)

        try:
            clone_with_branch = self._build_clone_command(
                github_url=github_url,
                workspace=workspace,
                base_branch=base_branch,
                github_token=github_token,
            )
            clone_default = self._build_clone_command(
                github_url=github_url,
                workspace=workspace,
                base_branch=None,
                github_token=github_token,
            )
            try:
                self._exec(container_id, clone_with_branch)
            except ContainerError:
                # Retry without --branch for repos where base_branch doesn't exist.
                # Use sh -c to avoid issues if workspace is also the container WORKDIR.
                self._exec(
                    container_id,
                    ["sh", "-c", f"rm -rf {shlex.quote(workspace)} && mkdir -p {shlex.quote(workspace)}"],
                    workdir="/",
                )
                self._exec(container_id, clone_default, workdir="/")

            # Create task branch
            self._exec(
                container_id,
                ["git", "checkout", "-b", branch_name],
                workdir=workspace,
            )
        except Exception:
            self.destroy_container(container_id)
            raise

        return ContainerInfo(
            container_id=container_id,
            branch_name=branch_name,
            workspace_path=workspace,
        )

    def exec_in_container(
        self,
        container_id: str,
        command: list[str],
        *,
        workdir: str | None = None,
        timeout: int = 60,
    ) -> ExecResult:
        return self._exec(container_id, command, workdir=workdir, timeout=timeout)

    def read_file_in_container(self, container_id: str, path: str) -> str:
        result = self._exec(container_id, ["cat", path])
        return result.stdout

    def write_file_in_container(self, container_id: str, path: str, content: str) -> None:
        quoted_path = shlex.quote(path)
        quoted_dir = shlex.quote(path.rsplit("/", 1)[0] if "/" in path else ".")
        self._exec(
            container_id,
            ["sh", "-c", f"mkdir -p {quoted_dir} && cat > {quoted_path}"],
            stdin=content,
        )

    def destroy_container(self, container_id: str) -> None:
        try:
            self._docker.container.stop(container_id, time=10)
        except docker_exceptions.NoSuchContainer:
            return
        except Exception:
            logger.warning("Failed to stop container %s, forcing removal", container_id)

        try:
            self._docker.container.remove(container_id, force=True)
        except docker_exceptions.NoSuchContainer:
            pass
        except Exception as exc:
            logger.error("Failed to remove container %s: %s", container_id, exc)

    def cleanup_orphaned_containers(self) -> None:
        settings = get_settings()
        try:
            containers = self._docker.container.list(
                all=True,
                filters=[
                    ("label", "orchestrator.managed=true"),
                    ("label", f"orchestrator.network={settings.docker_network}"),
                ],
            )
            for container in containers:
                logger.info("Cleaning up orphaned container: %s", container.name)
                self.destroy_container(container.id)
        except Exception as exc:
            logger.warning("Failed to list containers for cleanup: %s", exc)

    def _build_clone_command(
        self,
        *,
        github_url: str,
        workspace: str,
        base_branch: str | None,
        github_token: str | None,
    ) -> list[str]:
        cmd = ["git"]
        if github_token and github_url.startswith("https://github.com/"):
            credential_helper = (
                "credential.helper=!f() { test \"$1\" = get && "
                "echo username=x-access-token && echo password=$GH_TOKEN; }; f"
            )
            cmd.extend(["-c", credential_helper])

        cmd.append("clone")
        if base_branch:
            cmd.extend(["--branch", base_branch])
        cmd.extend([github_url, workspace])
        return cmd

    def _is_task_workspace_ready(
        self, container_id: str, workspace: str, branch_name: str
    ) -> bool:
        try:
            inside = self._exec(
                container_id,
                ["git", "rev-parse", "--is-inside-work-tree"],
                workdir=workspace,
            )
            if inside.stdout.strip() != "true":
                return False

            branch = self._exec(
                container_id,
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                workdir=workspace,
            )
            return branch.stdout.strip() == branch_name
        except ContainerError:
            return False

    def _exec(
        self,
        container_id: str,
        command: list[str],
        *,
        workdir: str | None = None,
        timeout: int = 60,
        stdin: str | None = None,
    ) -> ExecResult:
        try:
            kwargs: dict = {"tty": False}
            if workdir:
                kwargs["workdir"] = workdir
            if stdin is not None:
                # Write content via docker exec with stdin
                import subprocess

                exec_cmd = ["docker", "exec", "-i"]
                if workdir:
                    exec_cmd.extend(["-w", workdir])
                exec_cmd.append(container_id)
                exec_cmd.extend(command)
                proc = subprocess.run(
                    exec_cmd,
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                if proc.returncode != 0:
                    raise ContainerError(
                        f"Command failed (exit {proc.returncode}): {proc.stderr}"
                    )
                return ExecResult(
                    exit_code=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                )

            output = self._docker.execute(
                container_id,
                command,
                **kwargs,
            )
            stdout = output if isinstance(output, str) else str(output)
            return ExecResult(exit_code=0, stdout=stdout, stderr="")
        except docker_exceptions.DockerException as exc:
            raise ContainerError(f"Container exec failed: {exc}") from exc
        except Exception as exc:
            if isinstance(exc, ContainerError):
                raise
            raise ContainerError(f"Container exec failed: {exc}") from exc
