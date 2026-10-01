import { spawn, ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { useEffect, useRef, useState, useCallback } from "react";
import type {
  AgentEvent,
  ToolCallState,
  Turn,
  StartedEvent,
  DeltaEvent,
  CompletedEvent,
  LoopEvent,
  LoopSnapshot,
  ReplyEvent,
} from "./types.js";

// bridge.py lives at tui/bridge.py. The depth from this module differs between
// the tsx dev build (tui/src/) and the compiled build (tui/dist/src/), so walk
// up from here until we find it instead of hard-coding a relative depth.
function resolveBridge(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let i = 0; i < 6; i++) {
    const candidate = join(dir, "bridge.py");
    if (existsSync(candidate)) return candidate;
    dir = dirname(dir);
  }
  // Fall back to the original relative guess.
  return new URL("../../bridge.py", import.meta.url).pathname;
}

const BRIDGE_SCRIPT = resolveBridge();

export function useBridge() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [ready, setReady] = useState(false);
  const [tools, setTools] = useState<string[]>([]);
  const [model, setModel] = useState<string>("none");
  const [busy, setBusy] = useState(false);
  const [loopSnapshot, setLoopSnapshot] = useState<LoopSnapshot | null>(null);
  const procRef = useRef<ChildProcess | null>(null);
  const bufferRef = useRef("");
  const currentTurnRef = useRef<Turn | null>(null);

  // Start the Python bridge process
  useEffect(() => {
    const proc = spawn("python3", [BRIDGE_SCRIPT], {
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });

    procRef.current = proc;

    proc.stderr?.on("data", (data: Buffer) => {
      // Forward stderr to our stderr for debugging
      process.stderr.write(data);
    });

    proc.stdout?.on("data", (data: Buffer) => {
      bufferRef.current += data.toString();

      // Process complete JSON lines
      const lines = bufferRef.current.split("\n");
      bufferRef.current = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const event: AgentEvent = JSON.parse(line);
          handleEvent(event);
        } catch {
          // skip malformed lines
        }
      }
    });

    proc.on("exit", (code) => {
      setReady(false);
      if (code !== 0) {
        setTurns((prev) => {
          const last = prev[prev.length - 1];
          if (last && !last.done) {
            last.error = `Bridge exited with code ${code}`;
            last.done = true;
            return [...prev.slice(0, -1), { ...last }];
          }
          return prev;
        });
      }
    });

    return () => {
      proc.kill();
    };
  }, []);

  function handleEvent(event: AgentEvent) {
    switch (event.type) {
      case "ready": {
        setReady(true);
        setTools(event.tools);
        setModel((event as { model?: string }).model ?? "none");
        setLoopSnapshot(event.loop_snapshot ?? null);
        break;
      }
      case "config": {
        setModel((event as { model?: string }).model ?? "none");
        break;
      }
      case "loop": {
        const le = event as LoopEvent;
        setLoopSnapshot(le.snapshot);
        break;
      }
      case "reply": {
        const re = event as ReplyEvent;
        if (currentTurnRef.current) {
          currentTurnRef.current.reply = re.text;
          setTurns((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { ...currentTurnRef.current! };
            return updated;
          });
        }
        break;
      }
      case "started": {
        const se = event as StartedEvent;
        const tc: ToolCallState = {
          call_id: se.call_id,
          tool_name: se.tool_name,
          args: se.args,
          deltas: [],
          result: null,
          error: null,
          duration_ms: 0,
          expanded: false,
          status: "running",
        };
        if (currentTurnRef.current) {
          currentTurnRef.current.toolCalls.push(tc);
          setTurns((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { ...currentTurnRef.current! };
            return updated;
          });
        }
        break;
      }
      case "delta": {
        const de = event as DeltaEvent;
        if (currentTurnRef.current) {
          const tc = currentTurnRef.current.toolCalls.find(
            (t) => t.call_id === de.call_id,
          );
          if (tc) {
            tc.deltas.push(de.delta);
            setTurns((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { ...currentTurnRef.current! };
              return updated;
            });
          }
        }
        break;
      }
      case "completed": {
        const ce = event as CompletedEvent;
        if (currentTurnRef.current) {
          const tc = currentTurnRef.current.toolCalls.find(
            (t) => t.call_id === ce.call_id,
          );
          if (tc) {
            tc.result = ce.result;
            tc.error = ce.error;
            tc.duration_ms = ce.duration_ms;
            tc.status = ce.error ? "error" : "done";
            setTurns((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { ...currentTurnRef.current! };
              return updated;
            });
          }
        }
        break;
      }
      case "done": {
        if (currentTurnRef.current) {
          currentTurnRef.current.done = true;
          setTurns((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { ...currentTurnRef.current! };
            return updated;
          });
          currentTurnRef.current = null;
          setBusy(false);
        }
        break;
      }
      case "error": {
        if (currentTurnRef.current) {
          currentTurnRef.current.error = event.message;
          currentTurnRef.current.done = true;
          setTurns((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = { ...currentTurnRef.current! };
            return updated;
          });
          currentTurnRef.current = null;
          setBusy(false);
        }
        break;
      }
    }
  }

  const sendPrompt = useCallback(
    (text: string) => {
      if (!procRef.current || !ready) return;

      const turn: Turn = {
        id: crypto.randomUUID(),
        prompt: text,
        toolCalls: [],
        done: false,
        error: null,
        timestamp: Date.now(),
      };

      currentTurnRef.current = turn;
      setTurns((prev) => [...prev, turn]);
      setBusy(true);

      const missionPrefix = /^\/mission\s+/;
      const messageType = missionPrefix.test(text) ? "mission" : "prompt";
      const payloadText = text.replace(missionPrefix, "").trim();
      procRef.current.stdin?.write(
        JSON.stringify({ type: messageType, text: payloadText }) + "\n",
      );
    },
    [ready],
  );

  const toggleExpand = useCallback((turnIdx: number, callId: string) => {
    setTurns((prev) => {
      const updated = [...prev];
      const turn = { ...updated[turnIdx] };
      turn.toolCalls = turn.toolCalls.map((tc) =>
        tc.call_id === callId ? { ...tc, expanded: !tc.expanded } : tc,
      );
      updated[turnIdx] = turn;
      return updated;
    });
  }, []);

  const clearTurns = useCallback(() => {
    setTurns([]);
  }, []);

  return {
    turns,
    ready,
    tools,
    model,
    busy,
    loopSnapshot,
    sendPrompt,
    toggleExpand,
    clearTurns,
  };
}
