"""Agent — orchestrates tool execution and yields streaming events."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, Generator, List, Optional, Protocol, Union

from agent_loop.models import (
    Message,
    MessageRole,
    ToolCallCompletedEvent,
    ToolCallDeltaEvent,
    ToolCallStartedEvent,
)


def _resolve(value: Any) -> Any:
    """Return the resolved value if *value* is a coroutine, else the value itself."""
    if asyncio.iscoroutine(value):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = asyncio.run_coroutine_threadsafe(value, loop)
                return future.result()
        return asyncio.run(value)
    return value


class ToolExecutor(Protocol):
    """Protocol for tool executors registered with the Agent."""

    @property
    def name(self) -> str:
        ...

    async def execute(self, args: dict, context: dict | None = None) -> Any:
        ...


class Agent:
    """An AI coding agent that orchestrates tool execution and yields streaming events.

    Usage:
        agent = Agent(executors=[shell_exec, read_exec])
        for event in agent.run("List the files"):
            match event:
                case ToolCallStartedEvent(): ...
                case ToolCallDeltaEvent(): ...
                case ToolCallCompletedEvent(): ...
    """

    def __init__(
        self,
        executors: Optional[List[ToolExecutor]] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self._executors: Dict[str, ToolExecutor] = {}
        self._history: List[Message] = []
        self._system_prompt = system_prompt or "You are a helpful AI coding agent."

        if executors:
            for exe in executors:
                self.register_tool(exe)

    # ── history ───────────────────────────────────────────────────────

    @property
    def history(self) -> List[Message]:
        return list(self._history)

    def add_message(self, role: MessageRole, content: str, **kwargs: Any) -> None:
        self._history.append(Message(role=role, content=content, **kwargs))

    def clear_history(self) -> None:
        self._history.clear()

    # ── tool registration ─────────────────────────────────────────────

    def register_tool(self, executor: ToolExecutor) -> None:
        if executor.name in self._executors:
            raise ValueError(f"Tool '{executor.name}' is already registered.")
        self._executors[executor.name] = executor

    def unregister_tool(self, name: str) -> None:
        self._executors.pop(name, None)

    @property
    def tool_names(self) -> List[str]:
        return list(self._executors.keys())

    def get_executor(self, name: str) -> Optional[ToolExecutor]:
        return self._executors.get(name)

    # ── run ───────────────────────────────────────────────────────────

    def run(
        self,
        prompt: str,
        *,
        tool_sequence: Optional[List[Dict[str, Any]]] = None,
    ) -> Generator[Union[ToolCallStartedEvent, ToolCallDeltaEvent, ToolCallCompletedEvent], None, str]:
        """Accept a prompt and yield streaming tool events.

        The *tool_sequence* is a list of dicts with keys:
            - tool (str): name of the registered executor
            - args (dict): arguments to pass

        By default a simple sequence is auto-generated.  Subclasses
        should override this method to implement LLM call-and-response
        loops.  The return value is the final assistant reply.
        """
        self.add_message(MessageRole.user, prompt)

        if tool_sequence is None:
            tool_sequence = []

        final_content: List[str] = []

        for call_spec in tool_sequence:
            tool_name = call_spec["tool"]
            args = call_spec.get("args", {})
            call_id = call_spec.get("call_id", uuid.uuid4().hex[:12])

            executor = self._executors.get(tool_name)
            if executor is None:
                yield ToolCallCompletedEvent(
                    call_id=call_id,
                    tool_name=tool_name,
                    result={},
                    error=f"Unknown tool: {tool_name}",
                )
                final_content.append(f"[Tool {tool_name} not found]")
                continue

            yield ToolCallStartedEvent(call_id=call_id, tool_name=tool_name, args=args)

            # For each tool, yield incremental delta events
            yield ToolCallDeltaEvent(call_id=call_id, delta=f"Executing {tool_name}...")

            try:
                result = _resolve(executor.execute(args))
            except Exception as exc:
                result = {}
                error = str(exc)
                yield ToolCallCompletedEvent(
                    call_id=call_id,
                    tool_name=tool_name,
                    result={},
                    error=error,
                )
                self.add_message(
                    MessageRole.tool,
                    content=f"Error: {error}",
                    name=tool_name,
                    tool_call_id=call_id,
                )
                final_content.append(f"[{tool_name} error: {error}]")
                continue

            yield ToolCallCompletedEvent(call_id=call_id, tool_name=tool_name, result=result)

            self.add_message(
                MessageRole.tool,
                content=str(result),
                name=tool_name,
                tool_call_id=call_id,
            )

            final_content.append(f"[{tool_name} completed]")

        reply = "\n".join(final_content) if final_content else f"Processed: {prompt}"
        self.add_message(MessageRole.assistant, reply)
        return reply


__all__ = ["Agent", "ToolExecutor"]
