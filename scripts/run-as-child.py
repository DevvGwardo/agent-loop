#!/usr/bin/env python3
"""
agent-loop child agent bridge.

Reads a task from stdin (JSON), runs agent-loop's Agent with the
configured tool set, and outputs streaming events as NDJSON
(newline-delimited JSON) to stdout.

Usage:
  echo '{"task": "list files in ~/", "tools": ["shell", "read"]}' | \
    python3 run-as-child.py

Each line of stdout is a streaming event:
  {"type": "tool_started", "tool": "shell", "id": "call_1"}
  {"type": "tool_delta", "tool": "shell", "id": "call_1", "data": "..."}
  {"type": "tool_completed", "tool": "shell", "id": "call_1", "result": {...}}
  {"type": "done", "summary": "...", "history": [...]}

Designed to be called from Hermes via:
  terminal(background=true, command="... | python3 run-as-child.py")
  process(action='log')  # reads the streaming output
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

# Ensure agent-loop is importable
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from agent_loop.harness import CodingAgentHarness
from agent_loop.llm import OpenAICompatibleChatClient
from agent_loop.master_loop import LoopLifecycleEvent, MasterLoopHarness, MissionLoopSpec
from agent_loop.mcp import load_mcp_config
from agent_loop.models import ToolCallCompletedEvent, ToolCallDeltaEvent, ToolCallStartedEvent
from agent_loop.tools import (
    EditExecutor,
    GrepExecutor,
    GlobExecutor,
    PlanExecutor,
    ReadExecutor,
    ShellExecutor,
    WebFetchExecutor,
    WebSearchExecutor,
)


def emit(event: dict) -> None:
    """Write a JSON event to stdout and flush immediately."""
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def main() -> None:
    # Read input
    raw = sys.stdin.read()
    if not raw:
        emit({"type": "error", "message": "No input received"})
        sys.exit(1)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        emit({"type": "error", "message": f"Invalid JSON: {e}"})
        sys.exit(1)

    task = payload.get("task") or payload.get("objective") or payload.get("text") or ""
    if not task:
        emit({"type": "error", "message": "Missing 'task' field"})
        sys.exit(1)

    tool_names = payload.get("tools", ["shell", "read", "edit", "grep", "glob", "update_plan"])
    working_dir = payload.get("working_directory")

    executor_map = {
        "shell": ShellExecutor,
        "read": ReadExecutor,
        "edit": EditExecutor,
        "grep": GrepExecutor,
        "glob": GlobExecutor,
        "web_fetch": WebFetchExecutor,
        "web_search": WebSearchExecutor,
        "update_plan": PlanExecutor,
    }

    executors = []
    for name in tool_names:
        cls = executor_map.get(name)
        if cls:
            executors.append(cls())
        else:
            emit({"type": "warn", "message": f"Unknown tool: {name}, skipping"})

    if not executors:
        emit({"type": "error", "message": "No valid tools configured"})
        sys.exit(1)

    model_client = None
    model = payload.get("model") or None
    if model:
        model_client = OpenAICompatibleChatClient(
            model=model,
            api_key=payload.get("api_key"),
            base_url=payload.get("base_url", "https://api.openai.com/v1"),
            timeout=float(payload.get("model_timeout", 120)),
        )

    mcp_cache, mcp_instructions, mcp_client = load_mcp_config()
    harness = CodingAgentHarness(
        model_client=model_client,
        executors=executors,
        working_directory=working_dir,
        max_iterations=int(payload.get("max_iterations", 8)),
        mcp_cache=mcp_cache if mcp_cache.tools else None,
        mcp_client=mcp_client,
        mcp_instructions=mcp_instructions,
        permission_mode=payload.get("permission_mode", "workspace"),
    )
    master_loop = MasterLoopHarness(harness)

    def emit_stream_event(event: object) -> None:
        if isinstance(event, LoopLifecycleEvent):
            emit({
                "type": "loop_event",
                "event": event.event_type,
                "node": event.node,
                "snapshot": event.snapshot,
                "message": event.message,
            })
        elif isinstance(event, ToolCallStartedEvent):
            emit({
                "type": "tool_started",
                "tool": event.tool_name,
                "id": event.call_id,
                "args": event.args,
            })
        elif isinstance(event, ToolCallDeltaEvent):
            emit({
                "type": "tool_delta",
                "id": event.call_id,
                "data": event.delta,
            })
        elif isinstance(event, ToolCallCompletedEvent):
            emit({
                "type": "tool_completed",
                "tool": event.tool_name,
                "id": event.call_id,
                "result": event.result,
                "error": event.error,
            })

    # Run the task and stream events
    def run_task():
        tool_sequence = payload.get("tool_sequence")
        mission_mode = (
            payload.get("mode") == "mission"
            or payload.get("mission") is True
            or "goals" in payload
        )

        if mission_mode:
            mission_payload = dict(payload)
            mission_payload.setdefault("objective", task)
            if tool_sequence is not None and not mission_payload.get("goals"):
                mission_payload["goals"] = [
                    {
                        "name": "primary-goal",
                        "objective": task,
                        "agents": [
                            {
                                "name": "primary-agent",
                                "workflows": [
                                    {
                                        "name": "execute",
                                        "tool_sequence": tool_sequence,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            runner = master_loop.run(MissionLoopSpec.from_json(mission_payload))
        elif tool_sequence is None and model_client is None:
            if "shell" not in harness.tool_names:
                emit({
                    "type": "error",
                    "message": "No model configured and shell fallback is unavailable",
                })
                return
            tool_sequence = [{"tool": "shell", "args": {"command": task}, "call_id": "call_1"}]
            runner = harness.run_tool_sequence(task, tool_sequence)
        else:
            runner = (
                harness.run_tool_sequence(task, tool_sequence)
                if tool_sequence is not None
                else harness.run(task)
            )

        summary = ""
        while True:
            try:
                event = next(runner)
            except StopIteration as done:
                summary = done.value or ""
                break

            emit_stream_event(event)

        emit({
            "type": "done",
            "summary": summary or f"Task completed: {task}",
            "history": harness.messages,
            "loop_snapshot": master_loop.snapshot(),
        })

    run_task()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        emit({"type": "error", "message": f"Unhandled exception: {e}\n{traceback.format_exc()}"})
        sys.exit(1)
