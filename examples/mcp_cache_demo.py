"""MCP snapshot cache demo — creates a cache, registers tools, shows generation tracking.

Usage:
    python examples/mcp_cache_demo.py

Demonstrates:
    1. Creating an McpSnapshotCache
    2. Registering tools manually (bypassing sync)
    3. Syncing a batch of tools (with generation bumping)
    4. Looking up tools by server
    5. Unregistering tools
"""

from __future__ import annotations

from agent_loop.mcp.cache import McpSnapshotCache, McpToolDefinition


def main() -> None:
    print("=" * 60)
    print("MCP Snapshot Cache Demo")
    print("=" * 60)

    # 1. Create the cache
    cache = McpSnapshotCache()
    print(f"\n1. Created cache.  generation={cache.generation}  tools={len(cache.tools)}")

    # 2. Register tools one at a time
    cache.register(
        McpToolDefinition(
            server_name="filesystem",
            tool_name="read_file",
            description="Read a file from disk",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path"},
                },
                "required": ["path"],
            },
        )
    )
    print(f"\n2. Registered 'read_file'.  generation={cache.generation}  tools={len(cache.tools)}")

    cache.register(
        McpToolDefinition(
            server_name="filesystem",
            tool_name="write_file",
            description="Write content to a file",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        )
    )
    print(f"   Registered 'write_file'.  generation={cache.generation}  tools={len(cache.tools)}")

    # 3. Sync a batch (no change — generation stays same)
    gen_before = cache.generation
    cache.sync(cache.tools)  # same tools
    print(f"\n3. Synced with same tools.  generation before={gen_before}  after={cache.generation}")
    assert cache.generation == gen_before, "Generation should NOT bump for identical toolset"

    # 4. Sync with a new tool added (generation bumps)
    new_tools = cache.tools + [
        McpToolDefinition(
            server_name="github",
            tool_name="list_pulls",
            description="List open pull requests",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                },
                "required": ["repo"],
            },
        ),
    ]
    gen_before = cache.generation
    gen_after = cache.sync(new_tools)
    print(f"\n4. Synced with new tool 'list_pulls'.  gen {gen_before} → {gen_after}")
    assert gen_after > gen_before, "Generation SHOULD bump after adding a tool"

    # 5. List tools by server
    print("\n5. Tools by server:")
    for server in ["filesystem", "github"]:
        tools = cache.list_by_server(server)
        print(f"   [{server}] ({len(tools)} tools)")
        for t in tools:
            print(f"      - {t.tool_name}: {t.description}")

    # 6. Lookup a specific tool
    tool = cache.get("filesystem", "read_file")
    print(f"\n6. Lookup 'filesystem:read_file': {tool}")
    assert tool is not None

    # 7. Unregister a tool
    removed = cache.unregister("filesystem", "read_file")
    print(f"\n7. Unregister 'filesystem:read_file'.  removed={removed}")
    print(f"   generation={cache.generation}  tools={len(cache.tools)}")
    assert cache.get("filesystem", "read_file") is None

    # 8. Clear
    cache.clear()
    print(f"\n8. Cleared cache.  generation={cache.generation}  tools={len(cache.tools)}")
    assert cache.generation == 0
    assert len(cache.tools) == 0

    print("\n✓ All demo steps completed successfully.")


if __name__ == "__main__":
    main()
