"""Codex-style Telegram command surface for agent-loop."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_loop.harness import CodingAgentHarness
from agent_loop.llm import OpenAICompatibleChatClient, detect_chat_client
from agent_loop.master_loop import LoopLifecycleEvent, MasterLoopHarness, MissionLoopSpec
from agent_loop.mcp import format_mcp_status, load_mcp_config
from agent_loop.mcp.client import McpClient
from agent_loop.mcp.cache import McpSnapshotCache
from agent_loop.models import ToolCallCompletedEvent, ToolCallDeltaEvent, ToolCallStartedEvent
from agent_loop.session import AgentSessionState, PermissionMode, SessionStore


HELP_TEXT = """Commands:
/mission <objective> - run the autonomous master loop on an objective
/auto <objective> - run a perpetual mission until you /stop it
/stop - stop the current mission
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
    model: str = ""
    working_directory: str = ""
    base_url: str = "https://api.openai.com/v1"
    max_iterations: int = 8
    permission_mode: str = PermissionMode.FULL_ACCESS.value
    mission_cycles: int = 1
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
        # Resolve a model client up front so the bot starts with zero config.
        client, model_label = detect_chat_client()
        self.model_client = client
        self.model_label = model_label
        if config is None:
            mcp_cache, mcp_instructions, mcp_client = load_mcp_config()
            config = TelegramAgentConfig(
                model=model_label if model_label != "none" else "",
                working_directory=os.environ.get("AGENT_LOOP_WORKDIR", os.getcwd()),
                base_url=os.environ.get("AGENT_LOOP_BASE_URL", "https://api.openai.com/v1"),
                max_iterations=int(os.environ.get("AGENT_LOOP_MAX_ITERATIONS", "8")),
                permission_mode=os.environ.get(
                    "AGENT_LOOP_PERMISSION_MODE", PermissionMode.FULL_ACCESS.value
                ),
                mission_cycles=int(os.environ.get("AGENT_LOOP_MISSION_CYCLES", "1")),
                mcp_cache=mcp_cache if mcp_cache.tools else None,
                mcp_client=mcp_client,
                mcp_instructions=mcp_instructions,
            )
        self.config = config
        self._harnesses: dict[str, CodingAgentHarness] = {}
        self._active_threads: dict[str, str] = {}
        self._missions: dict[str, MasterLoopHarness] = {}
        self._stop_flags: dict[str, bool] = {}

    def handle_text(self, chat_id: int | str, text: str) -> str:
        """Blocking convenience wrapper: collect the full stream into one string."""
        return "\n".join(chunk for chunk in self.stream(chat_id, text) if chunk).strip()

    def stream(self, chat_id: int | str, text: str) -> Generator[str, None, None]:
        """Yield progress chunks as the agent works, for live Telegram updates."""
        text = text.strip()
        if not text:
            return
        cid = str(chat_id)

        if text.startswith("/"):
            name, _, raw_args = text.partition(" ")
            command = name.removeprefix("/").lower()
            args = raw_args.strip()
            if command in {"mission", "auto"}:
                yield from self._stream_mission(cid, args, perpetual=command == "auto")
                return
            if command == "stop":
                yield self._stop(cid)
                return
            # All other commands are quick and return a single string.
            yield self._handle_command(cid, text)
            return

        harness = self._harness_for_chat(cid)
        if self.model_client is None:
            yield self._no_model_hint()
            return
        yield from self._stream_prompt(harness, text)
        self._persist(cid, harness)

    @staticmethod
    def _no_model_hint() -> str:
        return (
            "No language model is configured. Set an API key (OPENAI_API_KEY, "
            "OPENROUTER_API_KEY, GROQ_API_KEY, …) or AGENT_LOOP_MODEL and restart "
            "the bot. You can still use /shell, /diff, and /gitstatus."
        )

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
                permission_mode=self.config.permission_mode,
            )
            self.store.upsert(state)
        self._active_threads[chat_id] = state.thread_id
        return self._harness_from_state(state)

    def _harness_from_state(self, state: AgentSessionState) -> CodingAgentHarness:
        if state.thread_id in self._harnesses:
            return self._harnesses[state.thread_id]
        # Prefer a session-pinned model; otherwise use the auto-detected client.
        if state.model and state.model != self.model_label and state.model != "none":
            client: Any = OpenAICompatibleChatClient(
                model=state.model, base_url=self.config.base_url
            )
        else:
            client = self.model_client
        harness = CodingAgentHarness(
            model_client=client,
            working_directory=state.working_directory or self.config.working_directory,
            max_iterations=self.config.max_iterations,
            thread_id=state.thread_id,
            permission_mode=state.permission_mode or self.config.permission_mode,
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
        return getattr(client, "model", None) or self.config.model or self.model_label

    @staticmethod
    def _short(value: Any, limit: int = 80) -> str:
        text = str(value)
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def _stream_prompt(
        self, harness: CodingAgentHarness, prompt: str
    ) -> Generator[str, None, None]:
        """Run a model-driven prompt, yielding a line per tool start/finish + reply."""
        runner = harness.run(prompt)
        while True:
            try:
                event = next(runner)
            except StopIteration as done:
                if done.value:
                    yield str(done.value)
                break
            except Exception as exc:  # surface model/tool failures to the chat
                yield f"⚠ error: {exc}"
                break
            if isinstance(event, ToolCallStartedEvent):
                yield f"⚙ {event.tool_name} {self._short(event.args)}"
            elif isinstance(event, ToolCallCompletedEvent):
                status = "ok" if event.error is None else f"error: {event.error}"
                yield f"{'✓' if event.error is None else '✗'} {event.tool_name} ({status})"

    def _stream_mission(
        self, chat_id: str, objective: str, *, perpetual: bool
    ) -> Generator[str, None, None]:
        """Drive the autonomous master loop for an objective, streaming progress."""
        if not objective:
            yield "Usage: /mission <objective>   (or /auto for a perpetual run)"
            return
        if self.model_client is None:
            yield self._no_model_hint()
            return
        if chat_id in self._missions:
            yield "A mission is already running. Send /stop first."
            return

        harness = self._harness_for_chat(chat_id)
        self._stop_flags[chat_id] = False
        master = MasterLoopHarness(
            harness,
            should_continue=lambda _snapshot: not self._stop_flags.get(chat_id, False),
        )
        self._missions[chat_id] = master
        mode = "perpetual" if perpetual else f"{self.config.mission_cycles} cycle(s)"
        yield f"🚀 mission started ({mode}): {objective}"

        spec = MissionLoopSpec(
            objective=objective,
            max_cycles=None if perpetual else self.config.mission_cycles,
            perpetual=perpetual,
        )
        try:
            runner = master.run(spec)
            while True:
                try:
                    event = next(runner)
                except StopIteration as done:
                    if done.value:
                        yield f"🏁 {self._short(done.value, 300)}"
                    break
                for line in self._mission_progress(event):
                    yield line
        except Exception as exc:
            yield f"⚠ mission error: {exc}"
        finally:
            self._missions.pop(chat_id, None)
            self._stop_flags.pop(chat_id, None)
            self._persist(chat_id, harness)

    def _mission_progress(self, event: Any) -> list[str]:
        """Translate a master-loop event into concise chat lines (or nothing)."""
        if isinstance(event, ToolCallStartedEvent):
            return [f"⚙ {event.tool_name} {self._short(event.args)}"]
        if isinstance(event, ToolCallCompletedEvent):
            mark = "✓" if event.error is None else "✗"
            tail = "" if event.error is None else f" error: {event.error}"
            return [f"{mark} {event.tool_name}{tail}"]
        if isinstance(event, LoopLifecycleEvent):
            node = event.node
            kind = node.get("kind")
            if event.event_type == "loop.completed" and kind in {"mission", "goal"}:
                return [f"✅ {kind} complete: {node.get('name', '')}"]
            if event.event_type == "loop.failed":
                return [f"❌ {kind} failed: {self._short(event.message)}"]
            if event.event_type == "loop.updated" and kind == "mission":
                return [f"🔄 {self._short(event.message)}"]
        return []

    def _stop(self, chat_id: str) -> str:
        if chat_id not in self._missions:
            return "No mission is running."
        self._stop_flags[chat_id] = True
        return "🛑 Stopping after the current step…"

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
            client, _ = detect_chat_client(model=args)
            harness.model_client = client
            self.model_client = client
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
            harness.set_messages(self._compact_messages(harness.messages))
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
            harness.clear_transcript()
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
