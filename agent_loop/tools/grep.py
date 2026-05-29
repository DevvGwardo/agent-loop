"""Grep tool: fast file search using ripgrep."""
from __future__ import annotations

import subprocess
from typing import Any

from .base import ToolExecutor


class GrepExecutor(ToolExecutor):
    """Search file contents using ripgrep (rg)."""

    @property
    def name(self) -> str:
        return "grep"

    @property
    def description(self) -> str:
        return "Fast file content search using ripgrep. Supports regex patterns, file globs, and context lines."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory to search in (default: current)"},
                "file_glob": {"type": "string", "description": "Optional file glob filter (e.g. *.py)"},
                "context": {"type": "integer", "description": "Lines of context before/after each match"},
            },
            "required": ["pattern"],
        }

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        args = args or {}
        cmd = ["rg", "-n"]
        if not args.get("pattern"):
            return {"exit_code": 1, "stdout": "", "stderr": "No pattern provided", "count": 0, "success": False}
        if ctx := args.get("context"):
            cmd.extend(["-C", str(ctx)])
        if glob := args.get("file_glob"):
            cmd.extend(["-g", glob])
        cmd.append(args["pattern"])
        if path := args.get("path"):
            cmd.append(path)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return {"matches": result.stdout.splitlines(), "count": len(result.stdout.splitlines())}
            elif result.returncode == 1:
                return {"matches": [], "count": 0, "note": "No matches found"}
            else:
                return {"error": result.stderr.strip(), "exit_code": result.returncode}
        except subprocess.TimeoutExpired:
            return {"error": "Search timed out after 30s"}
        except FileNotFoundError:
            return {"error": "ripgrep (rg) not found. Install with: brew install ripgrep"}
