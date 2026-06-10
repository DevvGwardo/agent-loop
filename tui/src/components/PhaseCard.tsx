import React from "react";
import { Box, Text } from "ink";
import type { LoopNodeState } from "../types.js";

export interface PhaseRow {
  node: LoopNodeState;
  label: string;
  detail: string;
}

export interface Phase {
  node: LoopNodeState;
  index: number;
  total: number;
  rows: PhaseRow[];
}

interface Props {
  phase: Phase;
  active: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  pending: "gray",
  running: "yellow",
  completed: "green",
  failed: "red",
  stopped: "gray",
};

const STATUS_MARK: Record<string, string> = {
  pending: " ",
  running: "◐",
  completed: "✓",
  failed: "✗",
  stopped: "·",
};

const LABEL_WIDTH = 22;

function bar(done: number, total: number, width = 14): string {
  if (total <= 0) return "░".repeat(width);
  const filled = Math.round((done / total) * width);
  return "█".repeat(filled) + "░".repeat(Math.max(0, width - filled));
}

function pad(value: string, width: number): string {
  if (value.length >= width) return value.slice(0, width - 1) + "…";
  return value + " ".repeat(width - value.length);
}

export function PhaseCard({ phase, active }: Props) {
  const { node, index, total, rows } = phase;
  const done = rows.filter((r) => r.node.status === "completed").length;
  const denom = rows.length || 1;
  const headerColor = STATUS_COLOR[node.status] ?? "white";
  const complete = node.status === "completed";
  const failed = node.status === "failed";

  return (
    <Box flexDirection="column" marginBottom={1}>
      {/* Header: "N/total  name" + progress bar */}
      <Box>
        <Text dimColor>{`${index + 1}/${total} `}</Text>
        <Text bold color={active ? "white" : headerColor}>
          {node.name}
        </Text>
        <Text> </Text>
        <Text color={complete ? "green" : "yellow"}>{bar(done, denom)}</Text>
        <Text dimColor>{`  ${done}/${rows.length}`}</Text>
      </Box>

      {/* Checklist rows */}
      <Box flexDirection="column" marginLeft={1}>
        {rows.length === 0 ? (
          <Text dimColor>· waiting…</Text>
        ) : (
          rows.map((row) => {
            const color = STATUS_COLOR[row.node.status] ?? "white";
            const mark = STATUS_MARK[row.node.status] ?? " ";
            return (
              <Box key={row.node.id}>
                <Text color={color}>{mark} </Text>
                <Text color={row.node.status === "pending" ? "gray" : "white"}>
                  {pad(row.label, LABEL_WIDTH)}
                </Text>
                <Text dimColor>{row.detail}</Text>
              </Box>
            );
          })
        )}
      </Box>

      {/* Footer pill */}
      {(complete || failed) && (
        <Box marginLeft={1}>
          <Text color={complete ? "green" : "red"}>
            {complete ? "✔" : "✗"} {node.name} {complete ? "complete" : "failed"}
          </Text>
          <Text dimColor>{"   ·   "}</Text>
          <Text
            backgroundColor={complete ? "green" : "red"}
            color="black"
            bold
          >
            {complete ? " done " : " fail "}
          </Text>
        </Box>
      )}
    </Box>
  );
}
