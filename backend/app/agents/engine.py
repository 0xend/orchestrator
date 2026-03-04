from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from anthropic import AsyncAnthropic

from app.agents.tools import ToolContext, execute_tool
from app.db.models import AgentSession


@dataclass(slots=True)
class AgentEvent:
    event: str
    data: dict


async def run_agent_loop(
    session: AgentSession,
    user_message: str,
    tools: list[dict],
    on_event: Callable[[AgentEvent], Awaitable[None]],
    cwd: str,
    *,
    api_key: str | None = None,
    model: str = "claude-3-7-sonnet-latest",
    max_steps: int = 12,
) -> None:
    """Run a minimal Claude tool loop with streaming-compatible event callbacks."""
    worktree_root = Path(cwd).resolve()

    if not api_key:
        await on_event(
            AgentEvent(
                event="token",
                data={
                    "text": "ANTHROPIC_API_KEY is not configured. Agent loop scaffold is running in dry mode."
                },
            )
        )
        return

    client = AsyncAnthropic(api_key=api_key)
    conversation: list[dict] = [{"role": "user", "content": user_message}]

    for _ in range(max_steps):
        response = await client.messages.create(
            model=model,
            max_tokens=1200,
            system=session.system_prompt,
            messages=conversation,
            tools=tools,
        )

        assistant_content: list[dict] = []
        issued_tool = False

        for block in response.content:
            if block.type == "text":
                await on_event(AgentEvent(event="token", data={"text": block.text}))
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                issued_tool = True
                await on_event(
                    AgentEvent(
                        event="tool_use",
                        data={"tool": block.name, "input": block.input, "id": block.id},
                    )
                )
                tool_result = await execute_tool(
                    ToolContext(worktree_root=worktree_root, role=session.agent_role),
                    block.name,
                    dict(block.input),
                )
                await on_event(
                    AgentEvent(event="tool_result", data={"tool": block.name, "output": tool_result})
                )

                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )
                conversation.append({"role": "assistant", "content": assistant_content})
                conversation.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": tool_result,
                            }
                        ],
                    }
                )
                break

        if not issued_tool:
            conversation.append({"role": "assistant", "content": assistant_content})
            return

    await on_event(
        AgentEvent(
            event="status_change",
            data={"status": "failed", "reason": "agent loop reached max steps"},
        )
    )
