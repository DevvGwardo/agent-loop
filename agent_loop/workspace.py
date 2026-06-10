"""Workspace context helpers for coding-agent system prompts."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_status_short(working_directory: str) -> str:
    """Return a short git status for *working_directory*, or empty if unavailable."""
    try:
        result = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout + result.stderr).strip()


def read_agents_md(working_directory: str, *, max_chars: int = 8000) -> str:
    """Read ``AGENTS.md`` from the workspace if present."""
    path = Path(working_directory) / "AGENTS.md"
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n... (truncated)"
    return text


def build_workspace_context(working_directory: str) -> str:
    """Assemble workspace notes for injection into the system prompt."""
    sections: list[str] = []
    agents = read_agents_md(working_directory)
    if agents:
        sections.append(f"## AGENTS.md\n{agents}")
    git = git_status_short(working_directory)
    if git:
        sections.append(f"## Git status\n```\n{git}\n```")
    sections.append(f"## Workspace\n`{Path(working_directory).resolve()}`")
    return "\n\n".join(sections)


def compose_system_prompt(
    base_prompt: str,
    *,
    workspace_context: str = "",
    mcp_instructions: str = "",
) -> str:
    """Merge base instructions with optional workspace and MCP sections."""
    parts = [base_prompt.strip()]
    if workspace_context.strip():
        parts.append(workspace_context.strip())
    if mcp_instructions.strip():
        parts.append(f"## MCP\n{mcp_instructions.strip()}")
    return "\n\n".join(parts)


__all__ = [
    "build_workspace_context",
    "compose_system_prompt",
    "git_status_short",
    "read_agents_md",
]
