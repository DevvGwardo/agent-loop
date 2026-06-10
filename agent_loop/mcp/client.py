"""MCP client adapters for harness tool execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Protocol

import httpx

from .cache import McpSnapshotCache, McpToolDefinition

McpHandler = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class McpClient(Protocol):
    """Protocol for invoking tools on MCP servers."""

    def call_tool(self, server_name: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        ...


class CallableMcpClient:
    """Routes MCP tool calls through registered Python handlers."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], McpHandler] = {}

    def register(
        self,
        server_name: str,
        tool_name: str,
        handler: McpHandler,
    ) -> None:
        self._handlers[(server_name, tool_name)] = handler

    def call_tool(self, server_name: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = self._handlers.get((server_name, tool_name))
        if handler is None:
            return {
                "success": False,
                "error": f"No MCP handler registered for {server_name}:{tool_name}",
            }
        try:
            result = handler(server_name, tool_name, args)
            if "success" not in result:
                result = {"success": True, **result}
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class HttpMcpClient:
    """POST tool invocations to a local MCP bridge HTTP endpoint."""

    def __init__(self, base_url: str, *, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def call_tool(self, server_name: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/call",
            json={"server": server_name, "tool": tool_name, "arguments": args},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "success" not in data:
            return {"success": True, **data}
        return data


def load_mcp_config(
    path: str | Path | None = None,
) -> tuple[McpSnapshotCache, str, CallableMcpClient | HttpMcpClient | None]:
    """Load MCP tool definitions from ``~/.agent-loop/mcp.json`` or *path*.

    Returns ``(cache, instructions, client_or_none)``. When no HTTP bridge URL
    is configured the client is a :class:`CallableMcpClient` (handlers must be
    registered separately).
    """
    config_path = Path(
        path or os.environ.get("AGENT_LOOP_MCP_CONFIG", Path.home() / ".agent-loop" / "mcp.json"),
    )
    cache = McpSnapshotCache()
    instructions = ""

    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        instructions = str(raw.get("instructions") or "")
        tools = [
            McpToolDefinition(
                server_name=item["server_name"],
                tool_name=item["tool_name"],
                description=item.get("description", ""),
                input_schema=item.get("input_schema") or {"type": "object", "properties": {}},
            )
            for item in raw.get("tools", [])
            if item.get("server_name") and item.get("tool_name")
        ]
        if tools:
            cache.sync(tools)

    bridge_url = os.environ.get("AGENT_LOOP_MCP_URL")
    if bridge_url:
        return cache, instructions, HttpMcpClient(bridge_url)
    return cache, instructions, CallableMcpClient() if cache.tools else None


__all__ = [
    "CallableMcpClient",
    "HttpMcpClient",
    "McpClient",
    "McpHandler",
    "load_mcp_config",
]
