"""Basic agent example — creates an Agent with ShellExecutor and ReadExecutor and runs a prompt.

Usage:
    python examples/basic_agent.py

This demonstrates the streaming event pattern:
    ToolCallStartedEvent → ToolCallDeltaEvent → ToolCallCompletedEvent
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from agent_loop.agent import Agent
from agent_loop.models import (
    ToolCallCompletedEvent,
    ToolCallDeltaEvent,
    ToolCallStartedEvent,
)


# ── Sync executor wrappers (Agent protocol expects async) ─────────────


class SimpleShellExecutor:
    """Minimal shell executor for the example (runs via asyncio.create_subprocess_shell)."""

    @property
    def name(self) -> str:
        return "shell"

    async def execute(self, call_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        command: str = args.get("command", "")
        if not command:
            return {"success": False, "error": "No command provided"}

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode or 0,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }


class SimpleReadExecutor:
    """Minimal file reader for the example."""

    @property
    def name(self) -> str:
        return "read"

    async def execute(self, call_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        path: str = args.get("path", "")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"success": True, "content": content, "total_lines": content.count("\n")}
        except FileNotFoundError:
            return {"success": False, "error": f"File not found: {path}"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


def main() -> None:
    # Create the agent with two tools
    agent = Agent(
        executors=[SimpleShellExecutor(), SimpleReadExecutor()],
        system_prompt="You are a helpful coding agent.",
    )

    prompt = "List files in the current directory and then read this script."
    print(f"Prompt: {prompt!r}\n")
    print("Events:")

    gen = agent.run(
        prompt,
        tool_sequence=[
            {"tool": "shell", "args": {"command": "ls -la"}},
            {"tool": "read", "args": {"path": __file__}},
        ],
    )

    final_reply = ""
    while True:
        try:
            event = next(gen)
        except StopIteration as exc:
            final_reply = exc.value
            break

        match event:
            case ToolCallStartedEvent():
                print(f"  [START]  {event.tool_name}  call_id={event.call_id}")
            case ToolCallDeltaEvent():
                print(f"  [DELTA]  {event.delta}")
            case ToolCallCompletedEvent():
                status = "OK" if event.error is None else f"ERROR: {event.error}"
                print(f"  [DONE]   {event.tool_name}  {status}")

    print(f"\nFinal reply:\n{final_reply}")


if __name__ == "__main__":
    main()
