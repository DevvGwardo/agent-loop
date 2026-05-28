"""Pydantic models for request and invocation context."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Selection types
# ---------------------------------------------------------------------------

class SelectedType(str, Enum):
    """Type of IDE selection."""

    FILE = "file"
    TERMINAL = "terminal"
    FOLDER = "folder"
    TEXT = "text"


class SelectedContext(BaseModel):
    """Represents what the user currently has selected in the IDE."""

    type: SelectedType
    value: str
    label: str | None = None
    path: str | None = None


# ---------------------------------------------------------------------------
# Agent skill model
# ---------------------------------------------------------------------------

class AgentSkill(BaseModel):
    """A named skill the agent can load."""

    name: str
    description: str
    instructions: str = ""
    enabled: bool = True


# ---------------------------------------------------------------------------
# Cursor rules
# ---------------------------------------------------------------------------

class CursorRule(BaseModel):
    """A single rule the agent should follow.

    Attributes
    ----------
    type : str
        One of ``"global"`` (always active), ``"file"`` (scoped to a file), or
        ``"manual"`` (user-invoked).
    content : str
        The rule text.
    file_pattern : str | None
        Glob pattern when type is ``"file"``.
    """

    type: str = Field(default="global", pattern=r"^(global|file|manual)$")
    content: str
    file_pattern: str | None = None


# ---------------------------------------------------------------------------
# Invocation context  (IDE / git / PR information)
# ---------------------------------------------------------------------------

class InvocationContext(BaseModel):
    """Snapshot of the IDE state at the time of the request.

    Parameters
    ----------
    timestamp : datetime
        When this snapshot was taken.
    working_directory : str
        Absolute path to the project root.
    selected : SelectedContext | None
        Whatever the user had selected.
    git_branch : str | None
        Current git branch name.
    git_status : str | None
        Output of ``git status --short`` (or similar).
    git_commit : str | None
        HEAD commit SHA.
    git_diff : str | None
        Uncommitted diff (``git diff``).
    pr_number : int | None
        Pull-request number if applicable.
    pr_title : str | None
        PR title (if applicable).
    pr_description : str | None
        PR body text (if applicable).
    """

    timestamp: datetime = Field(default_factory=datetime.now)
    working_directory: str = "."
    selected: SelectedContext | None = None
    git_branch: str | None = None
    git_status: str | None = None
    git_commit: str | None = None
    git_diff: str | None = None
    pr_number: int | None = None
    pr_title: str | None = None
    pr_description: str | None = None


# ---------------------------------------------------------------------------
# Full request context
# ---------------------------------------------------------------------------

class RequestContext(BaseModel):
    """Complete context payload sent to the LLM on each request.

    Each section has a matching ``<section>_complete: bool`` field so
    builders / consumers can detect which sections have been populated.
    """

    # --- System-level sections ---
    rules: str = ""
    rules_complete: bool = False

    env: dict[str, str] = Field(default_factory=dict)
    env_complete: bool = False

    repository_info: dict[str, Any] = Field(default_factory=dict)
    repository_info_complete: bool = False

    tools: dict[str, Any] = Field(default_factory=dict)
    tools_complete: bool = False

    mcp_instructions: str = ""
    mcp_instructions_complete: bool = False

    agent_skills: list[AgentSkill] = Field(default_factory=list)
    agent_skills_complete: bool = False

    custom_subagents: list[dict[str, Any]] = Field(default_factory=list)
    custom_subagents_complete: bool = False

    git_status: str = ""
    git_status_complete: bool = False

    # --- Invocation-level context ---
    invocation: InvocationContext = Field(default_factory=InvocationContext)

    def section_complete(self, name: str) -> bool:
        """Return whether the named section has been marked complete."""
        flag = getattr(self, f"{name}_complete", None)
        if flag is None:
            raise KeyError(f"Unknown context section: {name!r}")
        return bool(flag)

    def mark_complete(self, name: str) -> None:
        """Mark the named section as complete."""
        if not hasattr(self, f"{name}_complete"):
            raise KeyError(f"Unknown context section: {name!r}")
        setattr(self, f"{name}_complete", True)
