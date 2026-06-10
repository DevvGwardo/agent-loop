// Bridge protocol types between Ink TUI and Python agent-loop process.

export interface BridgeEvent {
  type: string;
  [key: string]: unknown;
}

export interface ReadyEvent extends BridgeEvent {
  type: "ready";
  tools: string[];
  loop_snapshot?: LoopSnapshot;
}

export interface StartedEvent extends BridgeEvent {
  type: "started";
  call_id: string;
  tool_name: string;
  args: Record<string, unknown>;
}

export interface DeltaEvent extends BridgeEvent {
  type: "delta";
  call_id: string;
  delta: string;
}

export interface CompletedEvent extends BridgeEvent {
  type: "completed";
  call_id: string;
  tool_name: string;
  result: Record<string, unknown>;
  error: string | null;
  duration_ms: number;
}

export interface ReplyEvent extends BridgeEvent {
  type: "reply";
  text: string;
}

export interface LoopNodeState {
  id: string;
  kind: "master" | "mission" | "goal" | "agent" | "workflow" | "tool";
  name: string;
  objective: string;
  parent_id: string | null;
  status: "pending" | "running" | "completed" | "failed" | "stopped";
  cycle: number;
  iteration: number;
  metrics: Record<string, unknown>;
  children: LoopNodeState[];
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
}

export interface LoopSnapshot {
  root: LoopNodeState | null;
  active_path: string[];
  stats: Record<string, number>;
}

export interface LoopEvent extends BridgeEvent {
  type: "loop";
  event: string;
  node: LoopNodeState;
  snapshot: LoopSnapshot;
  message: string;
}

export interface DoneEvent extends BridgeEvent {
  type: "done";
}

export interface ErrorEvent extends BridgeEvent {
  type: "error";
  message: string;
}

export interface ByeEvent extends BridgeEvent {
  type: "bye";
}

export type AgentEvent =
  | ReadyEvent
  | StartedEvent
  | DeltaEvent
  | CompletedEvent
  | ReplyEvent
  | LoopEvent
  | DoneEvent
  | ErrorEvent
  | ByeEvent;

// Tool call state tracked by the UI
export interface ToolCallState {
  call_id: string;
  tool_name: string;
  args: Record<string, unknown>;
  deltas: string[];
  result: Record<string, unknown> | null;
  error: string | null;
  duration_ms: number;
  expanded: boolean;
  status: "running" | "done" | "error";
}

// A turn in the conversation
export interface Turn {
  id: string;
  prompt: string;
  reply?: string;
  toolCalls: ToolCallState[];
  done: boolean;
  error: string | null;
  timestamp: number;
}
