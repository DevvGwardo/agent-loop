"""Codex-style Telegram command surface for agent-loop."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_loop.harness import CodingAgentHarness
from agent_loop.llm import OpenAICompatibleChatClient
from agent_loop.mcp import format_mcp_status, load_mcp_config
from agent_loop.mcp.client import McpClient
from agent_loop.mcp.cache import McpSnapshotCache
from agent_loop.models import ToolCallCompletedEvent, ToolCallDeltaEvent, ToolCallStartedEvent
from agent_loop.session import AgentSessionState, PermissionMode, SessionStore


HELP_TEXT = """Commands:
/status - show model, thread, cwd, permissions, and tools
/permissions [read-only|workspace|full-access] - view or change permissions
/model [name] - view or change model
/cd <path> - change workspace
/shell <command> - run an explicit user shell command
/diff - show git diff, including untracked files
/gitstatus - show git status
/review [focus] - ask the agent to review local changes
/plan [prompt] - ask for a plan before work
/compact - trim stored transcript
/init - create AGENTS.md if missing
/tools - list model-visible tools
/sessions - list saved sessions for this chat
/resume <thread-id|last> - resume a saved session
/new - start a new session
/clear - clear current transcript
/help - show this message"""


@dataclass
class TelegramAgentConfig:
    model: str
    working_directory: str
    base_url: str = "https://api.openai.com/v1"
    max_iterations: int = 8
    mcp_cache: McpSnapshotCache | None = None
    mcp_client: McpClient | None = None
    mcp_instructions: str = ""


class TelegramCodexAgent:
    """Stateful Telegram-facing controller with Codex-like slash commands."""

    def __init__(
        self,
        *,
        store: SessionStore | None = None,
        config: TelegramAgentConfig | None = None,
    ) -> None:
        self.store = store or SessionStore()
        if config is None:
            mcp_cache, mcp_instructions, mcp_client = load_mcp_config()
            config = TelegramAgentConfig(
                model=os.environ["AGENT_LOOP_MODEL"],
                working_directory=os.environ.get("AGENT_LOOP_WORKDIR", os.getcwd()),
                base_url=os.environ.get("AGENT_LOOP_BASE_URL", "https://api.openai.com/v1"),
                max_iterations=int(os.environ.get("AGENT_LOOP_MAX_ITERATIONS", "8")),
                mcp_cache=mcp_cache if mcp_cache.tools else None,
                mcp_client=mcp_client,
                mcp_instructions=mcp_instructions,
            )
        self.config = config
        self._harnesses: dict[str, CodingAgentHarness] = {}
        self._active_threads: dict[str, str] = {}

    def handle_text(self, chat_id: int | str, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        if text.startswith("/"):
            return self._handle_command(str(chat_id), text)
        harness = self._harness_for_chat(str(chat_id))
        output = self._run_prompt(harness, text)
        self._persist(str(chat_id), harness)
        return output

    def _harness_for_chat(self, chat_id: str) -> CodingAgentHarness:
        state = None
        if active := self._active_threads.get(chat_id):
            state = self.store.get(active)
        if state is None:
            state = self.store.latest_for_chat(chat_id)
        if state is None:
            state = AgentSessionState(
                chat_id=chat_id,
                model=self.config.model,
                working_directory=self.config.working_directory,
            )
            self.store.upsert(state)
        self._active_threads[chat_id] = state.thread_id
        return self._harness_from_state(state)

    def _harness_from_state(self, state: AgentSessionState) -> CodingAgentHarness:
        if state.thread_id in self._harnesses:
            return self._harnesses[state.thread_id]
        client = OpenAICompatibleChatClient(
            model=state.model or self.config.model,
            base_url=self.config.base_url,
        )
        harness = CodingAgentHarness(
            model_client=client,
            working_directory=state.working_directory,
            max_iterations=self.config.max_iterations,
            thread_id=state.thread_id,
            permission_mode=state.permission_mode,
            initial_messages=state.messages or None,
            mcp_cache=self.config.mcp_cache,
            mcp_client=self.config.mcp_client,
            mcp_instructions=self.config.mcp_instructions,
        )
        harness.restore_plan(state.plan)
        self._harnesses[state.thread_id] = harness
        return harness

    def _persist(self, chat_id: str, harness: CodingAgentHarness) -> None:
        state = harness.snapshot(chat_id=chat_id, model=self._model_for_harness(harness))
        self.store.upsert(state)

    def _model_for_harness(self, harness: CodingAgentHarness) -> str:
        client = harness.model_client
        return getattr(client, "model", self.config.model)

    def _handle_command(self, chat_id: str, text: str) -> str:
        name, _, raw_args = text.partition(" ")
        command = name.removeprefix("/").lower()
        args = raw_args.strip()
        harness = self._harness_for_chat(chat_id)

        if command in {"help", "start"}:
            return HELP_TEXT
        if command == "status":
            return self._status(harness)
        if command == "tools":
            return "Tools: " + ", ".join(harness.tool_names)
        if command == "permissions":
            if not args:
                return f"Permission mode: {harness.permission_mode.value}"
            harness.permission_mode = PermissionMode.parse(args)
            self._persist(chat_id, harness)
            return f"Permission mode set to {harness.permission_mode.value}"
        if command == "model":
            if not args:
                return f"Model: {self._model_for_harness(harness)}"
            harness.model_client = OpenAICompatibleChatClient(model=args, base_url=self.config.base_url)
            self._persist(chat_id, harness)
            return f"Model set to {args}"
        if command == "cd":
            if not args:
                return f"Workspace: {harness.working_directory}"
            path = Path(args).expanduser()
            if not path.is_absolute():
                path = Path(harness.working_directory) / path
            if not path.exists() or not path.is_dir():
                return f"Not a directory: {path}"
            harness.set_working_directory(str(path.resolve()))
            self._persist(chat_id, harness)
            return f"Workspace set to {harness.working_directory}"
        if command == "shell":
            if not args:
                return "Usage: /shell <command>"
            return self._run_shell(chat_id, harness, args)
        if command == "diff":
            return self._git(["diff", "--stat"], harness) + "\n" + self._git(["diff"], harness)
        if command == "gitstatus":
            return self._git(["status", "--short", "--branch"], harness)
        if command == "review":
            focus = f"\nFocus: {args}" if args else ""
            prompt = (
                "Review the current working tree like a Codex code review. "
                "Prioritize bugs, regressions, risks, and missing tests. "
                "Inspect the diff first and do not edit files."
                f"{focus}"
            )
            output = self._run_prompt(harness, prompt)
            self._persist(chat_id, harness)
            return output
        if command == "plan":
            prompt = args or "Create a concise implementation plan for the current task."
            output = self._run_prompt(harness, f"Plan mode: {prompt}")
            self._persist(chat_id, harness)
            return output
        if command == "compact":
            harness._messages = self._compact_messages(harness.messages)  # noqa: SLF001
            self._persist(chat_id, harness)
            return "Transcript compacted."
        if command == "init":
            return self._init_agents_md(harness)
        if command == "sessions":
            return self._sessions(chat_id)
        if command == "resume":
            return self._resume(chat_id, args)
        if command == "new":
            state = AgentSessionState(
                chat_id=chat_id,
                model=self.config.model,
                working_directory=harness.working_directory,
                permission_mode=harness.permission_mode.value,
            )
            self.store.upsert(state)
            self._harnesses[state.thread_id] = self._harness_from_state(state)
            self._active_threads[chat_id] = state.thread_id
            return f"Started new session {state.thread_id}"
        if command == "clear":
            harness.agent.clear_history()
            harness._messages = harness.messages[:1]  # noqa: SLF001
            self._persist(chat_id, harness)
            return "Current transcript cleared."
        if command == "mcp":
            if self.config.mcp_cache is None:
                return "No MCP tools configured. Add ~/.agent-loop/mcp.json or set AGENT_LOOP_MCP_URL."
            harness.sync_mcp_tools()
            return format_mcp_status(self.config.mcp_cache, self.config.mcp_instructions)
        return f"Unknown command: /{command}\n\n{HELP_TEXT}"

    def _run_prompt(self, harness: CodingAgentHarness, prompt: str) -> str:
        lines: list[str] = []
        runner = harness.run(prompt)
        while True:
            try:
                event = next(runner)
            except StopIteration as done:
                if done.value:
                    lines.append(str(done.value))
                break
            if isinstance(event, ToolCallStartedEvent):
                lines.append(f"$ {event.tool_name} {event.args}")
            elif isinstance(event, ToolCallDeltaEvent) and event.delta.strip():
                lines.append(event.delta.strip())
            elif isinstance(event, ToolCallCompletedEvent):
                status = "ok" if event.error is None else f"error: {event.error}"
                lines.append(f"{event.tool_name} completed ({status})")
        return "\n".join(lines).strip() or "Done."

    def _run_shell(self, chat_id: str, harness: CodingAgentHarness, command: str) -> str:
        runner = harness.run_tool_sequence(
            f"/shell {command}",
            [{"tool": "shell", "args": {"command": command, "timeout": 3600}}],
        )
        lines: list[str] = []
        while True:
            try:
                event = next(runner)
            except StopIteration:
                break
            if isinstance(event, ToolCallCompletedEvent):
                result = event.result
                stdout = result.get("stdout", "")
                stderr = result.get("stderr", "")
                lines.append(stdout)
                if stderr:
                    lines.append(stderr)
                if event.error:
                    lines.append(f"error: {event.error}")
        self._persist(chat_id, harness)
        return "\n".join(part for part in lines if part).strip() or "Done."

    def _status(self, harness: CodingAgentHarness) -> str:
        plan = "\n".join(f"- [{step.status}] {step.step}" for step in harness.plan)
        return "\n".join(
            [
                f"Thread: {harness.thread_id}",
                f"Model: {self._model_for_harness(harness)}",
                f"Workspace: {harness.working_directory}",
                f"Permissions: {harness.permission_mode.value}",
                f"Tools: {', '.join(harness.tool_names)}",
                f"Messages: {len(harness.messages)}",
                "Plan:",
                plan or "- none",
            ]
        )

    def _git(self, args: list[str], harness: CodingAgentHarness) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=harness.working_directory,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as exc:
            return f"git error: {exc}"
        output = (result.stdout + result.stderr).strip()
        return output or "No output."

    def _init_agents_md(self, harness: CodingAgentHarness) -> str:
        path = Path(harness.working_directory) / "AGENTS.md"
        if path.exists():
            return "AGENTS.md already exists."
        path.write_text(
            "# Agent Instructions\n\n- Inspect before editing.\n- Keep changes focused.\n- Run relevant tests before handing off.\n",
            encoding="utf-8",
        )
        return f"Created {path}"

    def _sessions(self, chat_id: str) -> str:
        sessions = self.store.list_for_chat(chat_id)
        if not sessions:
            return "No saved sessions."
        return "\n".join(
            f"{state.thread_id}  {state.model or self.config.model}  {state.working_directory}"
            for state in sessions
        )

    def _resume(self, chat_id: str, args: str) -> str:
        state = self.store.latest_for_chat(chat_id) if args in {"", "last"} else self.store.get(args)
        if state is None or state.chat_id != chat_id:
            return "No matching session."
        self._harnesses[state.thread_id] = self._harness_from_state(state)
        self._active_threads[chat_id] = state.thread_id
        return f"Resumed session {state.thread_id}"

    @staticmethod
    def _compact_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(messages) <= 21:
            return messages
        system = messages[:1]
        tail = messages[-20:]
        summary = {
            "role": "system",
            "content": f"Earlier transcript compacted. {len(messages) - len(tail) - len(system)} messages omitted.",
        }
        return [*system, summary, *tail]


__all__ = ["HELP_TEXT", "TelegramAgentConfig", "TelegramCodexAgent"]
