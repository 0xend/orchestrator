from __future__ import annotations

import fnmatch
import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.db.models import AgentRole
from app.security.command_runner import CommandPolicy, run_command
from app.security.path_guard import resolve_worktree_path


@dataclass(slots=True)
class ToolContext:
    worktree_root: Path
    role: AgentRole


READ_ONLY_COMMANDS = {"git", "ls", "cat", "rg", "pwd", "find"}
FULL_COMMANDS = None


def _policy_for_role(role: AgentRole) -> CommandPolicy:
    if role in {AgentRole.PLANNER, AgentRole.PLAN_REVIEWER}:
        return CommandPolicy(allowed_commands=READ_ONLY_COMMANDS, timeout_seconds=20, max_output_bytes=64_000)
    return CommandPolicy(allowed_commands=FULL_COMMANDS, timeout_seconds=45, max_output_bytes=128_000)


async def read_file(ctx: ToolContext, path: str, offset: int = 0, limit: int | None = None) -> str:
    target = resolve_worktree_path(ctx.worktree_root, path)
    content = target.read_text(encoding="utf-8")
    if offset:
        content = content[offset:]
    if limit is not None:
        content = content[:limit]
    return content


async def write_file(ctx: ToolContext, path: str, content: str) -> dict:
    target = resolve_worktree_path(ctx.worktree_root, path, for_write=True)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write to avoid partially-written files.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as handle:
        handle.write(content)
        tmp_name = handle.name

    Path(tmp_name).replace(target)
    return {"path": str(target), "bytes": len(content.encode("utf-8"))}


async def edit_file(ctx: ToolContext, path: str, old_string: str, new_string: str) -> dict:
    target = resolve_worktree_path(ctx.worktree_root, path, for_write=True)
    existing = target.read_text(encoding="utf-8")
    if old_string not in existing:
        raise ValueError("old_string not found in file")

    updated = existing.replace(old_string, new_string, 1)
    return await write_file(ctx, path, updated)


async def glob(ctx: ToolContext, pattern: str, path: str | None = None) -> list[str]:
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
    base = resolve_worktree_path(ctx.worktree_root, path or ".")
    regex = re.compile(pattern)
    results: list[dict] = []

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
