import React from "react";
import { Box, Text } from "ink";
import type { LoopNodeState, LoopSnapshot } from "../types.js";
import { PhaseCard, type Phase, type PhaseRow } from "./PhaseCard.js";

interface Props {
  snapshot: LoopSnapshot | null;
  busy: boolean;
}

function walk(node: LoopNodeState, fn: (n: LoopNodeState) => void): void {
  fn(node);
  for (const child of node.children) walk(child, fn);
}

// Pick the layer that best maps to the screenshot's "sections": prefer goals,
// then missions, then whatever sits directly under the root.
function phaseNodes(root: LoopNodeState): LoopNodeState[] {
  const goals: LoopNodeState[] = [];
  walk(root, (n) => {
    if (n.kind === "goal") goals.push(n);
  });
  if (goals.length) return goals;

  const missions: LoopNodeState[] = [];
  walk(root, (n) => {
    if (n.kind === "mission") missions.push(n);
  });
  if (missions.length) return missions;

  return root.children.length ? root.children : [root];
}

// Checklist rows = the actionable descendants (workflow / tool / agent steps).
function rowsFor(phase: LoopNodeState): PhaseRow[] {
  const rows: PhaseRow[] = [];
  walk(phase, (n) => {
    if (n.id === phase.id) return;
    if (n.kind === "tool" || n.kind === "workflow" || n.kind === "agent") {
      const detail =
        n.kind === "tool"
          ? String(n.metrics?.tool_name ?? n.objective ?? "")
          : n.objective || "";
      rows.push({ node: n, label: n.name, detail });
    }
  });
  return rows;
}

function stat(stats: Record<string, number>, key: string): number {
  return Number(stats[key] ?? 0);
}

export function LoopDashboard({ snapshot, busy }: Props) {
  const root = snapshot?.root ?? null;
  const stats = snapshot?.stats ?? {};
  const activePath = new Set(snapshot?.active_path ?? []);

  const phases: Phase[] = root
    ? phaseNodes(root).map((node, index, all) => ({
        node,
        index,
        total: all.length,
        rows: rowsFor(node),
      }))
    : [];

  return (
    <Box
      borderStyle="round"
      borderColor={busy ? "yellow" : "gray"}
      paddingX={1}
      flexDirection="column"
      marginBottom={1}
    >
      {/* Stats strip */}
      <Box justifyContent="space-between" marginBottom={1}>
        <Box>
          <Text color="green">{stat(stats, "cycles_completed")}</Text>
          <Text dimColor> cycles </Text>
          <Text color="green">{stat(stats, "goals_completed")}</Text>
          <Text dimColor> goals </Text>
          <Text color="green">{stat(stats, "tools_completed")}</Text>
          <Text dimColor> tools</Text>
          {stat(stats, "tools_failed") > 0 && (
            <Text color="red"> · {stat(stats, "tools_failed")} failed</Text>
          )}
        </Box>
        <Text color={busy ? "yellow" : "gray"}>{busy ? "● running" : "○ idle"}</Text>
      </Box>

      {phases.length === 0 ? (
        <Box flexDirection="column">
          <Text dimColor>0/0 no mission loop yet</Text>
          <Box marginLeft={1} flexDirection="column">
            <Text dimColor>· type a prompt to chat with the agent</Text>
            <Text dimColor>· /shell &lt;command&gt; to run a shell command</Text>
            <Text dimColor>· /mission &lt;objective&gt; to launch a mission loop</Text>
          </Box>
        </Box>
      ) : (
        phases.map((phase) => (
          <PhaseCard
            key={phase.node.id}
            phase={phase}
            active={activePath.has(phase.node.id)}
          />
        ))
      )}
    </Box>
  );
}
