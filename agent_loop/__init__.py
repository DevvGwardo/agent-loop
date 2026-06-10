"""agent-loop — A clean reimplementation of an AI coding agent streaming protocol."""

from agent_loop.agent import Agent, ToolExecutor
from agent_loop.dispatcher import ToolDispatcher
from agent_loop.harness import (
    CodingAgentHarness,
    DEFAULT_CODING_SYSTEM_PROMPT,
    default_coding_tools,
    tool_schema,
)
from agent_loop.llm import (
    ChatModelClient,
    ChatModelResponse,
    OpenAICompatibleChatClient,
    ToolCallRequest,
)
from agent_loop.master_loop import (
    AgentLoopSpec,
    GoalLoopSpec,
    LoopKind,
    LoopLifecycleEvent,
    LoopNode,
    LoopStatus,
    MasterLoopHarness,
    MissionLoopSpec,
    WorkflowLoopSpec,
)
from agent_loop.session import AgentSessionState, PermissionMode, PlanStep, SessionStore
from agent_loop.telegram import TelegramAgentConfig, TelegramCodexAgent
from agent_loop.exceptions import (
    AgentError,
    ToolExecutionError,
    ToolNotFoundError,
    ApprovalRequiredError,
    ApprovalRejectedError,
    McpServerError,
    SandboxError,
)
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
    "CodingAgentHarness",
    "DEFAULT_CODING_SYSTEM_PROMPT",
    "default_coding_tools",
    "tool_schema",
    "ChatModelClient",
    "ChatModelResponse",
    "OpenAICompatibleChatClient",
    "ToolCallRequest",
    "AgentLoopSpec",
    "GoalLoopSpec",
    "LoopKind",
    "LoopLifecycleEvent",
    "LoopNode",
    "LoopStatus",
    "MasterLoopHarness",
    "MissionLoopSpec",
    "WorkflowLoopSpec",
    "AgentSessionState",
    "PermissionMode",
    "PlanStep",
    "SessionStore",
    "TelegramAgentConfig",
    "TelegramCodexAgent",
    # Exceptions
    "AgentError",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ApprovalRequiredError",
    "ApprovalRejectedError",
    "McpServerError",
    "SandboxError",
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
