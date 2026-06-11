"""Tests for the Codex-style Telegram controller."""

from __future__ import annotations

from agent_loop.session import SessionStore
from agent_loop.telegram import TelegramAgentConfig, TelegramCodexAgent


def _agent(tmp_path) -> TelegramCodexAgent:
    return TelegramCodexAgent(
        store=SessionStore(tmp_path / "sessions.json"),
        config=TelegramAgentConfig(
            model="test-model",
            working_directory=str(tmp_path),
        ),
    )


def test_status_and_permissions_commands(tmp_path) -> None:
    agent = _agent(tmp_path)
    status = agent.handle_text(123, "/status")
    assert "Thread:" in status
    assert "Permissions: full-access" in status  # autonomous default

    changed = agent.handle_text(123, "/permissions read-only")
    assert "read-only" in changed
    assert "Permissions: read-only" in agent.handle_text(123, "/status")


def test_shell_command_respects_read_only_permissions(tmp_path) -> None:
    agent = _agent(tmp_path)
    agent.handle_text(123, "/permissions read-only")
    output = agent.handle_text(123, "/shell pwd")
    assert "blocked in read-only" in output


def test_shell_command_runs_in_workspace_mode(tmp_path) -> None:
    agent = _agent(tmp_path)
    output = agent.handle_text(123, "/shell pwd")
    assert str(tmp_path) in output


def test_sessions_new_and_resume(tmp_path) -> None:
    agent = _agent(tmp_path)
    first_status = agent.handle_text(123, "/status")
    first_thread = first_status.splitlines()[0].split(": ", 1)[1]

    new_output = agent.handle_text(123, "/new")
    second_thread = new_output.rsplit(" ", 1)[-1]
    assert second_thread != first_thread

    sessions = agent.handle_text(123, "/sessions")
    assert first_thread in sessions
    assert second_thread in sessions

    resumed = agent.handle_text(123, f"/resume {first_thread}")
    assert first_thread in resumed
    assert f"Thread: {first_thread}" in agent.handle_text(123, "/status")


def test_init_creates_agents_md(tmp_path) -> None:
    agent = _agent(tmp_path)
    output = agent.handle_text(123, "/init")
    assert "Created" in output
    assert (tmp_path / "AGENTS.md").exists()


def test_mcp_without_config_reports_empty(tmp_path) -> None:
    agent = _agent(tmp_path)
    output = agent.handle_text(123, "/mcp")
    assert "No MCP tools configured" in output


def test_help_lists_autonomous_commands(tmp_path) -> None:
    agent = _agent(tmp_path)
    help_text = "\n".join(agent.stream(123, "/help"))
    assert "/mission" in help_text
    assert "/auto" in help_text
    assert "/stop" in help_text


def test_stop_and_empty_mission_messaging(tmp_path) -> None:
    agent = _agent(tmp_path)
    assert "No mission is running" in "\n".join(agent.stream(123, "/stop"))
    assert "Usage: /mission" in "\n".join(agent.stream(123, "/mission"))


def test_clear_transcript_keeps_system_message(tmp_path) -> None:
    agent = _agent(tmp_path)
    harness = agent._harness_for_chat("123")  # noqa: SLF001
    harness.set_messages(harness.messages + [{"role": "user", "content": "hi"}])
    assert len(harness.messages) >= 2
    harness.clear_transcript()
    assert len(harness.messages) == 1
    assert harness.messages[0]["role"] == "system"
