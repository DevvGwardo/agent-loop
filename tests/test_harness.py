"""Tests for the reusable coding-agent harness."""

from __future__ import annotations

from agent_loop.harness import CodingAgentHarness, tool_schema
from agent_loop.llm import ChatModelResponse, ToolCallRequest
from agent_loop.models import ToolCallCompletedEvent
from agent_loop.session import PermissionMode
from agent_loop.tools import ReadExecutor, ShellExecutor


class _FakeModel:
    def __init__(self) -> None:
        self.calls = 0
        self.seen_tools: list[dict] = []

    def complete(self, messages, tools):
        self.calls += 1
        self.seen_tools = tools
        if self.calls == 1:
            return ChatModelResponse(
                tool_calls=[
                    ToolCallRequest(
                        name="shell",
                        args={"command": "pwd"},
                        call_id="call_pwd",
                    )
                ]
            )
        return ChatModelResponse(content="The command ran.")


def test_tool_schema_for_shell_has_command_required() -> None:
    schema = tool_schema(ShellExecutor())
    function = schema["function"]
    assert function["name"] == "shell"
    assert "command" in function["parameters"]["required"]


def test_run_tool_sequence_passes_working_directory(tmp_path) -> None:
    harness = CodingAgentHarness(
        executors=[ShellExecutor()],
        working_directory=str(tmp_path),
    )
    events = list(
        harness.run_tool_sequence(
            "print cwd",
            [{"tool": "shell", "args": {"command": "pwd"}, "call_id": "call_pwd"}],
        )
    )
    completed = [event for event in events if isinstance(event, ToolCallCompletedEvent)]
    assert len(completed) == 1
    assert completed[0].result["stdout"].strip() == str(tmp_path)


def test_model_driven_loop_executes_tool_and_returns_final_reply(tmp_path) -> None:
    model = _FakeModel()
    harness = CodingAgentHarness(
        model_client=model,
        executors=[ShellExecutor(), ReadExecutor()],
        working_directory=str(tmp_path),
    )

    runner = harness.run("where are we?")
    events = []
    while True:
        try:
            events.append(next(runner))
        except StopIteration as done:
            reply = done.value
            break

    assert reply == "The command ran."
    assert model.calls == 2
    assert any(tool["function"]["name"] == "shell" for tool in model.seen_tools)
    assert any(isinstance(event, ToolCallCompletedEvent) for event in events)
    assert any(message["role"] == "tool" for message in harness.messages)


def test_read_only_permissions_block_shell(tmp_path) -> None:
    harness = CodingAgentHarness(
        executors=[ShellExecutor()],
        working_directory=str(tmp_path),
        permission_mode=PermissionMode.READ_ONLY,
    )
    events = list(
        harness.run_tool_sequence(
            "try shell",
            [{"tool": "shell", "args": {"command": "pwd"}, "call_id": "call_pwd"}],
        )
    )
    completed = [event for event in events if isinstance(event, ToolCallCompletedEvent)]
    assert len(completed) == 1
    assert "read-only" in (completed[0].error or "")


def test_json_events_follow_codex_exec_shape(tmp_path) -> None:
    model = _FakeModel()
    harness = CodingAgentHarness(
        model_client=model,
        executors=[ShellExecutor()],
        working_directory=str(tmp_path),
    )
    runner = harness.run_json_events("where are we?")
    events = []
    while True:
        try:
            events.append(next(runner))
        except StopIteration:
            break

    assert events[0]["type"] == "thread.started"
    assert events[1]["type"] == "turn.started"
    assert any(event["type"] == "item.started" for event in events)
    assert events[-1]["type"] == "turn.completed"
