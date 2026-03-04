from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class CommandPolicyError(ValueError):
    """Raised when command execution violates policy."""


@dataclass(slots=True)
class CommandPolicy:
    allowed_commands: set[str] | None
    timeout_seconds: int = 30
    max_output_bytes: int = 100_000


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int


def _to_argv(command: str | Sequence[str]) -> list[str]:
    if isinstance(command, str):
        argv = shlex.split(command)
    else:
        argv = list(command)

    if not argv:
        raise CommandPolicyError("Command must not be empty")
    return argv


def _trim_output(data: bytes, limit: int) -> str:
    if len(data) <= limit:
        return data.decode("utf-8", errors="replace")
    trimmed = data[:limit]
    return trimmed.decode("utf-8", errors="replace") + "\n[output truncated]"


async def run_command(
    command: str | Sequence[str],
    cwd: Path,
    policy: CommandPolicy,
) -> CommandResult:
    argv = _to_argv(command)
    program = argv[0]

    if policy.allowed_commands is not None and program not in policy.allowed_commands:
        raise CommandPolicyError(f"Command '{program}' is not allowed")

    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    timed_out = False
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=policy.timeout_seconds)
    except TimeoutError:
        timed_out = True
        process.kill()
        stdout, stderr = await process.communicate()

    duration_ms = int((time.monotonic() - started) * 1000)
    return CommandResult(
        command=argv,
        cwd=str(cwd),
        exit_code=process.returncode if not timed_out else 124,
        stdout=_trim_output(stdout, policy.max_output_bytes),
        stderr=_trim_output(stderr, policy.max_output_bytes),
        timed_out=timed_out,
        duration_ms=duration_ms,
    )
