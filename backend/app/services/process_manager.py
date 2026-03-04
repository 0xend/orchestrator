from __future__ import annotations

import asyncio
import contextlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import RepoConfig
from app.security.path_guard import resolve_worktree_path


class ProcessStartupError(RuntimeError):
    """Raised when startup command or preview detection fails."""


@dataclass(slots=True)
class ManagedProcess:
    process: asyncio.subprocess.Process
    log_task: asyncio.Task[None] | None


class ProcessManager:
    def __init__(self) -> None:
        self._processes: dict[str, ManagedProcess] = {}

    async def start(self, task_id: str, repo: RepoConfig, worktree_path: str) -> str | None:
        if task_id in self._processes:
            raise ProcessStartupError(f"Process already running for task {task_id}")

        command = repo.startup.command
        if not command:
            raise ProcessStartupError(f"startup.command is empty for repo '{repo.name}'")

        root = Path(worktree_path).resolve()
        startup_cwd = resolve_worktree_path(root, repo.startup.cwd)
        env = os.environ.copy()
        env.update(repo.startup.env)

        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(startup_cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )

        managed = ManagedProcess(process=process, log_task=None)
        self._processes[task_id] = managed

        try:
            preview_url = await self._resolve_preview_url(repo, managed)
            if managed.log_task is None:
                managed.log_task = asyncio.create_task(self._drain_output(process))
            return preview_url
        except Exception:
            await self.stop(task_id)
            raise

    async def stop(self, task_id: str, *, timeout_seconds: int = 10) -> None:
        managed = self._processes.pop(task_id, None)
        if managed is None:
            return

        process = managed.process
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
            except TimeoutError:
                process.kill()
                await process.wait()

        if managed.log_task:
            managed.log_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await managed.log_task

    async def _resolve_preview_url(
        self,
        repo: RepoConfig,
        managed: ManagedProcess,
    ) -> str | None:
        strategy = repo.preview.strategy
        timeout_seconds = repo.startup.ready_timeout_seconds

        if strategy == "fixed_url":
            managed.log_task = asyncio.create_task(self._drain_output(managed.process))
            return repo.preview.url

        if strategy == "stdout_regex":
            regex = repo.preview.stdout_regex
            if not regex:
                raise ProcessStartupError("preview.stdout_regex is required for stdout_regex strategy")
            return await self._wait_for_stdout_match(managed.process, regex, timeout_seconds)

        if strategy == "healthcheck":
            url = repo.preview.healthcheck_url or repo.preview.url
            if not url:
                raise ProcessStartupError("preview.healthcheck_url or preview.url is required")
            managed.log_task = asyncio.create_task(self._drain_output(managed.process))
            await self._wait_for_healthcheck(managed.process, url, timeout_seconds)
            return repo.preview.url or url

        raise ProcessStartupError(f"Unsupported preview strategy: {strategy}")

    async def _wait_for_stdout_match(
        self,
        process: asyncio.subprocess.Process,
        regex: str,
        timeout_seconds: int,
    ) -> str:
        if process.stdout is None:
            raise ProcessStartupError("Process stdout is unavailable")

        pattern = re.compile(regex)
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            if process.returncode is not None:
                raise ProcessStartupError(f"Startup process exited with code {process.returncode}")

            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=1)
            except TimeoutError:
                continue

            if not line:
                continue

            text = line.decode("utf-8", errors="replace").strip()
            match = pattern.search(text)
            if match:
                return match.group(1) if match.groups() else match.group(0)

        raise ProcessStartupError("Timed out waiting for preview URL from stdout")

    async def _wait_for_healthcheck(
        self,
        process: asyncio.subprocess.Process,
        url: str,
        timeout_seconds: int,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        async with httpx.AsyncClient(timeout=3.0) as client:
            while time.monotonic() < deadline:
                if process.returncode is not None:
                    raise ProcessStartupError(f"Startup process exited with code {process.returncode}")

                try:
                    response = await client.get(url)
                    if response.status_code < 500:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(1)

        raise ProcessStartupError(f"Timed out waiting for healthcheck at {url}")

    async def _drain_output(self, process: asyncio.subprocess.Process) -> None:
        if process.stdout is None:
            return

        while True:
            line = await process.stdout.readline()
            if not line:
                return


process_manager = ProcessManager()
