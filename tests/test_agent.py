"""Tests for the Agent class — run loop, tool registration, dispatch, error handling."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from agent_loop.agent import Agent
from agent_loop.models import (
    ToolCallCompletedEvent,
    ToolCallDeltaEvent,
    ToolCallStartedEvent,
)


# ── Mock executor helpers ─────────────────────────────────────────────


class _MockExecutor:
    """Minimal ToolExecutor-compatible stub for testing."""

    def __init__(self, name: str, *, fail: bool = False) -> None:
        self._name = name
        self._fail = fail
        self.executed_calls: list[tuple[str, dict]] = []

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, args: dict | None = None, context: dict | None = None) -> Dict[str, Any]:
        self.executed_calls.append((str(args), args or {}))
        if self._fail:
            raise RuntimeError(f"{self._name} failed deliberately")
        return {"success": True, "output": f"{self._name} executed: {args!r}"}


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def shell_exec() -> _MockExecutor:
    return _MockExecutor("shell")


@pytest.fixture
def read_exec() -> _MockExecutor:
    return _MockExecutor("read")


@pytest.fixture
def failing_exec() -> _MockExecutor:
    return _MockExecutor("bomb", fail=True)


@pytest.fixture
def agent(shell_exec: _MockExecutor, read_exec: _MockExecutor) -> Agent:
    return Agent(executors=[shell_exec, read_exec])


# ── Tests ─────────────────────────────────────────────────────────────


class TestAgentRunLoop:
    """Agent.run() yields the correct sequence of streaming events."""

    def test_yields_events_for_tool_sequence(self, agent: Agent) -> None:
        events = list(
            agent.run(
                "do something",
                tool_sequence=[
                    {"tool": "shell", "args": {"command": "echo hello"}},
                ],
            )
        )
        # Should yield: started, delta, completed
        assert len(events) == 3
        assert isinstance(events[0], ToolCallStartedEvent)
        assert events[0].tool_name == "shell"
        assert isinstance(events[1], ToolCallDeltaEvent)
        assert events[1].call_id == events[0].call_id
        assert isinstance(events[2], ToolCallCompletedEvent)
        assert events[2].tool_name == "shell"
        assert events[2].result["success"] is True

    def test_empty_tool_sequence(self, agent: Agent) -> None:
        events = list(agent.run("just talk"))
        assert events == []  # no tool calls → no events

    def test_multiple_tools_in_sequence(self, agent: Agent) -> None:
        events = list(
            agent.run(
                "do two things",
                tool_sequence=[
                    {"tool": "shell", "args": {"command": "echo a"}},
                    {"tool": "read", "args": {"path": "foo.txt"}},
                ],
            )
        )
        assert len(events) == 6  # 3 events per tool
        assert events[0].tool_name == "shell"
        assert events[3].tool_name == "read"


class TestToolRegistration:
    """register_tool / unregister_tool / tool_names."""

    def test_register_new_tool(self) -> None:
        agent = Agent()
        exec_ = _MockExecutor("my_tool")
        agent.register_tool(exec_)
        assert "my_tool" in agent.tool_names

    def test_register_duplicate_raises(self) -> None:
        agent = Agent(executors=[_MockExecutor("dup")])
        with pytest.raises(ValueError, match="already registered"):
            agent.register_tool(_MockExecutor("dup"))

    def test_unregister_tool(self, agent: Agent) -> None:
        agent.unregister_tool("shell")
        assert "shell" not in agent.tool_names
        assert "read" in agent.tool_names

    def test_get_executor(self, agent: Agent) -> None:
        exec_ = agent.get_executor("shell")
        assert exec_ is not None
        assert exec_.name == "shell"
        assert agent.get_executor("nope") is None


class TestToolDispatch:
    """Tool execution dispatch via run()."""

    def test_dispatch_executes_correct_tool(
        self, agent: Agent, shell_exec: _MockExecutor
    ) -> None:
        list(agent.run("x", tool_sequence=[{"tool": "shell", "args": {"cmd": "hi"}}]))
        assert len(shell_exec.executed_calls) == 1
        call_id, args = shell_exec.executed_calls[0]
        assert args == {"cmd": "hi"}
        assert isinstance(call_id, str)

    def test_unknown_tool_yields_error_event(self, agent: Agent) -> None:
        events = list(
            agent.run("x", tool_sequence=[{"tool": "nonexistent", "args": {}}])
        )
        assert len(events) == 1
        assert isinstance(events[0], ToolCallCompletedEvent)
        assert events[0].error is not None
        assert "nonexistent" in events[0].error


class TestErrorHandling:
    """Agent gracefully handles executor failures."""

    def test_failing_executor_yields_error_event(
        self, failing_exec: _MockExecutor
    ) -> None:
        agent = Agent(executors=[failing_exec])
        events = list(
            agent.run("x", tool_sequence=[{"tool": "bomb", "args": {}}])
        )
        # started, delta, completed (with error)
        assert len(events) == 3
        assert isinstance(events[2], ToolCallCompletedEvent)
        assert events[2].error is not None
        assert "deliberately" in events[2].error

    def test_history_updated_on_error(self, failing_exec: _MockExecutor) -> None:
        agent = Agent(executors=[failing_exec])
        list(agent.run("x", tool_sequence=[{"tool": "bomb", "args": {}}]))
        assert len(agent.history) >= 1
        last_msg = agent.history[-1]
        assert "Error" in last_msg.content or "bomb" in last_msg.content


class TestHistory:
    """Agent history management."""

    def test_add_and_clear_history(self, agent: Agent) -> None:
        agent.add_message("user", "hello")
        assert len(agent.history) == 1
        agent.clear_history()
        assert len(agent.history) == 0

    def test_history_contains_messages_from_run(self, agent: Agent) -> None:
        list(
            agent.run("test", tool_sequence=[{"tool": "shell", "args": {"cmd": "ls"}}])
        )
        # user message + tool result + assistant reply
        assert len(agent.history) >= 3
        assert agent.history[0].role == "user"
        assert agent.history[0].content == "test"
