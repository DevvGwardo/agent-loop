import React from "react";
import { Box, Text } from "ink";

interface Props {
  ready: boolean;
  tools: string[];
  model: string;
  turnCount: number;
  busy: boolean;
}

export function StatusBar({ ready, tools, model, turnCount, busy }: Props) {
  const statusColor = ready ? "green" : "red";
  const statusText = ready ? (busy ? "running" : "ready") : "connecting...";
  const hasModel = model && model !== "none";

  return (
    <Box justifyContent="space-between">
      <Box>
        <Text dimColor>agent-loop </Text>
        <Text color={statusColor}>{statusText}</Text>
        <Text dimColor> · </Text>
        <Text color={hasModel ? "cyan" : "yellow"}>
          {hasModel ? model : "no model"}
        </Text>
        <Text dimColor> · {tools.length} tools</Text>
        {turnCount > 0 && (
          <Text dimColor> · {turnCount} turn{turnCount !== 1 ? "s" : ""}</Text>
        )}
      </Box>
      <Box>
        <Text dimColor>ctrl+c to quit</Text>
      </Box>
    </Box>
  );
}
