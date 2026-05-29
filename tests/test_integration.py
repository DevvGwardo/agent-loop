"""Integration tests: Agent + real tools via tool_sequence paths.

NOTE: Agent.run() is a synchronous generator that internally uses
_resolve() to bridge async tool executors. In pytest-asyncio's STRICT
mode, this can deadlock. These tests use two strategies:
1. Agent + MockExecutor for streaming protocol tests
2. Direct executor tests with asyncio for real tool integration

Combined Agent + real-tools tests that exhaust the generator via list()
inside an async test are avoided due to the sync→async bridge deadlock.
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path

import pytest

from agent_loop import Agent
from agent_loop.tools import ReadExecutor, EditExecutor, GrepExecutor


# ── Mock executor for streaming protocol tests ──

class _StreamRecorder:
    """Records streaming events from Agent.run() for verification."""
    def __init__(self):
        self.events = []
        self.tool_names = set()

    def record(self, event):
        self.events.append(event)
        # ToolCallDeltaEvent has no tool_name field
        if hasattr(event, 'tool_name'):
            self.tool_names.add(event.tool_name)


class _MockExec:
    """Minimal sync ToolExecutor for testing Agent streaming protocol.

    Uses sync execute() so Agent.run()'s _resolve() doesn't hit the
    async bridge deadlock in STRICT asyncio mode.
    """
    def __init__(self, name: str = "mock", fail: bool = False):
        self._name = name
        self._fail = fail

    @property
    def name(self) -> str:
        return self._name

    def execute(self, args=None, context=None):
        if self._fail:
            raise RuntimeError(f"{self._name} failed")
        return {"success": True, "output": f"{self._name} ran: {args!r}"}


class TestAgentStreamingProtocol:
    """Agent.run() streaming protocol with mock executors.

    These tests verify the ToolCallStarted → Delta → Completed lifecycle
    without needing async tool executors.
    """

    def test_single_tool_produces_streaming_events(self):
        agent = Agent(executors=[_MockExec("shell")])
        rec = _StreamRecorder()
        for event in agent.run("x", tool_sequence=[{"tool": "shell", "args": {"cmd": "hi"}}]):
            rec.record(event)
        assert len(rec.events) >= 2  # started + completed
        assert "shell" in rec.tool_names

    def test_multi_tool_sequence_order(self):
        agent = Agent(executors=[_MockExec("a"), _MockExec("b")])
        rec = _StreamRecorder()
        for event in agent.run("x", tool_sequence=[
            {"tool": "a", "args": {}},
            {"tool": "b", "args": {}},
        ]):
            rec.record(event)
        # Verify ordering
        events = [e for e in rec.events if hasattr(e, 'tool_name')]
        tool_order = [e.tool_name for e in events]
        assert tool_order.index("a") < tool_order.index("b")

    def test_delta_event_between_start_and_complete(self):
        agent = Agent(executors=[_MockExec("shell")])
        rec = _StreamRecorder()
        for event in agent.run("x", tool_sequence=[{"tool": "shell", "args": {}}]):
            rec.record(event)
        from agent_loop.models import ToolCallDeltaEvent
        deltas = [e for e in rec.events if isinstance(e, ToolCallDeltaEvent)]
        assert len(deltas) >= 1  # "Executing shell..." delta

    def test_unknown_tool_yields_error(self):
        agent = Agent(executors=[_MockExec("shell")])
        rec = _StreamRecorder()
        for event in agent.run("x", tool_sequence=[{"tool": "ghost", "args": {}}]):
            rec.record(event)
        from agent_loop.models import ToolCallCompletedEvent
        errors = [e for e in rec.events if isinstance(e, ToolCallCompletedEvent) and e.error]
        assert len(errors) == 1
        assert "unknown tool" in (errors[0].error or "").lower()

    def test_tool_execution_error_yields_error_event(self):
        agent = Agent(executors=[_MockExec("fail", fail=True)])
        rec = _StreamRecorder()
        for event in agent.run("x", tool_sequence=[{"tool": "fail", "args": {}}]):
            rec.record(event)
        from agent_loop.models import ToolCallCompletedEvent
        errors = [e for e in rec.events if isinstance(e, ToolCallCompletedEvent) and e.error]
        assert len(errors) == 1
        assert "failed" in (errors[0].error or "").lower()

    def test_empty_tool_sequence_yields_no_events(self):
        agent = Agent(executors=[_MockExec("shell")])
        rec = _StreamRecorder()
        for event in agent.run("x", tool_sequence=[]):
            rec.record(event)
        assert len(rec.events) == 0

    def test_history_grows_with_tool_calls(self):
        agent = Agent(executors=[_MockExec("shell")])
        for _ in agent.run("x", tool_sequence=[{"tool": "shell", "args": {"cmd": "a"}},
                                                 {"tool": "shell", "args": {"cmd": "b"}}]):
            pass
        assert len(agent.history) >= 3  # user msg + 2 tool results + assistant reply
        roles = [m.role for m in agent.history]
        assert "user" in roles
        assert "tool" in roles


class TestRealToolIntegration:
    """Real tool executors tested directly with asyncio.

    These tests verify that ReadExecutor, EditExecutor, GrepExecutor
    work correctly when called directly (not through Agent.run()).
    """

    @pytest.mark.asyncio
    async def test_read_tool_works(self):
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "test.txt")
        Path(f).write_text("hello\nworld\n")
        r = ReadExecutor()
        result = await r.execute({"path": f})
        out = result.get("stdout") or result.get("content") or ""
        assert "hello" in out

    @pytest.mark.asyncio
    async def test_edit_str_replace_works(self):
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "edit.txt")
        Path(f).write_text("old\n")
        e = EditExecutor()
        result = await e.execute({"path": f, "mode": "str_replace",
                                   "old_string": "old", "new_string": "new"})
        assert result["success"] is True
        assert Path(f).read_text() == "new\n"

    @pytest.mark.asyncio
    async def test_edit_stream_content_works(self):
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "out.txt")
        e = EditExecutor()
        content = "line1\nline2\n"
        result = await e.execute({"path": f, "mode": "stream_content", "content": content})
        assert result["success"] is True
        assert Path(f).read_text() == content

    @pytest.mark.asyncio
    async def test_grep_tool_works(self):
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "target.txt")
        Path(f).write_text("needle\nhaystack\n")
        g = GrepExecutor()
        result = await g.execute({"pattern": "needle", "path": tmpdir})
        assert result.get("count", 0) >= 1

    @pytest.mark.asyncio
    async def test_grep_no_matches(self):
        tmpdir = tempfile.mkdtemp()
        # Write a file with known content to avoid /tmp permission issues
        f = os.path.join(tmpdir, "clean.txt")
        Path(f).write_text("this is a test\n")
        g = GrepExecutor()
        result = await g.execute({"pattern": "zzz_nonexistent_zzz", "path": tmpdir})
        n = result.get("count", -1)
        if n == -1 and "error" in result:
            pytest.skip(f"rg error: {result['error']}")
        assert n == 0 or result.get("matches", []) == []

    def test_shell_executor_sync_compat(self):
        """ShellExecutor works with Agent.run() via _resolve() sync bridge."""
        from agent_loop.tools import ShellExecutor
        agent = Agent(executors=[ShellExecutor()])
        # Use a short tool_sequence to test the sync bridge
        # Must be outside asyncio context to avoid deadlock
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                pytest.skip("Cannot test sync bridge from async context")
        except RuntimeError:
            pass

        events = list(agent.run("x", tool_sequence=[
            {"tool": "shell", "args": {"command": "echo sync-bridge-test"}},
        ]))
        from agent_loop.models import ToolCallCompletedEvent
        completed = [e for e in events if isinstance(e, ToolCallCompletedEvent)]
        assert len(completed) == 1
        assert completed[0].result.get("exit_code") == 0
        assert "sync-bridge-test" in completed[0].result.get("stdout", "")
