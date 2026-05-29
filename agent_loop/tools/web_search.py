"""Web search tool using the agent's configured web_search capability."""
from __future__ import annotations

from typing import Any

from .base import ToolExecutor


class WebSearchExecutor(ToolExecutor):
    """Search the web using the configured backend."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for information. Returns up to 5 results with titles, URLs, and descriptions."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "limit": {"type": "integer", "description": "Max results (default: 5)"},
            },
            "required": ["query"],
        }

    async def execute(self, args: dict[str, Any] | None = None, context: dict | None = None) -> dict:
        """Stub — override with your own web_search integration."""
        return {"results": [], "note": "Web search not configured. Override WebSearchExecutor.execute()."}
