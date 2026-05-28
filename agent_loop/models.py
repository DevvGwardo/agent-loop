"""Pydantic models for the agent-loop streaming protocol."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ─── Position / Range / OutputLocation ───────────────────────────────


class Position(BaseModel):
    line: int
    character: int


class Range(BaseModel):
    start: Position
    end: Position


class OutputLocation(BaseModel):
    file: str
    range: Optional[Range] = None


class Diagnostic(BaseModel):
    message: str
    severity: str = "error"  # error | warning | info | hint
    location: OutputLocation
    code: Optional[str] = None
    source: Optional[str] = None


# ─── Tool Call Argument / Result Dicts ───────────────────────────────


class ShellToolCall(BaseModel):
    """Execute a shell command on the host."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"command": "", "timeout": 30})
    result: Dict[str, Any] = Field(default_factory=lambda: {"stdout": "", "stderr": "", "exit_code": -1})


class ReadToolCall(BaseModel):
    """Read a file from the workspace."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"path": "", "offset": 0, "limit": 200})
    result: Dict[str, Any] = Field(default_factory=lambda: {"content": "", "total_lines": 0})


class EditToolCall(BaseModel):
    """Edit a file in the workspace via find-and-replace."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"path": "", "old_string": "", "new_string": ""})
    result: Dict[str, Any] = Field(default_factory=lambda: {"applied": False, "error": None})


class WebFetchToolCall(BaseModel):
    """Fetch content from a URL."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"url": "", "timeout": 15})
    result: Dict[str, Any] = Field(default_factory=lambda: {"content": "", "status_code": 0, "headers": {}})


class McpToolCall(BaseModel):
    """Call a tool exposed by an MCP server."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"server": "", "tool": "", "params": {}})
    result: Dict[str, Any] = Field(default_factory=lambda: {"content": "", "is_error": False})


class GrepToolCall(BaseModel):
    """Search file contents with a regex pattern."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"pattern": "", "path": ".", "file_glob": "", "context": 0})
    result: Dict[str, Any] = Field(default_factory=lambda: {"matches": [], "count": 0})


class GlobToolCall(BaseModel):
    """Find files matching a glob pattern."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"pattern": "", "path": "."})
    result: Dict[str, Any] = Field(default_factory=lambda: {"files": []})


class AskQuestionToolCall(BaseModel):
    """Ask a question to the user and wait for a response."""

    args: Dict[str, Any] = Field(default_factory=lambda: {"question": "", "choices": None})
    result: Dict[str, Any] = Field(default_factory=lambda: {"answer": ""})


ToolCall = Union[
    ShellToolCall,
    ReadToolCall,
    EditToolCall,
    WebFetchToolCall,
    McpToolCall,
    GrepToolCall,
    GlobToolCall,
    AskQuestionToolCall,
]


# ─── Streaming Updates ───────────────────────────────────────────────


class ToolCallStartedUpdate(BaseModel):
    """Emitted when a tool call begins execution."""

    tool_name: str
    call_id: str
    args: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class ToolCallDeltaUpdate(BaseModel):
    """Emitted incrementally during a tool call's execution."""

    call_id: str
    delta: str
    done: bool = False


class ToolCallCompletedUpdate(BaseModel):
    """Emitted when a tool call finishes."""

    call_id: str
    tool_name: str
    result: Dict[str, Any]
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.now)


class ThinkingDeltaUpdate(BaseModel):
    """Emitted when the agent streams reasoning text."""

    delta: str


class ShellStreamStdout(BaseModel):
    """A chunk of stdout from a running shell tool."""

    call_id: str
    data: str


class ShellStreamStderr(BaseModel):
    """A chunk of stderr from a running shell tool."""

    call_id: str
    data: str


StreamingUpdate = Union[
    ToolCallStartedUpdate,
    ToolCallDeltaUpdate,
    ToolCallCompletedUpdate,
    ThinkingDeltaUpdate,
    ShellStreamStdout,
    ShellStreamStderr,
]


# ─── Approval Types ──────────────────────────────────────────────────


class ApprovalGateMode(str, Enum):
    pre = "pre"
    post = "post"


class ApprovalRequest(BaseModel):
    """A request for user approval before or after a tool call."""

    call_id: str
    tool_name: str
    args: Dict[str, Any]
    mode: ApprovalGateMode = ApprovalGateMode.pre
    prompt: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class ApprovalResponse(BaseModel):
    """User's response to an approval request."""

    call_id: str
    approved: bool
    feedback: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ApprovalGate(BaseModel):
    """Configuration for approval gating on a tool call."""

    mode: ApprovalGateMode
    call_id: str
    tool_name: str
    args: Dict[str, Any]
    request: Optional[ApprovalRequest] = None
    response: Optional[ApprovalResponse] = None


# ─── Request Context ─────────────────────────────────────────────────


class LazySection(BaseModel):
    """A lazily-loaded section of the request context."""

    name: str
    loaded: bool = False
    content: Optional[str] = None


class RequestContext(BaseModel):
    """The full context for a request, with lazy-loaded sections."""

    prompt: str
    conversation_id: Optional[str] = None
    workspace_path: Optional[str] = None
    sections: Dict[str, LazySection] = Field(default_factory=dict)

    def load_section(self, name: str, content: str) -> None:
        section = self.sections.get(name)
        if section is None:
            section = LazySection(name=name)
            self.sections[name] = section
        section.content = content
        section.loaded = True

    def get_section(self, name: str) -> Optional[str]:
        section = self.sections.get(name)
        if section is not None and section.loaded:
            return section.content
        return None


# ─── Agent Skills / Rules / MCP Definitions ──────────────────────────


class AgentSkill(BaseModel):
    """A skill (plugin) that the agent can load."""

    name: str
    description: str = ""
    version: str = "0.1.0"
    enabled: bool = True


class CursorRule(BaseModel):
    """A project-level rule for the agent to follow."""

    name: str
    description: str
    glob: Optional[str] = None  # file pattern this rule applies to
    instructions: str = ""


class McpToolDefinition(BaseModel):
    """A tool exposed by an MCP server."""

    server_name: str
    tool_name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)


# ─── Agent Conversation ──────────────────────────────────────────────


class MessageRole(str, Enum):
    system = "system"
    user = "user"
    assistant = "assistant"
    tool = "tool"


class Message(BaseModel):
    """A single message in the conversation history."""

    role: MessageRole
    content: str
    name: Optional[str] = None  # tool name for tool-role messages
    tool_call_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)


# ─── Events yielded by Agent.run() ────────────────────────────────────


class ToolCallStartedEvent(BaseModel):
    """Emitted when a tool starts executing."""

    call_id: str
    tool_name: str
    args: Dict[str, Any]


class ToolCallDeltaEvent(BaseModel):
    """Emitted with incremental output during execution."""

    call_id: str
    delta: str


class ToolCallCompletedEvent(BaseModel):
    """Emitted when a tool finishes."""

    call_id: str
    tool_name: str
    result: Dict[str, Any]
    error: Optional[str] = None


AgentEvent = Union[
    ToolCallStartedEvent,
    ToolCallDeltaEvent,
    ToolCallCompletedEvent,
]


__all__ = [
    "Position",
    "Range",
    "OutputLocation",
    "Diagnostic",
    "ShellToolCall",
    "ReadToolCall",
    "EditToolCall",
    "WebFetchToolCall",
    "McpToolCall",
    "GrepToolCall",
    "GlobToolCall",
    "AskQuestionToolCall",
    "ToolCall",
    "ToolCallStartedUpdate",
    "ToolCallDeltaUpdate",
    "ToolCallCompletedUpdate",
    "ThinkingDeltaUpdate",
    "ShellStreamStdout",
    "ShellStreamStderr",
    "StreamingUpdate",
    "ApprovalGateMode",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalGate",
    "LazySection",
    "RequestContext",
    "AgentSkill",
    "CursorRule",
    "McpToolDefinition",
    "MessageRole",
    "Message",
    "ToolCallStartedEvent",
    "ToolCallDeltaEvent",
    "ToolCallCompletedEvent",
    "AgentEvent",
]
