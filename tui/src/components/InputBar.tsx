import React, { useState } from "react";
import { Box, Text } from "ink";
import InkTextInput from "ink-text-input";

interface Props {
  onSubmit: (text: string) => void;
  busy: boolean;
}

export function InputBar({ onSubmit, busy }: Props) {
  const [value, setValue] = useState("");

  function handleSubmit(text: string) {
    const trimmed = text.trim();
    if (trimmed && !busy) {
      onSubmit(trimmed);
      setValue("");
    }
  }

  return (
    <Box flexDirection="column">
      <Box>
        <Text color="magenta" bold>
          {busy ? "⋯ " : "❯ "}
        </Text>
        {busy ? (
          <Text dimColor>waiting for agent...</Text>
        ) : (
          <InkTextInput
            value={value}
            onChange={setValue}
            onSubmit={handleSubmit}
            placeholder="ask something..."
          />
        )}
      </Box>
    </Box>
  );
}
