import React from "react";
import { Box, Text } from "ink";
import type { Turn } from "../types.js";
import { ToolCallView } from "./ToolCall.js";

interface Props {
  turns: Turn[];
  onToggle: (turnIdx: number, callId: string) => void;
}

export function ChatLog({ turns, onToggle }: Props) {
  if (turns.length === 0) {
    return (
      <Box flexDirection="column" paddingY={1}>
        <Text dimColor>cheekagent ready. type a prompt.</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column">
      {turns.map((turn, turnIdx) => (
        <Box key={turn.id} flexDirection="column" marginY={1}>
          {/* User prompt */}
          <Box>
            <Text color="blue" bold>
              {"❯ "}
            </Text>
            <Text>{turn.prompt}</Text>
          </Box>

          {/* Tool calls */}
          {turn.toolCalls.map((tc) => (
            <ToolCallView
              key={tc.call_id}
              toolCall={tc}
              expanded={tc.expanded}
              onToggle={() => onToggle(turnIdx, tc.call_id)}
            />
          ))}

          {/* Spinner while running */}
          {!turn.done && (
            <Box marginLeft={2}>
              <Text color="yellow">⋯ thinking</Text>
            </Box>
          )}

          {/* Error */}
          {turn.error && (
            <Box marginLeft={2}>
              <Text color="red">✗ {turn.error}</Text>
            </Box>
          )}
        </Box>
      ))}
    </Box>
  );
}
