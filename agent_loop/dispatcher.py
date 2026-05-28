"""ToolDispatcher — maps tool names to executors and dispatches calls with error handling."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

from agent_loop.agent import ToolExecutor


def _generate_call_id() -> str:
    return uuid.uuid4().hex[:12]


def _resolve_async(coro) -> Any:
    """Block on a coroutine from a sync context, handling running loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
    return asyncio.run(coro)


class ToolDispatcher:
    """Maps tool names to executor instances and dispatches tool calls.

    Handles:
      - name → executor resolution
      - timeouts via the *default_timeout* parameter
      - errors wrapped in result dicts
      - sync and async executors
    """

    def __init__(self, default_timeout: float = 30.0) -> None:
        self._executors: Dict[str, ToolExecutor] = {}
        self._default_timeout = default_timeout

    # ── registration ──────────────────────────────────────────────────

    def register(self, executor: ToolExecutor, *, name: Optional[str] = None) -> None:
        key = name or executor.name
        if key in self._executors:
            raise ValueError(f"A tool is already registered under '{key}'")
        self._executors[key] = executor

    def register_func(
        self,
        name: str,
        fn: Callable[..., Any],
        *,
        timeout: Optional[float] = None,
    ) -> None:
        """Register a plain function as a tool executor."""
        self._executors[name] = _FuncExecutor(name=name, fn=fn, timeout=timeout or self._default_timeout)

    def unregister(self, name: str) -> None:
        self._executors.pop(name, None)

    @property
    def tool_names(self) -> List[str]:
        return list(self._executors.keys())

    def get_executor(self, name: str) -> Optional[ToolExecutor]:
        return self._executors.get(name)

    # ── dispatch ──────────────────────────────────────────────────────

    def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Synchronously dispatch a tool call.

        Returns a dict with keys:
          - result (dict): the executor's output on success
          - error (str | None): error message on failure
          - duration_ms (float): wall-clock execution time in ms
        """
        executor = self._executors.get(tool_name)
        if executor is None:
            return {
                "result": {},
                "error": f"Unknown tool: '{tool_name}'",
                "duration_ms": 0.0,
            }

        call_id = _generate_call_id()
        start = time.monotonic()
        try:
            raw = executor.execute(call_id, args)
            if asyncio.iscoroutine(raw):
                raw = _resolve_async(raw)
            result = raw if isinstance(raw, dict) else {"output": raw}
            elapsed = (time.monotonic() - start) * 1000
            return {"result": result, "error": None, "duration_ms": elapsed}
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return {"result": {}, "error": str(exc), "duration_ms": elapsed}

    async def execute_async(
        self,
        tool_name: str,
        args: Dict[str, Any],
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Asynchronously dispatch a tool call with timeout support."""
        executor = self._executors.get(tool_name)
        if executor is None:
            return {
                "result": {},
                "error": f"Unknown tool: '{tool_name}'",
                "duration_ms": 0.0,
            }

        effective_timeout = timeout or self._default_timeout
        call_id = _generate_call_id()
        start = time.monotonic()

        try:
            raw = executor.execute(call_id, args)
            if asyncio.iscoroutine(raw):
                result = await asyncio.wait_for(raw, timeout=effective_timeout)
            else:
                result = raw
            result = result if isinstance(result, dict) else {"output": result}

            elapsed = (time.monotonic() - start) * 1000
            return {"result": result, "error": None, "duration_ms": elapsed}

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return {
                "result": {},
                "error": f"Tool '{tool_name}' timed out after {effective_timeout}s",
                "duration_ms": elapsed,
            }
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            return {"result": {}, "error": str(exc), "duration_ms": elapsed}

    def execute_multi(
        self,
        calls: List[Dict[str, Any]],
        *,
        timeout: Optional[float] = None,
        sequential: bool = False,
    ) -> List[Dict[str, Any]]:
        """Dispatch multiple tool calls.

        Each element of *calls* should have:
          - tool_name (str)
          - args (dict)

        Returns a list of result dicts in the same order as *calls*.
        """
        if sequential:
            return [self.execute(c["tool_name"], c.get("args", {}), timeout=timeout) for c in calls]

        # Parallel dispatch via asyncio
        async def _run_all() -> List[Dict[str, Any]]:
            tasks = [
                self.execute_async(c["tool_name"], c.get("args", {}), timeout=timeout)
                for c in calls
            ]
            return await asyncio.gather(*tasks, return_exceptions=False)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're already in an event loop — run sequentially
                return [self.execute(c["tool_name"], c.get("args", {}), timeout=timeout) for c in calls]
            return loop.run_until_complete(_run_all())
        except RuntimeError:
            return [self.execute(c["tool_name"], c.get("args", {}), timeout=timeout) for c in calls]


# ── Internal helper: wrap a plain function as a ToolExecutor ──────────


class _FuncExecutor:
    """Adapter that wraps a plain callable as a ToolExecutor."""

    def __init__(self, name: str, fn: Callable[..., Any], timeout: float) -> None:
        self._name = name
        self._fn = fn
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    def execute(self, call_id: str, args: Dict[str, Any]) -> Any:
        result = self._fn(**args)
        if asyncio.iscoroutine(result):
            return result
        if isinstance(result, dict):
            return result
        return {"output": result}


__all__ = ["ToolDispatcher"]
