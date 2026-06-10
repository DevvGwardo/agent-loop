"""Tests for MCP tool wiring in the coding harness."""

from __future__ import annotations

from agent_loop.harness import CodingAgentHarness
from agent_loop.mcp import CallableMcpClient, McpSnapshotCache, McpToolDefinition, sync_mcp_tools
from agent_loop.models import ToolCallCompletedEvent
from agent_loop.session import PermissionMode
from agent_loop.tools import ShellExecutor


def test_sync_mcp_tools_registers_callable_executor(tmp_path) -> None:
    cache = McpSnapshotCache()
    cache.register(
        McpToolDefinition(
            server_name="demo",
            tool_name="echo",
            description="Echo args",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )
    )
    client = CallableMcpClient()
    client.register(
        "demo",
        "echo",
        lambda _server, _tool, args: {"success": True, "message": args.get("message", "")},
    )

    harness = CodingAgentHarness(
        executors=[ShellExecutor()],
        working_directory=str(tmp_path),
        mcp_cache=cache,
        mcp_client=client,
    )

    assert "mcp__demo__echo" in harness.tool_names
    events = list(
        harness.run_tool_sequence(
            "echo",
            [{"tool": "mcp__demo__echo", "args": {"message": "hello"}, "call_id": "call_1"}],
        )
    )
    completed = [event for event in events if isinstance(event, ToolCallCompletedEvent)]
    assert completed[0].result["message"] == "hello"


def test_mcp_blocked_in_read_only_mode(tmp_path) -> None:
    cache = McpSnapshotCache()
    cache.register(McpToolDefinition(server_name="demo", tool_name="echo"))
    client = CallableMcpClient()
    client.register("demo", "echo", lambda *_args: {"success": True})

    harness = CodingAgentHarness(
        working_directory=str(tmp_path),
        permission_mode=PermissionMode.READ_ONLY,
        mcp_cache=cache,
        mcp_client=client,
    )
    events = list(
        harness.run_tool_sequence(
            "echo",
            [{"tool": "mcp__demo__echo", "args": {}, "call_id": "call_1"}],
        )
    )
    completed = [event for event in events if isinstance(event, ToolCallCompletedEvent)]
    assert "read-only" in (completed[0].error or "")


def test_sync_mcp_tools_helper_replaces_stale_executors() -> None:
    from agent_loop.agent import Agent

    cache = McpSnapshotCache()
    cache.sync([McpToolDefinition(server_name="s1", tool_name="a")])
    client = CallableMcpClient()
    agent = Agent()
    first = sync_mcp_tools(agent, cache, client)
    assert len(first) == 1

    cache.sync([McpToolDefinition(server_name="s1", tool_name="b")])
    second = sync_mcp_tools(agent, cache, client)
    assert len(second) == 1
    assert "mcp__s1__b" in agent.tool_names
    assert "mcp__s1__a" not in agent.tool_names
