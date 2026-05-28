"""Tool executor registry — exports all built-in tool executors."""
from __future__ import annotations


from .base import ToolExecutor
from .shell import ShellExecutor
from .read import ReadExecutor
from .edit import EditExecutor
from .web_fetch import WebFetchExecutor

__all__ = [
    "ToolExecutor",
    "ShellExecutor",
    "ReadExecutor",
    "EditExecutor",
    "WebFetchExecutor",
]

# Registry: tool_name -> executor class
BUILTIN_TOOLS: dict[str, type[ToolExecutor]] = {
    "shell": ShellExecutor,
    "read": ReadExecutor,
    "edit": EditExecutor,
    "web_fetch": WebFetchExecutor,
}


def get_executor(tool_name: str) -> type[ToolExecutor] | None:
    """Look up a built-in tool executor by name."""
    return BUILTIN_TOOLS.get(tool_name)
