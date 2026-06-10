import React from "react";
import { Box, Text } from "ink";
import type { LoopNodeState, LoopSnapshot } from "../types.js";

interface Props {
  snapshot: LoopSnapshot | null;
  busy: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "gray",
  running: "yellow",
  completed: "green",
  failed: "red",
  stopped: "gray",
};

const STATUS_MARKS: Record<string, string> = {
  pending: "-",
  running: ">",
  completed: "✓",
  failed: "x",
  stopped: "s",
};

interface Row {
  node: LoopNodeState;
  depth: number;
}

function flatten(node: LoopNodeState, depth = 0, rows: Row[] = []): Row[] {
  if (rows.length >= 18) return rows;
  rows.push({ node, depth });
  for (const child of node.children) {
    flatten(child, depth + 1, rows);
    if (rows.length >= 18) break;
  }
  return rows;
}

function trimText(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 1))}…`;
}

function metric(stats: Record<string, number>, key: string): number {
  return Number(stats[key] ?? 0);
}

export function LoopDashboard({ snapshot, busy }: Props) {
  const root = snapshot?.root ?? null;
  const stats = snapshot?.stats ?? {};
  const activePath = new Set(snapshot?.active_path ?? []);

  return (
    <Box
      borderStyle="single"
      borderColor={busy ? "yellow" : "gray"}
      paddingX={1}
      paddingY={0}
      marginBottom={1}
      flexDirection="column"
    >
      <Box justifyContent="space-between">
        <Text bold color="cyan">
          mission control
        </Text>
        <Text dimColor>{busy ? "active" : "idle"}</Text>
      </Box>

      <Box>
        <Text color="green">{metric(stats, "cycles_completed")}</Text>
        <Text dimColor> cycles </Text>
        <Text color="green">{metric(stats, "goals_completed")}</Text>
        <Text dimColor> goals </Text>
        <Text color="green">{metric(stats, "agents_completed")}</Text>
        <Text dimColor> agents </Text>
        <Text color="green">{metric(stats, "workflows_completed")}</Text>
        <Text dimColor> workflows </Text>
        <Text color="green">{metric(stats, "tools_completed")}</Text>
        <Text dimColor> tools</Text>
        {metric(stats, "tools_failed") > 0 && (
          <Text color="red"> {metric(stats, "tools_failed")} failed</Text>
        )}
      </Box>

      <Box flexDirection="column" marginTop={1}>
        {!root ? (
          <Text dimColor>no mission loop</Text>
        ) : (
          flatten(root).map(({ node, depth }) => {
            const color = STATUS_COLORS[node.status] ?? "white";
            const mark = STATUS_MARKS[node.status] ?? "?";
            const isActive = activePath.has(node.id);
            const label = `${node.kind}:${node.name}`;
            const detail =
              node.kind === "tool"
                ? String(node.metrics.tool_name ?? node.objective)
                : node.objective;

            return (
              <Box key={node.id}>
                <Text dimColor>{"  ".repeat(depth)}</Text>
                <Text color={color}>{mark} </Text>
                <Text color={isActive ? "white" : undefined} bold={isActive}>
                  {trimText(label, 32)}
                </Text>
                {detail && (
                  <Text dimColor> · {trimText(String(detail), 56)}</Text>
                )}
              </Box>
            );
          })
        )}
      </Box>
    </Box>
  );
}
