import React, { useEffect, useState } from "react";
import { Box, Text } from "ink";
import Gradient from "ink-gradient";
import BigText from "ink-big-text";
import { Spinner3D } from "./Spinner3D.js";

// Animated gradient sweep, the same trick Claude Code / Gemini / Copilot CLIs
// use: hold a fixed figlet wordmark and rotate the gradient stops each frame so
// the color band visibly travels across the letters.
const STOPS = ["#00e5ff", "#22d3ee", "#38bdf8", "#818cf8", "#c084fc", "#f472b6"];

function rotate<T>(arr: T[], by: number): T[] {
  const n = arr.length;
  const k = ((by % n) + n) % n;
  return [...arr.slice(k), ...arr.slice(0, k)];
}

interface Props {
  project?: string | null;
}

export function Banner({ project }: Props) {
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setFrame((f) => f + 1), 120);
    return () => clearInterval(id);
  }, []);

  const colors = rotate(STOPS, frame);

  return (
    <Box flexDirection="column" marginBottom={1}>
      {/* 3D hero: a live, steerable ASCII torus */}
      <Box justifyContent="center">
        <Spinner3D />
      </Box>
      <Box justifyContent="center">
        <Text dimColor>← → ↑ ↓ rotate</Text>
        <Text dimColor>{"   ·   "}</Text>
        <Text dimColor>space pause</Text>
        <Text dimColor>{"   ·   "}</Text>
        <Text dimColor>r reset</Text>
      </Box>

      <Box marginTop={1}>
        <Gradient colors={colors}>
          <BigText text="AGENT LOOP" font="block" space={false} />
        </Gradient>
        <Box flexDirection="column" justifyContent="flex-end" marginLeft={1}>
          <Text bold color="red">
            .dev
          </Text>
        </Box>
      </Box>

      <Box>
        <Text dimColor>prompt</Text>
        <Text color="cyan"> › </Text>
        <Text dimColor>mission loop</Text>
        <Text color="cyan"> › </Text>
        <Text dimColor>shipped change</Text>
        <Text dimColor>{"   ·   master loop harness"}</Text>
      </Box>

      <Box>
        <Text color="green">▸ </Text>
        <Text dimColor>
          {project
            ? `mission: ${project}`
            : "no active mission — type a prompt, /shell <cmd>, or /mission <objective>"}
        </Text>
      </Box>
    </Box>
  );
}
