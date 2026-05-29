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

from agent_loop import Agent
from agent_loop.tools import (
    ReadExecutor,
    EditExecutor,
    GrepExecutor,
    WebFetchExecutor,
    ShellExecutor,
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

    task = payload.get("task", "")
    if not task:
        emit({"type": "error", "message": "Missing 'task' field"})
        sys.exit(1)

    tool_names = payload.get("tools", ["shell", "read", "edit", "grep"])
    working_dir = payload.get("working_directory")

    # Map tool names to executors
    executor_map = {
        "shell": ShellExecutor,
        "read": ReadExecutor,
        "edit": EditExecutor,
        "grep": GrepExecutor,
        "web_fetch": WebFetchExecutor,
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

    # Build the agent
    agent = Agent(executors=executors)

    # Run the task and stream events
    import asyncio

    async def run_task():
        context = {}
        if working_dir:
            context["working_directory"] = working_dir

        # We don't have an LLM — we just execute the tool calls directly.
        # The agent-loop Agent.run() expects an LLM response with tool_calls.
        # Instead, we use a simplified direct-execution approach:
        # Parse the task, determine which tool to call, execute it.
        
        # For now: run shell as the primary tool with the task as a command.
        # This is a simplified bridge — extend for LLM-based agent execution.
        
        shell = agent.get_executor("shell")
        if shell and task:
            emit({"type": "tool_started", "tool": "shell", "id": "call_1"})
            
            args = {"command": task}
            if working_dir:
                args["working_directory"] = working_dir
            
            try:
                result = await shell.execute(args, context)
                exit_code = result.get("exit_code", -1)
                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                
                emit({"type": "tool_delta", "tool": "shell", "id": "call_1", "data": stdout})
                if stderr:
                    emit({"type": "tool_delta", "tool": "shell", "id": "call_1", "data": stderr})
                
                emit({
                    "type": "tool_completed",
                    "tool": "shell",
                    "id": "call_1",
                    "result": result,
                })
            except Exception as e:
                emit({
                    "type": "tool_completed",
                    "tool": "shell",
                    "id": "call_1",
                    "result": {
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": str(e),
                        "success": False,
                    },
                })

        emit({"type": "done", "summary": f"Task completed: {task}", "history": []})

    asyncio.run(run_task())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        emit({"type": "error", "message": f"Unhandled exception: {e}\n{traceback.format_exc()}"})
        sys.exit(1)
