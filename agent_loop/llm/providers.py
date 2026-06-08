"""LLM providers — a small registry of model backends to choose from.

Inspired by multi-provider tools like opencode: pick a provider by name
(``openai``, ``openrouter``, ``groq``, ``deepseek``, ``anthropic``, ``ollama``…)
plus a model id, and the :class:`~agent_loop.llm.agent.LLMAgent` drives the
tool-calling loop against it.

Two wire formats cover everything:

* :class:`OpenAICompatibleProvider` — the OpenAI ``/chat/completions`` shape,
  which most hosts speak (OpenAI, OpenRouter, Groq, DeepSeek, xAI, Mistral,
  Together, Fireworks, local Ollama). A provider is just a base URL + an API
  key env var.
* :class:`AnthropicProvider` — Anthropic's native ``/v1/messages`` shape.

Everything is implemented with ``httpx`` (already a dependency) so no extra
SDKs are required. :class:`ScriptedProvider` returns canned responses for
offline tests and demos.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx


# ─── Neutral request/response types ──────────────────────────────────


@dataclass
class LLMToolCall:
    """A tool call the model wants to make, in provider-neutral form."""

    id: str
    name: str
    args: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """One model turn: assistant text and/or a list of tool calls."""

    text: str = ""
    tool_calls: List[LLMToolCall] = field(default_factory=list)


# A neutral message is a dict with one of these shapes:
#   {"role": "user",      "content": str}
#   {"role": "assistant", "content": str, "tool_calls": [LLMToolCall, ...]}
#   {"role": "tool",      "tool_call_id": str, "name": str, "content": str}
Message = Dict[str, Any]
ToolDef = Dict[str, Any]  # {"name", "description", "parameters" (JSON schema)}


# ─── Base provider ───────────────────────────────────────────────────


class Provider:
    """Base class for model backends. Subclasses implement :meth:`chat`."""

    name: str = "provider"

    def chat(
        self,
        *,
        model: str,
        system: str,
        messages: List[Message],
        tools: List[ToolDef],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        raise NotImplementedError


# ─── OpenAI-compatible provider ──────────────────────────────────────


class OpenAICompatibleProvider(Provider):
    """Talks to any OpenAI ``/chat/completions``-compatible endpoint."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: float = 120.0,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def chat(
        self,
        *,
        model: str,
        system: str,
        messages: List[Message],
        tools: List[ToolDef],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": self._to_wire(system, messages),
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters") or {"type": "object", "properties": {}},
                    },
                }
                for t in tools
            ]

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        resp = self._client.post(
            f"{self.base_url}/chat/completions", json=payload, headers=headers
        )
        _raise_for_status(resp, self.name)
        data = resp.json()
        return self._parse(data)

    @staticmethod
    def _to_wire(system: str, messages: List[Message]) -> List[Dict[str, Any]]:
        wire: List[Dict[str, Any]] = []
        if system:
            wire.append({"role": "system", "content": system})
        for m in messages:
            role = m["role"]
            if role == "assistant" and m.get("tool_calls"):
                wire.append(
                    {
                        "role": "assistant",
                        "content": m.get("content") or None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                            }
                            for tc in m["tool_calls"]
                        ],
                    }
                )
            elif role == "tool":
                wire.append(
                    {
                        "role": "tool",
                        "tool_call_id": m["tool_call_id"],
                        "content": m["content"],
                    }
                )
            else:
                wire.append({"role": role, "content": m.get("content", "")})
        return wire

    @staticmethod
    def _parse(data: Dict[str, Any]) -> LLMResponse:
        msg = data["choices"][0]["message"]
        text = msg.get("content") or ""
        tool_calls: List[LLMToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            try:
                parsed_args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                parsed_args = {}
            tool_calls.append(LLMToolCall(id=tc.get("id", ""), name=fn.get("name", ""), args=parsed_args))
        return LLMResponse(text=text, tool_calls=tool_calls)


# ─── Anthropic provider ──────────────────────────────────────────────


class AnthropicProvider(Provider):
    """Talks to Anthropic's native ``/v1/messages`` endpoint."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.anthropic.com/v1",
        version: str = "2023-06-01",
        client: Optional[httpx.Client] = None,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.version = version
        self._client = client or httpx.Client(timeout=timeout)

    def chat(
        self,
        *,
        model: str,
        system: str,
        messages: List[Message],
        tools: List[ToolDef],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": self._to_wire(messages),
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters") or {"type": "object", "properties": {}},
                }
                for t in tools
            ]

        headers = {
            "Content-Type": "application/json",
            "anthropic-version": self.version,
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key

        resp = self._client.post(f"{self.base_url}/messages", json=payload, headers=headers)
        _raise_for_status(resp, self.name)
        return self._parse(resp.json())

    @staticmethod
    def _to_wire(messages: List[Message]) -> List[Dict[str, Any]]:
        """Translate neutral messages, coalescing consecutive tool results.

        Anthropic requires all tool results from one assistant turn to live in
        a single ``user`` message, so adjacent neutral ``tool`` messages are
        merged into one block list.
        """
        wire: List[Dict[str, Any]] = []
        pending_results: List[Dict[str, Any]] = []

        def flush_results() -> None:
            if pending_results:
                wire.append({"role": "user", "content": list(pending_results)})
                pending_results.clear()

        for m in messages:
            role = m["role"]
            if role == "tool":
                pending_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": m["tool_call_id"],
                        "content": m["content"],
                    }
                )
                continue

            flush_results()
            if role == "assistant" and m.get("tool_calls"):
                blocks: List[Dict[str, Any]] = []
                if m.get("content"):
                    blocks.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.args})
                wire.append({"role": "assistant", "content": blocks})
            else:
                wire.append({"role": role, "content": m.get("content", "")})

        flush_results()
        return wire

    @staticmethod
    def _parse(data: Dict[str, Any]) -> LLMResponse:
        text_parts: List[str] = []
        tool_calls: List[LLMToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    LLMToolCall(id=block.get("id", ""), name=block.get("name", ""), args=block.get("input", {}))
                )
        return LLMResponse(text="".join(text_parts), tool_calls=tool_calls)


# ─── Scripted provider (offline tests & demos) ───────────────────────


class ScriptedProvider(Provider):
    """Returns pre-baked responses in order. No network, no API key.

    Useful for tests and for running the example without credentials.
    """

    name = "scripted"

    def __init__(self, responses: List[LLMResponse]) -> None:
        self._responses = list(responses)
        self._i = 0
        self.calls: List[Dict[str, Any]] = []  # records each chat() invocation

    def chat(
        self,
        *,
        model: str,
        system: str,
        messages: List[Message],
        tools: List[ToolDef],
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.calls.append({"model": model, "messages": list(messages), "tools": tools})
        if self._i >= len(self._responses):
            return LLMResponse(text="[scripted: no further steps]")
        resp = self._responses[self._i]
        self._i += 1
        return resp


# ─── Registry ────────────────────────────────────────────────────────


# name -> (base_url, api_key_env_var)
_OPENAI_COMPATIBLE: Dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
    "ollama": ("http://localhost:11434/v1", "OLLAMA_API_KEY"),  # local; key optional
}


def list_providers() -> List[str]:
    """Return all provider names that can be passed to :func:`get_provider`."""
    return sorted([*_OPENAI_COMPATIBLE, "anthropic", "scripted"])


def get_provider(name: str, *, api_key: Optional[str] = None, **kwargs: Any) -> Provider:
    """Build a :class:`Provider` by name.

    The API key is taken from *api_key* if given, else from the provider's
    environment variable. ``ollama`` (local) does not require a key.
    """
    key = name.lower()

    if key == "anthropic":
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Anthropic provider requires ANTHROPIC_API_KEY (or api_key=).")
        return AnthropicProvider(api_key=api_key, **kwargs)

    if key in _OPENAI_COMPATIBLE:
        base_url, env_var = _OPENAI_COMPATIBLE[key]
        api_key = api_key or os.environ.get(env_var)
        if not api_key and key != "ollama":
            raise RuntimeError(f"Provider '{key}' requires {env_var} (or api_key=).")
        return OpenAICompatibleProvider(name=key, base_url=base_url, api_key=api_key, **kwargs)

    raise ValueError(f"Unknown provider '{name}'. Choose one of: {', '.join(list_providers())}")


def _raise_for_status(resp: httpx.Response, provider: str) -> None:
    if resp.status_code >= 400:
        body = resp.text[:500]
        raise RuntimeError(f"{provider} API error {resp.status_code}: {body}")


__all__ = [
    "LLMToolCall",
    "LLMResponse",
    "Provider",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "ScriptedProvider",
    "get_provider",
    "list_providers",
]
