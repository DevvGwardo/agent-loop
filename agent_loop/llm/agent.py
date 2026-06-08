"""LLMAgent — an Agent whose tool calls are driven by a real LLM.

The base :class:`~agent_loop.agent.Agent` replays a fixed ``tool_sequence``.
``LLMAgent`` overrides :meth:`run` with a call-and-respond loop: ask the model,
execute whatever tools it requests, feed the results back, and repeat until the
model answers with no further tool calls. It yields the same streaming events
as the base agent, so existing consumers (e.g. the TUI) work unchanged.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from agent_loop.agent import Agent, _resolve
from agent_loop.models import (
    MessageRole,
    ToolCallCompletedEvent,
    ToolCallDeltaEvent,
    ToolCallStartedEvent,
)

from .providers import LLMResponse, LLMToolCall, Provider, get_provider

# Called with (tool_name, args) before a flagged tool runs; return True to allow.
Approver = Callable[[str, Dict[str, Any]], bool]


class LLMAgent(Agent):
    """Drive tool execution with an LLM provider.

    Usage::

        from agent_loop.llm import LLMAgent
        from agent_loop.tools import ShellExecutor, ReadExecutor

        agent = LLMAgent(
            provider="openrouter",                 # or any Provider instance
            model="anthropic/claude-sonnet-4-6",
            executors=[ShellExecutor(), ReadExecutor()],
        )
        for event in agent.run("List the Python files and read the smallest one"):
            ...
    """

    def __init__(
        self,
        provider: Union[Provider, str],
        *,
        model: str,
        executors: Optional[List[Any]] = None,
        system_prompt: Optional[str] = None,
        max_steps: int = 12,
        max_tokens: int = 4096,
        context: Optional[Dict[str, Any]] = None,
        approver: Optional[Approver] = None,
        auto_approve: bool = False,
    ) -> None:
        super().__init__(executors=executors, system_prompt=system_prompt)
        self._provider: Provider = get_provider(provider) if isinstance(provider, str) else provider
        self._model = model
        self._max_steps = max_steps
        self._max_tokens = max_tokens
        self._context = context
        self._approver = approver
        self._auto_approve = auto_approve

    # ── tool definitions for the model ────────────────────────────────

    def _tool_defs(self) -> List[Dict[str, Any]]:
        defs: List[Dict[str, Any]] = []
        for name, ex in self._executors.items():
            schema_fn = getattr(ex, "args_schema", None)
            schema = schema_fn() if callable(schema_fn) else None
            defs.append(
                {
                    "name": name,
                    "description": getattr(ex, "description", "") or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                }
            )
        return defs

    # ── approval ──────────────────────────────────────────────────────

    def _is_approved(self, name: str, args: Dict[str, Any], executor: Any) -> bool:
        if not getattr(executor, "needs_approval", lambda _a: False)(args):
            return True
        if self._approver is not None:
            return bool(self._approver(name, args))
        return self._auto_approve

    # ── run loop ──────────────────────────────────────────────────────

    def run(self, prompt: str, *, tool_sequence: Optional[List[Dict[str, Any]]] = None):
        """Run the LLM tool loop. ``tool_sequence`` is ignored — the model drives."""
        self.add_message(MessageRole.user, prompt)
        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
        tools = self._tool_defs()

        for _ in range(self._max_steps):
            response: LLMResponse = self._provider.chat(
                model=self._model,
                system=self._system_prompt,
                messages=messages,
                tools=tools,
                max_tokens=self._max_tokens,
            )

            if not response.tool_calls:
                reply = response.text or ""
                self.add_message(MessageRole.assistant, reply)
                return reply

            messages.append(
                {"role": "assistant", "content": response.text, "tool_calls": response.tool_calls}
            )

            for call in response.tool_calls:
                yield from self._run_tool_call(call, messages)

        reply = "[stopped: reached max_steps without a final answer]"
        self.add_message(MessageRole.assistant, reply)
        return reply

    def _run_tool_call(self, call: LLMToolCall, messages: List[Dict[str, Any]]):
        call_id = call.id or uuid.uuid4().hex[:12]
        args = call.args or {}
        executor = self._executors.get(call.name)

        yield ToolCallStartedEvent(call_id=call_id, tool_name=call.name, args=args)

        if executor is None:
            error = f"Unknown tool: {call.name}"
            yield ToolCallCompletedEvent(call_id=call_id, tool_name=call.name, result={}, error=error)
            self._record_result(messages, call_id, call.name, error)
            return

        if not self._is_approved(call.name, args, executor):
            error = "Tool call denied (requires approval)."
            yield ToolCallDeltaEvent(call_id=call_id, delta=error)
            yield ToolCallCompletedEvent(call_id=call_id, tool_name=call.name, result={}, error=error)
            self._record_result(messages, call_id, call.name, error)
            return

        yield ToolCallDeltaEvent(call_id=call_id, delta=f"Executing {call.name}...")

        try:
            result = _resolve(executor.execute(args, self._context))
        except Exception as exc:  # noqa: BLE001 — surface tool errors to the model
            error = str(exc)
            yield ToolCallCompletedEvent(call_id=call_id, tool_name=call.name, result={}, error=error)
            self._record_result(messages, call_id, call.name, f"Error: {error}")
            return

        yield ToolCallCompletedEvent(call_id=call_id, tool_name=call.name, result=result)
        self._record_result(messages, call_id, call.name, str(result))

    def _record_result(self, messages: List[Dict[str, Any]], call_id: str, name: str, content: str) -> None:
        self.add_message(MessageRole.tool, content=content, name=name, tool_call_id=call_id)
        messages.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": content})


__all__ = ["LLMAgent", "Approver"]
