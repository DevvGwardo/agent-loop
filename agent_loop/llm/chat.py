"""Compatibility chat-client adapter for the coding harness."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from .providers import LLMToolCall, OpenAICompatibleProvider


@dataclass
class ToolCallRequest:
    """A model-requested tool invocation."""

    name: str
    args: dict[str, Any] = field(default_factory=dict)
    call_id: str | None = None


@dataclass
class ChatModelResponse:
    """Normalized chat-model response."""

    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    raw: dict[str, Any] | None = None


class ChatModelClient(Protocol):
    """Protocol for chat models that can request tool calls."""

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatModelResponse:
        ...


class OpenAICompatibleChatClient:
    """Small ``complete`` adapter around the provider registry's OpenAI wire client."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("AGENT_LOOP_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.provider = OpenAICompatibleProvider(
            name="openai-compatible",
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=timeout,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatModelResponse:
        if not self.api_key:
            raise RuntimeError(
                "Missing API key. Set OPENAI_API_KEY, AGENT_LOOP_API_KEY, "
                "or pass api_key to OpenAICompatibleChatClient."
            )

        system, neutral_messages = _split_system_messages(messages)
        response = self.provider.chat(
            model=self.model,
            system=system,
            messages=neutral_messages,
            tools=[_normalize_tool_schema(tool) for tool in tools],
        )
        return ChatModelResponse(
            content=response.text,
            tool_calls=[
                ToolCallRequest(name=call.name, args=call.args, call_id=call.id)
                for call in response.tool_calls
            ],
        )


def _split_system_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_parts: list[str] = []
    neutral: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            content = str(message.get("content") or "")
            if content:
                system_parts.append(content)
            continue

        item = dict(message)
        if role == "assistant" and item.get("tool_calls"):
            item["tool_calls"] = [_to_llm_tool_call(call) for call in item["tool_calls"]]
        neutral.append(item)
    return "\n\n".join(system_parts), neutral


def _normalize_tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    if tool.get("type") == "function":
        function = tool.get("function") or {}
        return {
            "name": function.get("name", ""),
            "description": function.get("description", ""),
            "parameters": function.get("parameters") or {"type": "object", "properties": {}},
        }
    return tool


def _to_llm_tool_call(call: Any) -> LLMToolCall:
    if isinstance(call, LLMToolCall):
        return call
    if isinstance(call, ToolCallRequest):
        return LLMToolCall(
            id=call.call_id or "",
            name=call.name,
            args=call.args,
        )
    if isinstance(call, dict):
        function = call.get("function") or {}
        raw_args = function.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (TypeError, ValueError, json.JSONDecodeError):
            args = {}
        return LLMToolCall(
            id=str(call.get("id") or call.get("call_id") or ""),
            name=str(function.get("name") or call.get("name") or ""),
            args=args,
        )
    return LLMToolCall(id="", name="", args={})


__all__ = [
    "ChatModelClient",
    "ChatModelResponse",
    "OpenAICompatibleChatClient",
    "ToolCallRequest",
]
