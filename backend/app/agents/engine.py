from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app.agents.providers import LLMProvider
from app.agents.tools import ToolContext, execute_tool
from app.db.models import AgentSession

if TYPE_CHECKING:
    from app.services.container_manager import ContainerManager


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
    provider: LLMProvider | None = None,
    max_tokens: int = 4096,
    max_steps: int = 25,
    container_id: str | None = None,
    container_manager: ContainerManager | None = None,
    conversation_history: list[dict] | None = None,
) -> None:
    """Run a minimal LLM tool loop with streaming-compatible event callbacks."""
    worktree_root = Path(cwd).resolve()

    if not provider:
        await on_event(
            AgentEvent(
                event="token",
                data={
                    "text": "No LLM provider configured. Agent loop scaffold is running in dry mode."
                },
            )
        )
        return

    conversation = list(conversation_history or []) + [{"role": "user", "content": user_message}]

    for _ in range(max_steps):
        response = await provider.chat(
            system_prompt=session.system_prompt,
            messages=conversation,
            tools=tools,
            max_tokens=max_tokens,
        )

        conversation.append(response.raw_assistant_message)

        for text in response.text_blocks:
            await on_event(AgentEvent(event="token", data={"text": text}))

        if not response.tool_calls:
            return

        for tc in response.tool_calls:
            await on_event(
                AgentEvent(
                    event="tool_use",
                    data={"tool": tc.name, "input": tc.input, "id": tc.id},
                )
            )
            tool_result = await execute_tool(
                ToolContext(
                    worktree_root=worktree_root,
                    role=session.agent_role,
                    container_id=container_id,
                    container_manager=container_manager,
                ),
                tc.name,
                tc.input,
            )
            await on_event(
                AgentEvent(event="tool_result", data={"tool": tc.name, "output": tool_result})
            )
            conversation.append(provider.format_tool_result(tc.id, tool_result))

    await on_event(
        AgentEvent(
            event="status_change",
            data={"status": "failed", "reason": "agent loop reached max steps"},
        )
    )
