from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from app.db.models import Message, MessageRole


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(slots=True)
class ProviderResponse:
    text_blocks: list[str]
    tool_calls: list[ToolCall]
    raw_assistant_message: dict


class LLMProvider(Protocol):
    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
    ) -> ProviderResponse: ...

    def format_tool_result(self, tool_call_id: str, result: str) -> dict: ...

    def build_conversation(self, messages: list[Message]) -> list[dict]: ...


def _anthropic_conversation_from_messages(messages: list[Message]) -> list[dict]:
    history: list[dict] = []
    current_assistant_blocks: list[dict] = []

    for msg in messages:
        if msg.role == MessageRole.USER:
            if current_assistant_blocks:
                history.append({"role": "assistant", "content": current_assistant_blocks})
                current_assistant_blocks = []
            history.append({"role": "user", "content": msg.content.get("text", "")})

        elif msg.role == MessageRole.ASSISTANT:
            current_assistant_blocks.append(
                {"type": "text", "text": msg.content.get("text", "")}
            )

        elif msg.role == MessageRole.TOOL_USE:
            current_assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": msg.content.get("id", ""),
                    "name": msg.content.get("tool", ""),
                    "input": msg.content.get("input", {}),
                }
            )

        elif msg.role == MessageRole.TOOL_RESULT:
            if current_assistant_blocks:
                history.append({"role": "assistant", "content": current_assistant_blocks})
                current_assistant_blocks = []
            history.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.content.get("id", ""),
                            "content": msg.content.get("output", ""),
                        }
                    ],
                }
            )

    if current_assistant_blocks:
        history.append({"role": "assistant", "content": current_assistant_blocks})

    return history


def _openai_conversation_from_messages(messages: list[Message]) -> list[dict]:
    history: list[dict] = []
    current_tool_calls: list[dict] = []

    for msg in messages:
        if msg.role == MessageRole.USER:
            if current_tool_calls:
                history.append(
                    {"role": "assistant", "tool_calls": current_tool_calls, "content": None}
                )
                current_tool_calls = []
            history.append({"role": "user", "content": msg.content.get("text", "")})

        elif msg.role == MessageRole.ASSISTANT:
            history.append(
                {"role": "assistant", "content": msg.content.get("text", "")}
            )

        elif msg.role == MessageRole.TOOL_USE:
            import json

            current_tool_calls.append(
                {
                    "id": msg.content.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": msg.content.get("tool", ""),
                        "arguments": json.dumps(msg.content.get("input", {})),
                    },
                }
            )

        elif msg.role == MessageRole.TOOL_RESULT:
            if current_tool_calls:
                history.append(
                    {"role": "assistant", "tool_calls": current_tool_calls, "content": None}
                )
                current_tool_calls = []
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.content.get("id", ""),
                    "content": msg.content.get("output", ""),
                }
            )

    if current_tool_calls:
        history.append(
            {"role": "assistant", "tool_calls": current_tool_calls, "content": None}
        )

    return history


@dataclass
class AnthropicProvider:
    api_key: str
    model: str
    _client: AsyncAnthropic = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = AsyncAnthropic(api_key=self.api_key)

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
    ) -> ProviderResponse:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
            tools=tools,
        )

        text_blocks: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_content: list[dict] = []

        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
                raw_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input)))
                raw_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        return ProviderResponse(
            text_blocks=text_blocks,
            tool_calls=tool_calls,
            raw_assistant_message={"role": "assistant", "content": raw_content},
        )

    def format_tool_result(self, tool_call_id: str, result: str) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result,
                }
            ],
        }

    def build_conversation(self, messages: list[Message]) -> list[dict]:
        return _anthropic_conversation_from_messages(messages)


def _anthropic_tools_to_openai(tools: list[dict]) -> list[dict]:
    openai_tools: list[dict] = []
    for tool in tools:
        openai_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return openai_tools


@dataclass
class OpenAIProvider:
    api_key: str
    model: str
    base_url: str | None = None
    _client: AsyncOpenAI = field(init=False, repr=False)

    def __post_init__(self) -> None:
        kwargs: dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = AsyncOpenAI(**kwargs)

    async def chat(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
    ) -> ProviderResponse:
        openai_tools = _anthropic_tools_to_openai(tools)
        openai_messages: list[dict] = [{"role": "system", "content": system_prompt}] + messages

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": openai_messages,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        text_blocks: list[str] = []
        tool_calls: list[ToolCall] = []

        if choice.message.content:
            text_blocks.append(choice.message.content)

        if choice.message.tool_calls:
            import json

            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=json.loads(tc.function.arguments),
                    )
                )

        raw_msg: dict[str, Any] = {"role": "assistant", "content": choice.message.content}
        if choice.message.tool_calls:
            raw_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

        return ProviderResponse(
            text_blocks=text_blocks,
            tool_calls=tool_calls,
            raw_assistant_message=raw_msg,
        )

    def format_tool_result(self, tool_call_id: str, result: str) -> dict:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        }

    def build_conversation(self, messages: list[Message]) -> list[dict]:
        return _openai_conversation_from_messages(messages)


def create_provider(
    provider_name: str,
    api_key: str,
    model: str,
    base_url: str | None = None,
) -> LLMProvider:
    if provider_name == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model)
    if provider_name in ("openai", "openai_compatible"):
        return OpenAIProvider(api_key=api_key, model=model, base_url=base_url)
    raise ValueError(f"Unknown provider: {provider_name}")
