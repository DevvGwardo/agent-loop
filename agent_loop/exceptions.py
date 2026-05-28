"""Custom exceptions for the agent-loop library."""

from __future__ import annotations


class AgentError(Exception):
    """Base exception for all agent-loop errors."""


class ToolExecutionError(AgentError):
    """Raised when a tool executor fails during execution."""


class ToolNotFoundError(AgentError):
    """Raised when a requested tool name is not registered."""


class ApprovalRequiredError(AgentError):
    """Raised when a tool invocation requires human approval."""


class ApprovalRejectedError(AgentError):
    """Raised when a human rejects a tool invocation that required approval."""


class McpServerError(AgentError):
    """Raised when an MCP server call fails or returns an error."""


class SandboxError(AgentError):
    """Raised when a sandbox operation (create / exec / destroy) fails."""
