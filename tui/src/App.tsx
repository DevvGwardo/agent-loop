import React from "react";
import { Box, Text } from "ink";
import { useBridge } from "./useBridge.js";
import { ChatLog } from "./components/ChatLog.js";
import { InputBar } from "./components/InputBar.js";
import { StatusBar } from "./components/StatusBar.js";

export function App() {
  const { turns, ready, tools, busy, sendPrompt, toggleExpand, clearTurns } =
    useBridge();

  return (
    <Box flexDirection="column" padding={1}>
      {/* Header */}
      <Box marginBottom={1}>
        <Text bold color="cyan">
          cheekagent
        </Text>
        <Text dimColor> — ink tui</Text>
      </Box>

      {/* Chat log (scrollable area) */}
      <Box flexDirection="column" flexGrow={1} minHeight={10}>
        <ChatLog turns={turns} onToggle={toggleExpand} />
      </Box>

      {/* Separator */}
      <Box>
        <Text dimColor>{"─".repeat(process.stdout.columns ?? 80)}</Text>
      </Box>

      {/* Input */}
      <InputBar onSubmit={sendPrompt} busy={busy} />

      {/* Status bar */}
      <Box marginTop={1}>
        <StatusBar
          ready={ready}
          tools={tools}
          turnCount={turns.length}
          busy={busy}
        />
      </Box>
    </Box>
  );
}
