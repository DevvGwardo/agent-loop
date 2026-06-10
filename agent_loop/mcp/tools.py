"""Dynamic MCP tool executors registered on the agent harness."""

from __future__ import annotations

from typing import Any

from agent_loop.agent import Agent
from agent_loop.mcp.cache import McpSnapshotCache, McpToolDefinition
from agent_loop.mcp.client import McpClient
from agent_loop.tools.base import ToolExecutor

MCP_PREFIX = "mcp__"


def mcp_executor_name(server_name: str, tool_name: str) -> str:
    """Build a stable, collision-resistant executor name for an MCP tool."""
    safe_server = server_name.replace("__", "_")
    safe_tool = tool_name.replace("__", "_")
    return f"{MCP_PREFIX}{safe_server}__{safe_tool}"


def parse_mcp_executor_name(name: str) -> tuple[str, str] | None:
    if not name.startswith(MCP_PREFIX):
        return None
    body = name.removeprefix(MCP_PREFIX)
    if "__" not in body:
        return None
    server, tool = body.split("__", 1)
    return server, tool


class McpToolExecutor(ToolExecutor):
    """Proxy executor that forwards a single MCP tool call to an :class:`McpClient`."""

    def __init__(self, definition: McpToolDefinition, client: McpClient) -> None:
        self._definition = definition
        self._client = client

    @property
    def server_name(self) -> str:
        return self._definition.server_name

    @property
    def mcp_tool_name(self) -> str:
        return self._definition.tool_name

    @property
    def name(self) -> str:
        return mcp_executor_name(self._definition.server_name, self._definition.tool_name)

    @property
    def description(self) -> str:
        base = self._definition.description or f"MCP tool {self._definition.tool_name}"
        return f"[{self._definition.server_name}] {base}"

    def args_schema(self) -> dict[str, Any]:
        schema = self._definition.input_schema
        if schema:
            return schema
        return {"type": "object", "properties": {}, "additionalProperties": True}

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        del context
        return self._client.call_tool(
            self._definition.server_name,
            self._definition.tool_name,
            args or {},
        )


def sync_mcp_tools(
    agent: Agent,
    cache: McpSnapshotCache,
    client: McpClient,
) -> list[McpToolExecutor]:
    """Replace MCP executors on *agent* with the current cache contents."""
    for name in list(agent.tool_names):
        if name.startswith(MCP_PREFIX):
            agent.unregister_tool(name)

    executors: list[McpToolExecutor] = []
    for definition in cache.tools:
        executor = McpToolExecutor(definition, client)
        agent.register_tool(executor)
        executors.append(executor)
    return executors


def format_mcp_status(cache: McpSnapshotCache, instructions: str = "") -> str:
    """Human-readable MCP summary for slash commands."""
    if not cache.tools:
        return "No MCP tools configured. Add ~/.agent-loop/mcp.json or set AGENT_LOOP_MCP_URL."
    lines = [f"MCP generation: {cache.generation}", f"Tools ({len(cache.tools)}):"]
    for tool in cache.tools:
        lines.append(f"- {mcp_executor_name(tool.server_name, tool.tool_name)}")
    if instructions.strip():
        lines.extend(["", "Instructions:", instructions.strip()])
    return "\n".join(lines)


__all__ = [
    "MCP_PREFIX",
    "McpToolExecutor",
    "format_mcp_status",
    "mcp_executor_name",
    "parse_mcp_executor_name",
    "sync_mcp_tools",
]
