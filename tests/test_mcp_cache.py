"""Tests for McpSnapshotCache — registration, sync, generation tracking, lookup."""

from __future__ import annotations

import time

import pytest

from agent_loop.mcp import McpSnapshotCache, McpToolDefinition


def _make_tool(server: str = "s1", name: str = "t1", desc: str = "") -> McpToolDefinition:
    return McpToolDefinition(
        server_name=server,
        tool_name=name,
        description=desc,
        input_schema={"type": "object", "properties": {}},
    )


class TestMcpSnapshotCacheInit:
    """Empty cache defaults."""

    def test_generation_starts_at_zero(self) -> None:
        cache = McpSnapshotCache()
        assert cache.generation == 0

    def test_tools_empty(self) -> None:
        cache = McpSnapshotCache()
        assert cache.tools == []

    def test_last_sync_starts_at_zero(self) -> None:
        cache = McpSnapshotCache()
        assert cache.last_sync == 0.0


class TestMcpSnapshotCacheRegister:
    """register() — single tool registration."""

    def test_register_increments_generation(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool())
        assert cache.generation == 1

    def test_register_duplicate_does_not_bump_generation(self) -> None:
        cache = McpSnapshotCache()
        tool = _make_tool()
        cache.register(tool)
        gen1 = cache.generation
        cache.register(tool)  # same key
        assert cache.generation == gen1

    def test_register_multiple_tools(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool("s1", "t1"))
        cache.register(_make_tool("s1", "t2"))
        assert len(cache.tools) == 2
        assert cache.generation == 2

    def test_register_different_servers_same_name(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool("s1", "t1"))
        cache.register(_make_tool("s2", "t1"))
        assert len(cache.tools) == 2
        assert cache.generation == 2


class TestMcpSnapshotCacheUnregister:
    """unregister() — removing tools."""

    def test_unregister_removes_and_bumps_generation(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool("s1", "t1"))
        gen1 = cache.generation
        assert cache.unregister("s1", "t1") is True
        assert len(cache.tools) == 0
        assert cache.generation > gen1

    def test_unregister_nonexistent_returns_false(self) -> None:
        cache = McpSnapshotCache()
        assert cache.unregister("ghost", "fake") is False

    def test_unregister_does_not_bump_on_failure(self) -> None:
        cache = McpSnapshotCache()
        gen = cache.generation
        cache.unregister("x", "y")
        assert cache.generation == gen


class TestMcpSnapshotCacheSync:
    """sync() — bulk replace with generation tracking."""

    def test_sync_empty_list_clears_cache(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool())
        assert len(cache.tools) == 1
        cache.sync([])
        assert len(cache.tools) == 0

    def test_sync_same_tools_no_bump(self) -> None:
        cache = McpSnapshotCache()
        tools = [_make_tool("s1", "t1"), _make_tool("s1", "t2")]
        gen1 = cache.sync(tools)
        gen2 = cache.sync(tools)  # same set
        assert gen2 == gen1

    def test_sync_different_tools_bumps_generation(self) -> None:
        cache = McpSnapshotCache()
        gen1 = cache.sync([_make_tool("s1", "t1")])
        gen2 = cache.sync([_make_tool("s1", "t2")])  # different tool
        assert gen2 > gen1

    def test_sync_updates_last_sync_timestamp(self) -> None:
        cache = McpSnapshotCache()
        old_ts = cache.last_sync
        cache.sync([_make_tool()])
        assert cache.last_sync >= old_ts
        assert cache.last_sync > 0

    def test_sync_returns_generation(self) -> None:
        cache = McpSnapshotCache()
        gen = cache.sync([_make_tool()])
        assert gen == cache.generation

    def test_sync_replaces_all_tools(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool("s1", "t1"))
        cache.register(_make_tool("s2", "t2"))
        cache.sync([_make_tool("s3", "t3")])
        names = {t.tool_name for t in cache.tools}
        assert names == {"t3"}


class TestMcpSnapshotCacheLookup:
    """get() and list_by_server() — tool lookups."""

    def test_get_existing_tool(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool("s1", "t1"))
        tool = cache.get("s1", "t1")
        assert tool is not None
        assert tool.tool_name == "t1"
        assert tool.server_name == "s1"

    def test_get_nonexistent_returns_none(self) -> None:
        cache = McpSnapshotCache()
        assert cache.get("fake", "nope") is None

    def test_list_by_server_empty(self) -> None:
        cache = McpSnapshotCache()
        assert cache.list_by_server("s1") == []

    def test_list_by_server_returns_matching_tools(self) -> None:
        cache = McpSnapshotCache()
        cache.register(_make_tool("s1", "t1"))
        cache.register(_make_tool("s1", "t2"))
        cache.register(_make_tool("s2", "t3"))
        s1_tools = cache.list_by_server("s1")
        assert len(s1_tools) == 2
        assert all(t.server_name == "s1" for t in s1_tools)

    def test_get_after_sync(self) -> None:
        cache = McpSnapshotCache()
        cache.sync([_make_tool("x", "y")])
        assert cache.get("x", "y") is not None


class TestMcpSnapshotCacheClear:
    """clear() — full reset."""

    def test_clear_empties_tools(self) -> None:
        cache = McpSnapshotCache()
        cache.sync([_make_tool(), _make_tool("s2", "t2")])
        cache.clear()
        assert len(cache.tools) == 0

    def test_clear_resets_generation(self) -> None:
        cache = McpSnapshotCache()
        cache.sync([_make_tool()])
        cache.clear()
        assert cache.generation == 0

    def test_clear_resets_last_sync(self) -> None:
        cache = McpSnapshotCache()
        cache.sync([_make_tool()])
        cache.clear()
        assert cache.last_sync == 0.0


class TestMcpSnapshotCacheEdgeCases:
    """Large sets, stress-adjacent operations."""

    def test_20k_tools_via_register(self) -> None:
        cache = McpSnapshotCache()
        for sid in range(200):
            for tid in range(100):
                cache.register(_make_tool(f"s{sid}", f"t{tid}"))
        assert cache.generation == 20000
        assert len(cache.tools) == 20000

    def test_20k_tools_via_sync(self) -> None:
        cache = McpSnapshotCache()
        tools = [_make_tool(f"s{sid}", f"t{tid}") for sid in range(200) for tid in range(100)]
        gen = cache.sync(tools)
        assert gen == 1  # single sync = 1 bump
        assert len(cache.tools) == 20000
