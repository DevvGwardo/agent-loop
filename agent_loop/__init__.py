"""agent-loop — A clean reimplementation of an AI coding agent streaming protocol."""

from agent_loop.agent import Agent, ToolExecutor
from agent_loop.dispatcher import ToolDispatcher
from agent_loop.models import (
    # Geometry
    Position,
    Range,
    OutputLocation,
    Diagnostic,
    # Tool call types
    ShellToolCall,
    ReadToolCall,
    EditToolCall,
    WebFetchToolCall,
    McpToolCall,
    GrepToolCall,
    GlobToolCall,
    AskQuestionToolCall,
    ToolCall,
    # Streaming updates
    ToolCallStartedUpdate,
    ToolCallDeltaUpdate,
    ToolCallCompletedUpdate,
    ThinkingDeltaUpdate,
    ShellStreamStdout,
    ShellStreamStderr,
    StreamingUpdate,
    # Approval
    ApprovalGateMode,
    ApprovalRequest,
    ApprovalResponse,
    ApprovalGate,
    # Context / skills
    LazySection,
    RequestContext,
    AgentSkill,
    CursorRule,
    McpToolDefinition,
    # Conversation
    MessageRole,
    Message,
    # Agent events
    ToolCallStartedEvent,
    ToolCallDeltaEvent,
    ToolCallCompletedEvent,
    AgentEvent,
)

__all__ = [
    # Core classes
    "Agent",
    "ToolExecutor",
    "ToolDispatcher",
    # Geometry
    "Position",
    "Range",
    "OutputLocation",
    "Diagnostic",
    # Tool call types
    "ShellToolCall",
    "ReadToolCall",
    "EditToolCall",
    "WebFetchToolCall",
    "McpToolCall",
    "GrepToolCall",
    "GlobToolCall",
    "AskQuestionToolCall",
    "ToolCall",
    # Streaming updates
    "ToolCallStartedUpdate",
    "ToolCallDeltaUpdate",
    "ToolCallCompletedUpdate",
    "ThinkingDeltaUpdate",
    "ShellStreamStdout",
    "ShellStreamStderr",
    "StreamingUpdate",
    # Approval
    "ApprovalGateMode",
    "ApprovalRequest",
    "ApprovalResponse",
    "ApprovalGate",
    # Context / skills
    "LazySection",
    "RequestContext",
    "AgentSkill",
    "CursorRule",
    "McpToolDefinition",
    # Conversation
    "MessageRole",
    "Message",
    # Agent events
    "ToolCallStartedEvent",
    "ToolCallDeltaEvent",
    "ToolCallCompletedEvent",
    "AgentEvent",
]

__version__ = "0.1.0"
