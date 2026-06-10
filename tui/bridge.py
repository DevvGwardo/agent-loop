#!/usr/bin/env python3
"""Bridge: reads JSON prompts from stdin, runs agent-loop, emits JSON events to stdout.

Protocol (stdin → stdout):
  ← {"type":"prompt","text":"list files"}
  → {"type":"started","call_id":"abc","tool_name":"shell","args":{...}}
  → {"type":"delta","call_id":"abc","delta":"Executing shell..."}
  → {"type":"completed","call_id":"abc","tool_name":"shell","result":{...},"error":null,"duration_ms":12.5}
  → {"type":"reply","text":"..."}
  → {"type":"done"}

Special commands:
  ← {"type":"exit"}   → process exits cleanly
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Add agent-loop to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_loop.harness import CodingAgentHarness
from agent_loop.llm import OpenAICompatibleChatClient
from agent_loop.master_loop import LoopLifecycleEvent, MasterLoopHarness, MissionLoopSpec
from agent_loop.mcp import load_mcp_config
from agent_loop.models import ToolCallCompletedEvent, ToolCallDeltaEvent, ToolCallStartedEvent
from agent_loop.session import PermissionMode


def emit(obj: dict) -> None:
    """Write a JSON line to stdout, flush immediately."""
    print(json.dumps(obj), flush=True)


def emit_stream_event(event: object, *, started_at: float) -> None:
    if isinstance(event, LoopLifecycleEvent):
        emit({
            "type": "loop",
            "event": event.event_type,
            "node": event.node,
            "snapshot": event.snapshot,
            "message": event.message,
        })
    elif isinstance(event, ToolCallStartedEvent):
        emit({
            "type": "started",
            "call_id": event.call_id,
            "tool_name": event.tool_name,
            "args": event.args,
        })
    elif isinstance(event, ToolCallDeltaEvent):
        emit({"type": "delta", "call_id": event.call_id, "delta": event.delta})
    elif isinstance(event, ToolCallCompletedEvent):
        emit({
            "type": "completed",
            "call_id": event.call_id,
            "tool_name": event.tool_name,
            "result": event.result,
            "error": event.error,
            "duration_ms": round((time.perf_counter() - started_at) * 1000, 1),
        })


def main() -> None:
    model_name = os.environ.get("AGENT_LOOP_MODEL")
    model_client = (
        OpenAICompatibleChatClient(
            model=model_name,
            base_url=os.environ.get("AGENT_LOOP_BASE_URL", "https://api.openai.com/v1"),
        )
        if model_name
        else None
    )
    mcp_cache, mcp_instructions, mcp_client = load_mcp_config()
    permission_mode = os.environ.get("AGENT_LOOP_PERMISSION_MODE", PermissionMode.WORKSPACE.value)
    harness = CodingAgentHarness(
        model_client=model_client,
        working_directory=os.environ.get("AGENT_LOOP_WORKDIR", os.getcwd()),
        system_prompt="You are cheekagent, a helpful coding agent running inside a terminal TUI.",
        mcp_cache=mcp_cache if mcp_cache.tools else None,
        mcp_client=mcp_client,
        mcp_instructions=mcp_instructions,
        permission_mode=permission_mode,
    )
    master_loop = MasterLoopHarness(harness)

    emit({"type": "ready", "tools": harness.tool_names, "loop_snapshot": master_loop.snapshot()})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            emit({"type": "error", "message": f"Invalid JSON: {line[:100]}"})
            continue

        msg_type = msg.get("type", "")

        if msg_type == "exit":
            emit({"type": "bye"})
            break

        if msg_type in {"prompt", "mission"}:
            text = msg.get("text", "")
            if not text:
                continue
            run_as_mission = msg_type == "mission" or text.startswith("/mission ")
            if text.startswith("/mission "):
                text = text.removeprefix("/mission ").strip()

            t0 = time.perf_counter()

            try:
                if run_as_mission:
                    spec = MissionLoopSpec(
                        objective=text,
                        max_cycles=int(os.environ.get("AGENT_LOOP_MISSION_CYCLES", "1")),
                        perpetual=os.environ.get("AGENT_LOOP_PERPETUAL", "").lower()
                        in {"1", "true", "yes"},
                    )
                    runner = master_loop.run(spec)
                elif text.startswith("/shell "):
                    runner = harness.run_tool_sequence(
                        text,
                        [{"tool": "shell", "args": {"command": text.removeprefix("/shell ").strip()}}],
                    )
                elif model_client is not None:
                    runner = harness.run(text)
                else:
                    emit({
                        "type": "error",
                        "message": "Set AGENT_LOOP_MODEL for model-driven coding, or use /shell <command>.",
                    })
                    continue

                while True:
                    try:
                        event = next(runner)
                    except StopIteration as done:
                        if done.value:
                            emit({"type": "reply", "text": str(done.value)})
                        break

                    emit_stream_event(event, started_at=t0)

                emit({"type": "done"})
            except Exception as exc:
                emit({"type": "error", "message": str(exc)})

        else:
            emit({"type": "error", "message": f"Unknown message type: {msg_type}"})


if __name__ == "__main__":
    main()
