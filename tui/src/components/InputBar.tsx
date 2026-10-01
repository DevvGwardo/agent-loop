import React, { useState } from "react";
import { Box, Text, useInput } from "ink";
import InkTextInput from "ink-text-input";

interface Props {
  onSubmit: (text: string) => void;
  busy: boolean;
}

interface SlashCommand {
  name: string;
  args: string; // hint shown in the menu; empty = submits immediately
  description: string;
}

const COMMANDS: SlashCommand[] = [
  { name: "/model", args: "<id> [--provider <slug>] [--global]", description: "switch model (--global persists)" },
  { name: "/provider", args: "<slug>", description: "switch to a provider's default model" },
  { name: "/apikey", args: "<slug> <key>", description: "set/update a provider API key" },
  { name: "/addprovider", args: "<slug> <base_url> [model]", description: "add a custom provider endpoint" },
  { name: "/addmodel", args: "<alias> <model_id> [--provider <slug>]", description: "add a model alias" },
  { name: "/models", args: "", description: "list providers, models, aliases" },
  { name: "/status", args: "", description: "show active model + config" },
  { name: "/shell", args: "<command>", description: "run a shell command" },
  { name: "/mission", args: "<objective>", description: "drive the master loop" },
  { name: "/help", args: "", description: "command reference" },
];

export function InputBar({ onSubmit, busy }: Props) {
  const [value, setValue] = useState("");
  const [selected, setSelected] = useState(0);

  // Menu is open while typing the command word itself (e.g. "/mo").
  const menuOpen = !busy && value.startsWith("/") && !value.includes(" ");
  const filtered = menuOpen
    ? COMMANDS.filter((c) => c.name.startsWith(value))
    : [];
  const sel = Math.min(selected, Math.max(filtered.length - 1, 0));

  useInput(
    (_input, key) => {
      if (!menuOpen || filtered.length === 0) return;
      if (key.upArrow) {
        setSelected((sel + filtered.length - 1) % filtered.length);
      } else if (key.downArrow) {
        setSelected((sel + 1) % filtered.length);
      } else if (key.tab) {
        complete(filtered[sel]);
      }
    },
    { isActive: menuOpen && filtered.length > 0 },
  );

  function complete(cmd: SlashCommand) {
    setValue(cmd.args ? cmd.name + " " : cmd.name);
    setSelected(0);
  }

  function handleChange(next: string) {
    setValue(next);
    setSelected(0);
  }

  function handleSubmit(text: string) {
    // Enter while the menu is open: complete the selection. Arg-less
    // commands submit straight away; others wait for their arguments.
    if (menuOpen && filtered.length > 0) {
      const cmd = filtered[sel];
      if (cmd.args && text.trim() !== cmd.name) {
        complete(cmd);
        return;
      }
      if (!cmd.args) {
        onSubmit(cmd.name);
        setValue("");
        setSelected(0);
        return;
      }
    }
    const trimmed = text.trim();
    if (trimmed && !busy) {
      onSubmit(trimmed);
      setValue("");
      setSelected(0);
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
            onChange={handleChange}
            onSubmit={handleSubmit}
            placeholder="ask something... (/ for commands)"
          />
        )}
      </Box>
      {menuOpen && filtered.length > 0 && (
        <Box flexDirection="column" marginLeft={2}>
          {filtered.map((cmd, i) => (
            <Box key={cmd.name}>
              <Text color={i === sel ? "magenta" : undefined} bold={i === sel}>
                {i === sel ? "▸ " : "  "}
                {cmd.name}
              </Text>
              {cmd.args ? <Text dimColor> {cmd.args}</Text> : null}
              <Text dimColor>  — {cmd.description}</Text>
            </Box>
          ))}
          <Text dimColor>↑↓ select · tab/enter complete</Text>
        </Box>
      )}
      {menuOpen && filtered.length === 0 && (
        <Box marginLeft={2}>
          <Text dimColor>no matching command — /help for the full list</Text>
        </Box>
      )}
    </Box>
  );
}
