"""MCP snapshot cache — tracks tool definitions and generation metadata."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class McpToolDefinition(BaseModel):
    """Metadata for a single tool exposed by an MCP server."""

    server_name: str
    tool_name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)


class McpSnapshotCache:
    """In-memory cache of MCP tool definitions with generation tracking.

    Usage::

        cache = McpSnapshotCache()
        cache.register(McpToolDefinition(
            server_name="my-server", tool_name="hello",
            description="Say hello", input_schema={"type": "object", "properties": {}},
        ))
        gen1 = cache.generation
        cache.sync([])  # no changes -> generation stays the same
        cache.sync([McpToolDefinition(...)])  # new tool -> generation bumps

    Note: register() takes a single McpToolDefinition, NOT (server_name, tool).
    The old register_server() and add_tool() methods do not exist.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, McpToolDefinition] = {}
        self._generation: int = 0
        self._last_sync: float = 0.0

    # ── properties ──────────────────────────────────────────────────

    @property
    def generation(self) -> int:
        """Monotonically increasing counter that bumps on every change."""
        return self._generation

    @property
    def tools(self) -> List[McpToolDefinition]:
        """All currently cached tool definitions."""
        return list(self._tools.values())

    @property
    def last_sync(self) -> float:
        """Unix timestamp of the last ``sync()`` call."""
        return self._last_sync

    # ── registration ────────────────────────────────────────────────

    def register(self, tool: McpToolDefinition) -> None:
        """Register a single tool directly (bypasses sync)."""
        key = f"{tool.server_name}:{tool.tool_name}"
        if key not in self._tools:
            self._tools[key] = tool
            self._generation += 1

    def unregister(self, server_name: str, tool_name: str) -> bool:
        """Remove a tool from the cache.  Returns ``True`` if it existed."""
        key = f"{server_name}:{tool_name}"
        if key in self._tools:
            del self._tools[key]
            self._generation += 1
            return True
        return False

    # ── sync ────────────────────────────────────────────────────────

    def sync(self, tools: List[McpToolDefinition]) -> int:
        """Replace the cache with *tools* and bump generation if changed.

        Parameters
        ----------
        tools : list of McpToolDefinition
            The full set of currently advertised tools.

        Returns
        -------
        int
            The new generation number.
        """
        new: Dict[str, McpToolDefinition] = {
            f"{t.server_name}:{t.tool_name}": t for t in tools
        }
        if set(new.keys()) != set(self._tools.keys()) or any(
            new[k] != self._tools.get(k) for k in new
        ):
            self._generation += 1
        self._tools = new
        self._last_sync = time.time()
        return self._generation

    # ── lookup ──────────────────────────────────────────────────────

    def get(self, server_name: str, tool_name: str) -> Optional[McpToolDefinition]:
        """Look up a tool by server + name."""
        return self._tools.get(f"{server_name}:{tool_name}")

    def list_by_server(self, server_name: str) -> List[McpToolDefinition]:
        """Return all tools belonging to a specific MCP server."""
        return [t for t in self._tools.values() if t.server_name == server_name]

    def clear(self) -> None:
        """Remove all cached tools and reset the generation counter."""
        self._tools.clear()
        self._generation = 0
        self._last_sync = 0.0
