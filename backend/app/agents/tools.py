from __future__ import annotations

import fnmatch
import json
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from app.db.models import AgentRole
from app.security.command_runner import CommandPolicy, run_command
from app.security.path_guard import resolve_worktree_path

if TYPE_CHECKING:
    from app.services.container_manager import ContainerManager


@dataclass(slots=True)
class ToolContext:
    worktree_root: Path
    role: AgentRole
    container_id: str | None = field(default=None)
    container_manager: ContainerManager | None = field(default=None)


READ_ONLY_COMMANDS = {"git", "ls", "cat", "rg", "pwd", "find"}
FULL_COMMANDS = None


def _policy_for_role(role: AgentRole) -> CommandPolicy:
    if role in {AgentRole.PLANNER, AgentRole.PLAN_REVIEWER}:
        return CommandPolicy(allowed_commands=READ_ONLY_COMMANDS, timeout_seconds=20, max_output_bytes=64_000)
    return CommandPolicy(allowed_commands=FULL_COMMANDS, timeout_seconds=45, max_output_bytes=128_000)


async def read_file(ctx: ToolContext, path: str, offset: int = 0, limit: int | None = None) -> str:
    if ctx.container_id and ctx.container_manager:
        full_path = f"{ctx.worktree_root}/{path}" if not path.startswith("/") else path
        content = ctx.container_manager.read_file_in_container(ctx.container_id, full_path)
        if offset:
            content = content[offset:]
        if limit is not None:
            content = content[:limit]
        return content

    target = resolve_worktree_path(ctx.worktree_root, path)
    content = target.read_text(encoding="utf-8")
    if offset:
        content = content[offset:]
    if limit is not None:
        content = content[:limit]
    return content


async def write_file(ctx: ToolContext, path: str, content: str) -> dict:
    if ctx.container_id and ctx.container_manager:
        full_path = f"{ctx.worktree_root}/{path}" if not path.startswith("/") else path
        ctx.container_manager.write_file_in_container(ctx.container_id, full_path, content)
        return {"path": full_path, "bytes": len(content.encode("utf-8"))}

    target = resolve_worktree_path(ctx.worktree_root, path, for_write=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write to avoid partially-written files.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        handle.write(content)
        tmp_name = handle.name

    Path(tmp_name).replace(target)
    return {"path": str(target), "bytes": len(content.encode("utf-8"))}


async def edit_file(ctx: ToolContext, path: str, old_string: str, new_string: str) -> dict:
    if ctx.container_id and ctx.container_manager:
        full_path = f"{ctx.worktree_root}/{path}" if not path.startswith("/") else path
        existing = ctx.container_manager.read_file_in_container(ctx.container_id, full_path)
        if old_string not in existing:
            raise ValueError("old_string not found in file")
        updated = existing.replace(old_string, new_string, 1)
        ctx.container_manager.write_file_in_container(ctx.container_id, full_path, updated)
        return {"path": full_path, "bytes": len(updated.encode("utf-8"))}

    target = resolve_worktree_path(ctx.worktree_root, path, for_write=True)
    existing = target.read_text(encoding="utf-8")
    if old_string not in existing:
        raise ValueError("old_string not found in file")

    updated = existing.replace(old_string, new_string, 1)
    return await write_file(ctx, path, updated)


async def glob(ctx: ToolContext, pattern: str, path: str | None = None) -> list[str]:
    if ctx.container_id and ctx.container_manager:
        search_path = f"{ctx.worktree_root}/{path}" if path else str(ctx.worktree_root)
        result = ctx.container_manager.exec_in_container(
            ctx.container_id,
            ["find", search_path, "-type", "f", "-name", pattern],
            workdir=str(ctx.worktree_root),
        )
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        root_prefix = str(ctx.worktree_root).rstrip("/") + "/"
        return sorted(line.removeprefix(root_prefix) for line in lines)

    base = resolve_worktree_path(ctx.worktree_root, path or ".")
    matches: list[str] = []
    for candidate in base.rglob("*"):
        rel = candidate.relative_to(ctx.worktree_root)
        if fnmatch.fnmatch(str(rel), pattern):
            matches.append(str(rel))
    return sorted(matches)


async def grep(
    ctx: ToolContext,
    pattern: str,
    path: str | None = None,
    glob_pattern: str | None = None,
) -> list[dict]:
    if ctx.container_id and ctx.container_manager:
        search_path = f"{ctx.worktree_root}/{path}" if path else str(ctx.worktree_root)
        cmd = ["rg", "--json", pattern, search_path]
        if glob_pattern:
            cmd.extend(["--glob", glob_pattern])
        result = ctx.container_manager.exec_in_container(
            ctx.container_id, cmd, workdir=str(ctx.worktree_root)
        )
        results: list[dict] = []
        root_prefix = str(ctx.worktree_root).rstrip("/") + "/"
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "match":
                data = entry["data"]
                file_path = data["path"]["text"].removeprefix(root_prefix)
                results.append({
                    "path": file_path,
                    "line": data["line_number"],
                    "text": data["lines"]["text"].rstrip("\n"),
                })
        return results

    base = resolve_worktree_path(ctx.worktree_root, path or ".")
    regex = re.compile(pattern)
    results = []

    for candidate in base.rglob("*"):
        if not candidate.is_file():
            continue
        rel = candidate.relative_to(ctx.worktree_root)
        if glob_pattern and not fnmatch.fnmatch(str(rel), glob_pattern):
            continue

        try:
            lines = candidate.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        for index, line in enumerate(lines, start=1):
            if regex.search(line):
                results.append({"path": str(rel), "line": index, "text": line})
    return results


async def bash(ctx: ToolContext, command: str) -> dict:
    policy = _policy_for_role(ctx.role)

    if ctx.container_id and ctx.container_manager:
        # Validate command policy on backend side before proxying
        import shlex

        argv = shlex.split(command)
        if argv and policy.allowed_commands is not None and argv[0] not in policy.allowed_commands:
            from app.security.command_runner import CommandPolicyError

            raise CommandPolicyError(f"Command '{argv[0]}' is not allowed")

        result = ctx.container_manager.exec_in_container(
            ctx.container_id,
            ["sh", "-c", command],
            workdir=str(ctx.worktree_root),
            timeout=policy.timeout_seconds,
        )
        return {
            "command": command,
            "cwd": str(ctx.worktree_root),
            "exit_code": result.exit_code,
            "stdout": result.stdout[:policy.max_output_bytes],
            "stderr": result.stderr[:policy.max_output_bytes],
            "timed_out": False,
            "duration_ms": 0,
        }

    result = await run_command(command=command, cwd=ctx.worktree_root, policy=policy)
    return {
        "command": result.command,
        "cwd": result.cwd,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
    }


async def execute_tool(ctx: ToolContext, tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        result = await read_file(ctx, **tool_input)
    elif tool_name == "write_file":
        result = await write_file(ctx, **tool_input)
    elif tool_name == "edit_file":
        result = await edit_file(ctx, **tool_input)
    elif tool_name == "glob":
        result = await glob(ctx, **tool_input)
    elif tool_name == "grep":
        normalized_input = dict(tool_input)
        if "glob" in normalized_input:
            normalized_input["glob_pattern"] = normalized_input.pop("glob")
        result = await grep(ctx, **normalized_input)
    elif tool_name == "bash":
        result = await bash(ctx, **tool_input)
    else:
        raise ValueError(f"Unsupported tool: {tool_name}")

    return json.dumps(result, ensure_ascii=False)
