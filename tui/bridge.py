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
import sys
import time
from pathlib import Path

# Add agent-loop to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_loop import Agent
from agent_loop.tools.shell import ShellExecutor
from agent_loop.tools.read import ReadExecutor
from agent_loop.tools.edit import EditExecutor
from agent_loop.tools.web_fetch import WebFetchExecutor


def emit(obj: dict) -> None:
    """Write a JSON line to stdout, flush immediately."""
    print(json.dumps(obj), flush=True)


def main() -> None:
    agent = Agent(
        executors=[
            ShellExecutor(),
            ReadExecutor(),
            EditExecutor(),
            WebFetchExecutor(),
        ],
        system_prompt="You are cheekagent — a helpful AI coding agent running inside a terminal TUI.",
    )

    emit({"type": "ready", "tools": agent.tool_names})

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

        if msg_type == "prompt":
            text = msg.get("text", "")
            if not text:
                continue

            t0 = time.perf_counter()

            try:
                for event in agent.run(text):
                    match event:
                        case {"tool_name": tn, "call_id": cid, "args": a} if hasattr(event, "tool_name") and not hasattr(event, "delta") and not hasattr(event, "result"):
                            emit({"type": "started", "call_id": cid, "tool_name": tn, "args": a})
                        case {"call_id": cid, "delta": d} if hasattr(event, "delta"):
                            emit({"type": "delta", "call_id": cid, "delta": d})
                        case {"call_id": cid, "tool_name": tn, "result": r, "error": e} if hasattr(event, "result"):
                            emit({
                                "type": "completed",
                                "call_id": cid,
                                "tool_name": tn,
                                "result": r,
                                "error": e,
                                "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                            })
                # agent.run() returns the final reply
                emit({"type": "done"})
            except Exception as exc:
                emit({"type": "error", "message": str(exc)})

        else:
            emit({"type": "error", "message": f"Unknown message type: {msg_type}"})


if __name__ == "__main__":
    main()
