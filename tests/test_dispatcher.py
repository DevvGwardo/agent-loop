"""Tests for ToolDispatcher — sync/async dispatch, registration, function wrapping, multi-call."""

from __future__ import annotations

import pytest

from agent_loop.dispatcher import ToolDispatcher
from agent_loop.exceptions import ToolNotFoundError, ToolExecutionError


def _echo_fn(msg: str = "hello") -> dict:
    return {"message": msg}


class TestDispatcherRegistration:
    """register(), register_func(), unregister(), tool_names, get_executor()."""

    def test_register_and_list(self) -> None:
        disp = ToolDispatcher()
        assert disp.tool_names == []

    def test_register_func_wraps_callable(self) -> None:
        disp = ToolDispatcher()
        disp.register_func("echo", _echo_fn)
        assert "echo" in disp.tool_names

    def test_unregister_removes_tool(self) -> None:
        disp = ToolDispatcher()
        disp.register_func("echo", _echo_fn)
        disp.unregister("echo")
        assert "echo" not in disp.tool_names

    def test_get_executor_returns_none_for_unknown(self) -> None:
        disp = ToolDispatcher()
        assert disp.get_executor("nope") is None


class TestDispatcherSyncExecute:
    """execute() — synchronous dispatch."""

    def test_unknown_tool_raises(self) -> None:
        disp = ToolDispatcher()
        with pytest.raises(ToolNotFoundError, match="nonexistent"):
            disp.execute("nonexistent", {})

    def test_func_tool_returns_result(self) -> None:
        disp = ToolDispatcher()
        disp.register_func("echo", _echo_fn)
        result = disp.execute("echo", {"msg": "world"})
        assert result["error"] is None
        # _echo_fn returns {"message": "world"} directly
        assert result["result"]["message"] == "world"

    def test_result_includes_duration_ms(self) -> None:
        disp = ToolDispatcher()
        disp.register_func("echo", _echo_fn)
        result = disp.execute("echo", {})
        assert isinstance(result["duration_ms"], float)
        assert result["duration_ms"] >= 0

    def test_exception_during_exec_raises(self) -> None:
        disp = ToolDispatcher()

        def _fail(**kw):
            raise ValueError("boom")

        disp.register_func("fail", _fail)
        with pytest.raises(ToolExecutionError, match="boom"):
            disp.execute("fail", {})


class TestDispatcherAsyncExecute:
    """execute_async() — async dispatch with timeout."""

    @pytest.mark.asyncio
    async def test_async_unknown_tool_raises(self) -> None:
        disp = ToolDispatcher()
        with pytest.raises(ToolNotFoundError):
            await disp.execute_async("nope", {})

    @pytest.mark.asyncio
    async def test_async_func_tool(self) -> None:
        disp = ToolDispatcher()
        disp.register_func("echo", _echo_fn)
        result = await disp.execute_async("echo", {"msg": "async"})
        assert result["error"] is None
        assert result["result"]["message"] == "async"


class TestDispatcherMultiCall:
    """execute_multi() — sequential and parallel dispatch."""

    def test_sequential_multi_empty(self) -> None:
        disp = ToolDispatcher()
        results = disp.execute_multi([])
        assert results == []

    def test_sequential_single_call(self) -> None:
        disp = ToolDispatcher()
        disp.register_func("echo", _echo_fn)
        results = disp.execute_multi(
            [{"tool_name": "echo", "args": {"msg": "x"}}],
            sequential=True,
        )
        assert len(results) == 1
        assert results[0]["error"] is None

    def test_sequential_multi_call_order(self) -> None:
        disp = ToolDispatcher()
        disp.register_func("echo", _echo_fn)
        results = disp.execute_multi(
            [
                {"tool_name": "echo", "args": {"msg": "first"}},
                {"tool_name": "echo", "args": {"msg": "second"}},
            ],
            sequential=True,
        )
        assert len(results) == 2
        assert results[0]["result"]["message"] == "first"
        assert results[1]["result"]["message"] == "second"

    def test_sequential_unknown_tool_raises(self) -> None:
        disp = ToolDispatcher()
        with pytest.raises(ToolNotFoundError):
            disp.execute_multi(
                [{"tool_name": "ghost", "args": {}}],
                sequential=True,
            )
