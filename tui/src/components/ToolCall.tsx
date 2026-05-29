import React from "react";
import { Box, Text } from "ink";
import type { ToolCallState } from "../types.js";

interface Props {
  toolCall: ToolCallState;
  expanded: boolean;
  onToggle: () => void;
}

const ICONS: Record<string, string> = {
  running: "◌",
  done: "✓",
  error: "✗",
};

const COLORS: Record<string, string> = {
  running: "yellow",
  done: "green",
  error: "red",
};

export function ToolCallView({ toolCall, expanded, onToggle }: Props) {
  const icon = ICONS[toolCall.status] ?? "?";
  const color = COLORS[toolCall.status] ?? "white";

  return (
    <Box flexDirection="column" marginLeft={2}>
      {/* Summary row — always visible */}
      <Box>
        <Text color={color}>
          {icon} {toolCall.tool_name}
        </Text>
        {toolCall.status === "done" && (
          <Text dimColor> ({toolCall.duration_ms}ms)</Text>
        )}
        <Text> </Text>
        <Text dimColor>[</Text>
        <Text color="cyan" dimColor={!expanded}>
          {expanded ? "-" : "+"}
        </Text>
        <Text dimColor>]</Text>
      </Box>

      {/* Expanded details */}
      {expanded && (
        <Box flexDirection="column" marginLeft={4}>
          {/* Args */}
          <Box>
            <Text dimColor>args: </Text>
            <Text>
              {JSON.stringify(toolCall.args, null, 2)
                .split("\n")
                .slice(0, 10)
                .join(" ")}
            </Text>
          </Box>

          {/* Deltas */}
          {toolCall.deltas.length > 0 && (
            <Box flexDirection="column">
              <Text dimColor>output:</Text>
              {toolCall.deltas.map((d, i) => (
                <Text key={i} dimColor>
                  {"  "}
                  {d}
                </Text>
              ))}
            </Box>
          )}

          {/* Result */}
          {toolCall.result && (
            <Box flexDirection="column">
              <Text dimColor>result:</Text>
              <Text color="green">
                {JSON.stringify(toolCall.result, null, 2)
                  .split("\n")
                  .slice(0, 15)
                  .map((l) => `  ${l}`)
                  .join("\n")}
              </Text>
            </Box>
          )}

          {/* Error */}
          {toolCall.error && (
            <Box>
              <Text color="red">error: {toolCall.error}</Text>
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
