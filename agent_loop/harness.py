"""Reusable coding-agent harness for channel adapters."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Generator, Iterable
from typing import Any

from agent_loop.agent import Agent
from agent_loop.llm import ChatModelClient, ToolCallRequest
from agent_loop.models import (
    AgentEvent,
    MessageRole,
    ToolCallCompletedEvent,
    ToolCallDeltaEvent,
    ToolCallStartedEvent,
)
from agent_loop.session import AgentSessionState, PermissionMode, PlanStep
from agent_loop.mcp.cache import McpSnapshotCache
from agent_loop.mcp.client import McpClient
from agent_loop.mcp.tools import MCP_PREFIX, sync_mcp_tools
from agent_loop.tools import (
    EditExecutor,
    GlobExecutor,
    GrepExecutor,
    PlanExecutor,
    ReadExecutor,
    ShellExecutor,
    ToolExecutor,
    WebFetchExecutor,
    WebSearchExecutor,
)
from agent_loop.workspace import build_workspace_context, compose_system_prompt


DEFAULT_CODING_SYSTEM_PROMPT = """You are a coding agent running in a real workspace.
Use tools to inspect files before editing. Prefer small, reversible changes.
When you edit, verify with the narrowest useful test or command. Summarize
what changed and mention any verification that could not be run.

Use update_plan for multi-step work. Treat permission errors as a signal to
ask the user to change /permissions or approve a narrower approach."""


def default_coding_tools(*, include_web_search: bool = False) -> list[ToolExecutor]:
    """Return the standard local coding tool set."""
    tools: list[ToolExecutor] = [
        ShellExecutor(),
        ReadExecutor(),
        EditExecutor(),
        GrepExecutor(),
        GlobExecutor(),
        WebFetchExecutor(),
        PlanExecutor(),
    ]
    if include_web_search:
        tools.append(WebSearchExecutor())
    return tools


def tool_schema(executor: ToolExecutor) -> dict[str, Any]:
    """Build an OpenAI-compatible tool schema for an executor."""
    if hasattr(executor, "args_schema"):
        schema = executor.args_schema()  # type: ignore[attr-defined]
    else:
        schema = _fallback_schema(executor.name)
    return {
        "type": "function",
        "function": {
            "name": executor.name,
            "description": executor.description,
            "parameters": schema,
        },
    }


def _fallback_schema(tool_name: str) -> dict[str, Any]:
    schemas: dict[str, dict[str, Any]] = {
        "shell": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "working_directory": {"type": "string", "description": "Directory to run in"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
                "env": {"type": "object", "description": "Environment variable overrides"},
            },
            "required": ["command"],
        },
        "read": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "offset": {"type": "integer", "description": "Byte offset"},
                "limit": {"type": "integer", "description": "Max bytes to read"},
            },
            "required": ["path"],
        },
        "edit": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit"},
                "mode": {
                    "type": "string",
                    "enum": ["str_replace", "stream_content"],
                    "description": "Edit mode",
                },
                "old_string": {"type": "string", "description": "Unique text to replace"},
                "new_string": {"type": "string", "description": "Replacement text"},
                "content": {"type": "string", "description": "Full file content for stream_content"},
            },
            "required": ["path", "mode"],
        },
        "web_fetch": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "timeout": {"type": "number", "description": "Timeout in seconds"},
            },
            "required": ["url"],
        },
        "glob": GlobExecutor().args_schema(),
        "update_plan": PlanExecutor().args_schema(),
    }
    return schemas.get(
        tool_name,
        {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        },
    )


class CodingAgentHarness:
    """Model/tool orchestration layer that can sit behind TUI, Telegram, or CI."""

    def __init__(
        self,
        *,
        model_client: ChatModelClient | None = None,
        executors: Iterable[ToolExecutor] | None = None,
        working_directory: str | None = None,
        system_prompt: str = DEFAULT_CODING_SYSTEM_PROMPT,
        max_iterations: int = 8,
        thread_id: str | None = None,
        permission_mode: PermissionMode | str = PermissionMode.WORKSPACE,
        initial_messages: list[dict[str, Any]] | None = None,
        mcp_cache: McpSnapshotCache | None = None,
        mcp_client: McpClient | None = None,
        mcp_instructions: str = "",
        load_workspace_context: bool = True,
    ) -> None:
        self.model_client = model_client
        self.working_directory = working_directory or os.getcwd()
        self.max_iterations = max_iterations
        self.thread_id = thread_id or str(uuid.uuid4())
        self.permission_mode = (
            permission_mode
            if isinstance(permission_mode, PermissionMode)
            else PermissionMode.parse(permission_mode)
        )
        self._system_prompt = system_prompt
        self._mcp_cache = mcp_cache
        self._mcp_client = mcp_client
        self._mcp_instructions = mcp_instructions
        self._load_workspace_context = load_workspace_context
        self.agent = Agent(
            executors=list(executors or default_coding_tools()),
            system_prompt=system_prompt,
        )
        if mcp_cache is not None and mcp_client is not None:
            sync_mcp_tools(self.agent, mcp_cache, mcp_client)
        if initial_messages:
            self._messages = list(initial_messages)
        else:
            self._messages = [
                {
                    "role": MessageRole.system.value,
                    "content": self._compose_system_message(),
                },
            ]

    @property
    def tool_names(self) -> list[str]:
        return self.agent.tool_names

    @property
    def mcp_tool_names(self) -> list[str]:
        return [name for name in self.tool_names if name.startswith(MCP_PREFIX)]

    def set_working_directory(self, path: str) -> None:
        """Change workspace and refresh injected workspace context."""
        self.working_directory = path
        self.refresh_workspace_context()

    def refresh_workspace_context(self) -> None:
        """Rebuild the system message with current workspace and MCP notes."""
        if not self._messages or self._messages[0].get("role") != MessageRole.system.value:
            return
        self._messages[0]["content"] = self._compose_system_message()

    def sync_mcp_tools(self) -> int:
        """Refresh MCP executors from the configured cache. Returns tool count."""
        if self._mcp_cache is None or self._mcp_client is None:
            return 0
        executors = sync_mcp_tools(self.agent, self._mcp_cache, self._mcp_client)
        self.refresh_workspace_context()
        return len(executors)

    def _compose_system_message(self) -> str:
        workspace_context = ""
        if self._load_workspace_context:
            workspace_context = build_workspace_context(self.working_directory)
        return compose_system_prompt(
            self._system_prompt,
            workspace_context=workspace_context,
            mcp_instructions=self._mcp_instructions,
        )

    @property
    def tools_for_model(self) -> list[dict[str, Any]]:
        return [
            tool_schema(executor)
            for name in self.agent.tool_names
            if (executor := self.agent.get_executor(name)) is not None
        ]

    @property
    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    @property
    def plan(self) -> list[PlanStep]:
        for name in self.agent.tool_names:
            executor = self.agent.get_executor(name)
            if isinstance(executor, PlanExecutor):
                return list(executor.plan)
        return []

    def snapshot(self, *, chat_id: str = "", model: str = "") -> AgentSessionState:
        return AgentSessionState(
            thread_id=self.thread_id,
            chat_id=chat_id,
            model=model,
            working_directory=self.working_directory,
            permission_mode=self.permission_mode.value,
            messages=self.messages,
            plan=self.plan,
        )

    def restore_plan(self, plan: list[PlanStep]) -> None:
        for name in self.agent.tool_names:
            executor = self.agent.get_executor(name)
            if isinstance(executor, PlanExecutor):
                executor.plan = list(plan)
                return

    def run_tool_sequence(
        self,
        prompt: str,
        tool_sequence: list[dict[str, Any]],
    ) -> Generator[AgentEvent, None, str]:
        """Run explicit tool calls through the same event protocol."""
        reply = yield from self._run_sequence(prompt, tool_sequence)
        return reply

    def run_json_events(self, prompt: str) -> Generator[dict[str, Any], None, str]:
        """Run a turn and emit codex exec-like JSON events."""
        yield {"type": "thread.started", "thread_id": self.thread_id}
        yield {"type": "turn.started"}
        runner = self.run(prompt)
        reply = ""
        while True:
            try:
                event = next(runner)
            except StopIteration as done:
                reply = done.value or ""
                break
            yield _event_to_thread_event(event)
        yield {"type": "turn.completed", "usage": {}}
        return reply

    def run(self, prompt: str) -> Generator[AgentEvent, None, str]:
        """Run a model-driven tool loop and yield tool execution events."""
        if self.model_client is None:
            raise RuntimeError("CodingAgentHarness.run() requires a model_client")

        self._messages.append({"role": MessageRole.user.value, "content": prompt})
        final_reply = ""

        for _ in range(self.max_iterations):
            response = self.model_client.complete(self._messages, self.tools_for_model)
            for index, call in enumerate(response.tool_calls):
                if not call.call_id:
                    call.call_id = f"call_{call.name}_{index}"
            final_reply = response.content
            assistant_message = {
                "role": MessageRole.assistant.value,
                "content": response.content,
            }

            if not response.tool_calls:
                self._messages.append(assistant_message)
                self.agent.add_message(MessageRole.assistant, response.content)
                return response.content

            assistant_message["tool_calls"] = [
                _tool_call_message(call) for call in response.tool_calls
            ]
            self._messages.append(assistant_message)

            tool_sequence = [
                {"tool": call.name, "args": call.args, "call_id": call.call_id}
                for call in response.tool_calls
            ]
            completed: list[ToolCallCompletedEvent] = []
            for event in self._run_sequence(prompt, tool_sequence):
                if isinstance(event, ToolCallCompletedEvent):
                    completed.append(event)
                yield event

            for event in completed:
                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": event.call_id,
                        "name": event.tool_name,
                        "content": json.dumps(
                            {"result": event.result, "error": event.error},
                            default=str,
                        ),
                    }
                )

        timeout_reply = (
            final_reply
            or f"Stopped after {self.max_iterations} tool-call iterations without a final reply."
        )
        self._messages.append({"role": MessageRole.assistant.value, "content": timeout_reply})
        self.agent.add_message(MessageRole.assistant, timeout_reply)
        return timeout_reply

    def _run_sequence(
        self,
        prompt: str,
        tool_sequence: list[dict[str, Any]],
    ) -> Generator[AgentEvent, None, str]:
        context = {"working_directory": self.working_directory}
        final_content: list[str] = []

        for call_spec in tool_sequence:
            tool_name = call_spec["tool"]
            args = call_spec.get("args", {})
            call_id = call_spec.get("call_id") or uuid.uuid4().hex[:12]
            blocked = self._permission_error(tool_name, args)
            if blocked:
                yield ToolCallCompletedEvent(
                    call_id=call_id,
                    tool_name=tool_name,
                    result={},
                    error=blocked,
                )
                final_content.append(f"[{tool_name} blocked: {blocked}]")
                continue

            for event in self.agent.run(
                prompt,
                tool_sequence=[{**call_spec, "call_id": call_id}],
                context=context,
            ):
                if isinstance(event, ToolCallCompletedEvent):
                    final_content.append(
                        f"[{tool_name} {'error' if event.error else 'completed'}]"
                    )
                yield event

        return "\n".join(final_content) if final_content else f"Processed: {prompt}"

    def _permission_error(self, tool_name: str, args: dict[str, Any]) -> str | None:
        if self.permission_mode == PermissionMode.FULL_ACCESS:
            return None
        if self.permission_mode == PermissionMode.READ_ONLY and (
            tool_name in {"shell", "edit"} or tool_name.startswith(MCP_PREFIX)
        ):
            return f"{tool_name} is blocked in read-only permission mode"
        if self.permission_mode == PermissionMode.WORKSPACE and tool_name == "shell":
            executor = self.agent.get_executor(tool_name)
            if executor is not None and hasattr(executor, "needs_approval"):
                if executor.needs_approval(args):
                    return "shell command requires full-access permissions"
        if self.permission_mode == PermissionMode.WORKSPACE and tool_name == "edit":
            path = str(args.get("path") or "")
            if path and os.path.isabs(path):
                try:
                    common = os.path.commonpath([self.working_directory, path])
                except ValueError:
                    return "absolute edit path is outside the workspace"
                if common != os.path.abspath(self.working_directory):
                    return "absolute edit path is outside the workspace"
        return None


def _tool_call_message(call: ToolCallRequest) -> dict[str, Any]:
    return {
        "id": call.call_id or f"call_{call.name}",
        "type": "function",
        "function": {
            "name": call.name,
            "arguments": json.dumps(call.args),
        },
    }


def _event_to_thread_event(event: AgentEvent) -> dict[str, Any]:
    if isinstance(event, ToolCallStartedEvent):
        return {
            "type": "item.started",
            "item": {
                "id": event.call_id,
                "type": "command_execution" if event.tool_name == "shell" else "tool_call",
                "tool_name": event.tool_name,
                "args": event.args,
                "status": "in_progress",
            },
        }
    if isinstance(event, ToolCallDeltaEvent):
        return {
            "type": "item.updated",
            "item": {
                "id": event.call_id,
                "type": "tool_delta",
                "delta": event.delta,
            },
        }
    if isinstance(event, ToolCallCompletedEvent):
        return {
            "type": "item.completed",
            "item": {
                "id": event.call_id,
                "type": "command_execution" if event.tool_name == "shell" else "tool_call",
                "tool_name": event.tool_name,
                "result": event.result,
                "error": event.error,
                "status": "failed" if event.error else "completed",
            },
        }
    return {"type": "item.updated", "item": {"id": "unknown", "type": "unknown"}}


__all__ = [
    "CodingAgentHarness",
    "DEFAULT_CODING_SYSTEM_PROMPT",
    "default_coding_tools",
    "tool_schema",
]
