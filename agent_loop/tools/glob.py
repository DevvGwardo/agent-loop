"""Glob tool: find files by pattern."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import ToolExecutor


class GlobExecutor(ToolExecutor):
    """Find files matching a glob pattern under a directory."""

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return "Find files matching a glob pattern. Returns up to 200 paths."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. **/*.py)"},
                "path": {"type": "string", "description": "Root directory (default: workspace)"},
            },
            "required": ["pattern"],
        }

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        pattern = str((args or {}).get("pattern") or "").strip()
        if not pattern:
            return {"success": False, "error": "pattern is required", "files": []}

        root = (args or {}).get("path")
        if not root and context:
            root = context.get("working_directory")
        root_path = Path(str(root or ".")).resolve()

        matches = sorted(
            str(path.relative_to(root_path)) if path.is_relative_to(root_path) else str(path)
            for path in root_path.glob(pattern)
            if path.is_file()
        )[:200]

        return {"success": True, "files": matches, "count": len(matches)}


__all__ = ["GlobExecutor"]
