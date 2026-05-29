// Bridge protocol types between Ink TUI and Python agent-loop process.

export interface BridgeEvent {
  type: string;
  [key: string]: unknown;
}

export interface ReadyEvent extends BridgeEvent {
  type: "ready";
  tools: string[];
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
  toolCalls: ToolCallState[];
  done: boolean;
  error: string | null;
  timestamp: number;
}
