"""Tests for the master mission/goal/agent/workflow/tool loop harness."""

from __future__ import annotations

from agent_loop.harness import CodingAgentHarness
from agent_loop.master_loop import (
    AgentLoopSpec,
    GoalLoopSpec,
    LoopKind,
    LoopLifecycleEvent,
    MasterLoopHarness,
    MissionLoopSpec,
    WorkflowLoopSpec,
)
from agent_loop.models import ToolCallCompletedEvent, ToolCallStartedEvent
from agent_loop.tools import ShellExecutor


def _loop_events(events: list[object]) -> list[LoopLifecycleEvent]:
    return [event for event in events if isinstance(event, LoopLifecycleEvent)]


def test_master_loop_runs_every_layer_and_wraps_tool_calls(tmp_path) -> None:
    coding = CodingAgentHarness(
        executors=[ShellExecutor()],
        working_directory=str(tmp_path),
    )
    mission = MissionLoopSpec(
        objective="Inspect the workspace",
        goals=[
            GoalLoopSpec(
                name="inspect",
                objective="Find the current directory",
                agents=[
                    AgentLoopSpec(
                        name="worker",
                        workflows=[
                            WorkflowLoopSpec(
                                name="pwd",
                                tool_sequence=[
                                    {
                                        "tool": "shell",
                                        "args": {"command": "pwd"},
                                        "call_id": "call_pwd",
                                    }
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )

    master = MasterLoopHarness(coding)
    events = list(master.run(mission))
    lifecycle = _loop_events(events)

    started_kinds = [
        event.node["kind"]
        for event in lifecycle
        if event.event_type == "loop.started"
    ]
    assert started_kinds == [
        LoopKind.MASTER.value,
        LoopKind.MISSION.value,
        LoopKind.GOAL.value,
        LoopKind.AGENT.value,
        LoopKind.WORKFLOW.value,
        LoopKind.TOOL.value,
    ]
    assert any(isinstance(event, ToolCallStartedEvent) for event in events)
    completed = [event for event in events if isinstance(event, ToolCallCompletedEvent)]
    assert completed[0].result["stdout"].strip() == str(tmp_path)
    assert master.snapshot()["stats"]["tools_completed"] == 1
    assert master.snapshot()["root"]["status"] == "completed"


def test_master_loop_can_run_multiple_mission_cycles(tmp_path) -> None:
    coding = CodingAgentHarness(
        executors=[ShellExecutor()],
        working_directory=str(tmp_path),
    )
    mission = MissionLoopSpec(
        objective="Repeatable mission",
        max_cycles=2,
        goals=[
            GoalLoopSpec(
                name="cycle-check",
                objective="Echo the cycle",
                agents=[
                    AgentLoopSpec(
                        workflows=[
                            WorkflowLoopSpec(
                                tool_sequence=[
                                    {
                                        "tool": "shell",
                                        "args": {"command": "echo cycle"},
                                        "call_id": "call_echo",
                                    }
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )

    master = MasterLoopHarness(coding)
    list(master.run(mission))

    snapshot = master.snapshot()
    assert snapshot["stats"]["cycles_completed"] == 2
    assert snapshot["stats"]["goals_completed"] == 2
    assert snapshot["stats"]["tools_completed"] == 2


def test_mission_spec_from_json_builds_default_goal_agent_workflow() -> None:
    spec = MissionLoopSpec.from_json({"objective": "Ship a feature"})
    coding = CodingAgentHarness(executors=[ShellExecutor()])
    master = MasterLoopHarness(coding)

    normalized = master._normalize_spec(spec)

    assert normalized.goals[0].name == "primary-goal"
    assert normalized.goals[0].agents[0].name == "primary-agent"
    assert normalized.goals[0].agents[0].workflows[0].name == "execute"
