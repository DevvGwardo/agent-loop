"""Small model-client adapters for tool-calling agent loops."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


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
    """HTTP client for OpenAI-compatible chat completions with tools.

    It intentionally uses ``httpx`` instead of a provider SDK so this package
    stays lightweight and can target OpenAI, local gateways, or compatible
    hosted models with the same adapter.
    """

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

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]

        tool_calls: list[ToolCallRequest] = []
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            raw_args = function.get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"_raw_arguments": raw_args}
            tool_calls.append(
                ToolCallRequest(
                    name=function.get("name", ""),
                    args=args,
                    call_id=call.get("id"),
                )
            )

        return ChatModelResponse(
            content=message.get("content") or "",
            tool_calls=tool_calls,
            raw=data,
        )


__all__ = [
    "ChatModelClient",
    "ChatModelResponse",
    "OpenAICompatibleChatClient",
    "ToolCallRequest",
]
