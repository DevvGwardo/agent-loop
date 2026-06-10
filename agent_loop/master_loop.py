"""Master loop orchestration for mission, goal, agent, workflow, and tool loops."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypeAlias

from agent_loop.harness import CodingAgentHarness
from agent_loop.models import (
    AgentEvent,
    ToolCallCompletedEvent,
    ToolCallDeltaEvent,
    ToolCallStartedEvent,
)


class LoopKind(str, Enum):
    """The runtime layers managed by the master loop harness."""

    MASTER = "master"
    MISSION = "mission"
    GOAL = "goal"
    AGENT = "agent"
    WORKFLOW = "workflow"
    TOOL = "tool"


class LoopStatus(str, Enum):
    """Lifecycle state for every loop node."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class WorkflowLoopSpec:
    """A workflow loop run by an agent loop."""

    name: str = "execute"
    objective: str = ""
    prompt: str | None = None
    tool_sequence: list[dict[str, Any]] | None = None

    @classmethod
    def from_json(cls, data: str | dict[str, Any]) -> "WorkflowLoopSpec":
        if isinstance(data, str):
            return cls(name=data, objective=data)
        return cls(
            name=str(data.get("name") or data.get("id") or "execute"),
            objective=str(data.get("objective") or data.get("task") or ""),
            prompt=data.get("prompt"),
            tool_sequence=list(data["tool_sequence"]) if data.get("tool_sequence") else None,
        )


@dataclass
class AgentLoopSpec:
    """An agent loop spawned for one goal."""

    name: str = "primary-agent"
    objective: str = ""
    workflows: list[WorkflowLoopSpec] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: str | dict[str, Any]) -> "AgentLoopSpec":
        if isinstance(data, str):
            return cls(name=data, objective=data)
        workflows = [
            WorkflowLoopSpec.from_json(item)
            for item in data.get("workflows") or []
        ]
        return cls(
            name=str(data.get("name") or data.get("id") or "primary-agent"),
            objective=str(data.get("objective") or data.get("task") or ""),
            workflows=workflows,
        )


@dataclass
class GoalLoopSpec:
    """A goal loop created inside a mission loop."""

    name: str
    objective: str
    agents: list[AgentLoopSpec] = field(default_factory=list)
    repeat: int = 1

    @classmethod
    def from_json(cls, data: str | dict[str, Any]) -> "GoalLoopSpec":
        if isinstance(data, str):
            return cls(name=data, objective=data)
        agents = [
            AgentLoopSpec.from_json(item)
            for item in data.get("agents") or []
        ]
        name = str(data.get("name") or data.get("id") or data.get("objective") or "goal")
        return cls(
            name=name,
            objective=str(data.get("objective") or data.get("task") or name),
            agents=agents,
            repeat=max(1, int(data.get("repeat", 1))),
        )


@dataclass
class MissionLoopSpec:
    """Top-level mission loop configuration.

    ``perpetual=True`` allows the mission loop to keep cycling until the
    harness-level ``should_continue`` callback returns ``False``. For command
    line safety, ``max_cycles`` defaults to one.
    """

    objective: str
    name: str = "mission"
    goals: list[GoalLoopSpec] = field(default_factory=list)
    max_cycles: int | None = 1
    perpetual: bool = False
    idle_sleep_seconds: float = 0.0
    stop_on_error: bool = True

    @classmethod
    def from_json(cls, data: str | dict[str, Any]) -> "MissionLoopSpec":
        if isinstance(data, str):
            return cls(objective=data)

        objective = str(
            data.get("objective")
            or data.get("task")
            or data.get("text")
            or data.get("mission")
            or ""
        ).strip()
        if not objective:
            raise ValueError("mission objective is required")

        goals = [
            GoalLoopSpec.from_json(item)
            for item in data.get("goals") or []
        ]
        max_cycles = data.get("max_cycles", 1)
        return cls(
            objective=objective,
            name=str(data.get("name") or "mission"),
            goals=goals,
            max_cycles=None if max_cycles is None else max(1, int(max_cycles)),
            perpetual=bool(data.get("perpetual", False)),
            idle_sleep_seconds=float(data.get("idle_sleep_seconds", 0.0)),
            stop_on_error=bool(data.get("stop_on_error", True)),
        )


@dataclass
class LoopNode:
    """Serializable node for one loop in the hierarchy."""

    id: str
    kind: str
    name: str
    objective: str = ""
    parent_id: str | None = None
    status: str = LoopStatus.PENDING.value
    cycle: int = 0
    iteration: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    children: list["LoopNode"] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None

    def start(self, *, cycle: int | None = None, iteration: int | None = None) -> None:
        self.status = LoopStatus.RUNNING.value
        self.started_at = self.started_at or _now()
        self.updated_at = _now()
        if cycle is not None:
            self.cycle = cycle
        if iteration is not None:
            self.iteration = iteration

    def finish(self, status: LoopStatus, *, error: str | None = None) -> None:
        self.status = status.value
        self.completed_at = _now()
        self.updated_at = self.completed_at
        self.error = error

    def touch(self) -> None:
        self.updated_at = _now()

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "objective": self.objective,
            "parent_id": self.parent_id,
            "status": self.status,
            "cycle": self.cycle,
            "iteration": self.iteration,
            "metrics": self.metrics,
            "children": [child.to_json() for child in self.children],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


@dataclass(frozen=True)
class LoopLifecycleEvent:
    """A lifecycle update emitted by the master loop harness."""

    event_type: str
    node: dict[str, Any]
    snapshot: dict[str, Any]
    message: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "node": self.node,
            "snapshot": self.snapshot,
            "message": self.message,
        }


MasterLoopEvent: TypeAlias = AgentEvent | LoopLifecycleEvent
ShouldContinue: TypeAlias = Callable[[dict[str, Any]], bool]


class _SafeFormat(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class MasterLoopHarness:
    """Run mission loops that expand into goal, agent, workflow, and tool loops."""

    def __init__(
        self,
        coding_harness: CodingAgentHarness,
        *,
        should_continue: ShouldContinue | None = None,
        idle_sleep_seconds: float = 0.0,
    ) -> None:
        self.coding_harness = coding_harness
        self.should_continue = should_continue
        self.idle_sleep_seconds = idle_sleep_seconds
        self._root: LoopNode | None = None
        self._nodes: dict[str, LoopNode] = {}
        self._active_path: list[str] = []
        self._stats = self._empty_stats()

    @property
    def root(self) -> LoopNode | None:
        return self._root

    def snapshot(self) -> dict[str, Any]:
        return {
            "root": self._root.to_json() if self._root else None,
            "active_path": list(self._active_path),
            "stats": dict(self._stats),
        }

    def run(
        self,
        mission: MissionLoopSpec | dict[str, Any] | str,
    ) -> Generator[MasterLoopEvent, None, str]:
        """Run a mission through every loop layer and stream lifecycle events."""

        parsed = (
            mission
            if isinstance(mission, MissionLoopSpec)
            else MissionLoopSpec.from_json(mission)
        )
        spec = self._normalize_spec(parsed)
        self._reset()

        master_node = self._create_node(
            LoopKind.MASTER,
            name="master loop",
            objective=spec.objective,
        )
        self._root = master_node
        master_node.start()
        self._active_path = [master_node.id]
        yield self._event("loop.started", master_node, "master loop started")

        mission_node = self._create_node(
            LoopKind.MISSION,
            name=spec.name,
            objective=spec.objective,
            parent=master_node,
        )
        mission_node.start()
        self._active_path = [master_node.id, mission_node.id]
        yield self._event("loop.started", mission_node, "mission loop started")

        summary = ""
        cycles_completed = 0
        try:
            while self._should_run_cycle(spec, cycles_completed):
                cycle = cycles_completed + 1
                mission_node.cycle = cycle
                mission_node.iteration = cycle
                mission_node.metrics["cycles_started"] = cycle
                mission_node.touch()
                self._stats["cycles_started"] = cycle
                yield self._event("loop.updated", mission_node, f"mission cycle {cycle} started")

                for goal_index, goal_spec in enumerate(spec.goals, start=1):
                    goal_reply = yield from self._run_goal(
                        spec,
                        mission_node,
                        goal_spec,
                        cycle=cycle,
                        goal_index=goal_index,
                    )
                    if goal_reply:
                        summary = goal_reply

                cycles_completed += 1
                self._stats["cycles_completed"] = cycles_completed
                mission_node.metrics["cycles_completed"] = cycles_completed
                mission_node.touch()

                if spec.perpetual and not self._should_continue_after_cycle(spec):
                    break
                delay = spec.idle_sleep_seconds or self.idle_sleep_seconds
                if delay > 0:
                    time.sleep(delay)

            mission_node.finish(LoopStatus.COMPLETED)
            self._active_path = [master_node.id, mission_node.id]
            yield self._event("loop.completed", mission_node, "mission loop completed")
            master_node.finish(LoopStatus.COMPLETED)
            self._active_path = [master_node.id]
            yield self._event("loop.completed", master_node, "master loop completed")
            return summary or f"Mission completed: {spec.objective}"
        except Exception as exc:
            message = str(exc)
            mission_node.finish(LoopStatus.FAILED, error=message)
            yield self._event("loop.failed", mission_node, message)
            master_node.finish(LoopStatus.FAILED, error=message)
            yield self._event("loop.failed", master_node, message)
            return f"Mission failed: {message}"

    def _run_goal(
        self,
        mission: MissionLoopSpec,
        mission_node: LoopNode,
        goal: GoalLoopSpec,
        *,
        cycle: int,
        goal_index: int,
    ) -> Generator[MasterLoopEvent, None, str]:
        goal_node = self._create_node(
            LoopKind.GOAL,
            name=goal.name,
            objective=goal.objective,
            parent=mission_node,
        )
        goal_node.start(cycle=cycle, iteration=goal_index)
        goal_node.metrics["repeat"] = goal.repeat
        self._stats["goals_started"] += 1
        self._active_path = self._path_for(goal_node)
        yield self._event("loop.started", goal_node, "goal loop started")

        summary = ""
        for goal_iteration in range(1, goal.repeat + 1):
            goal_node.iteration = goal_iteration
            goal_node.touch()
            yield self._event("loop.updated", goal_node, f"goal iteration {goal_iteration} started")

            for agent_index, agent in enumerate(goal.agents, start=1):
                agent_reply = yield from self._run_agent(
                    mission,
                    goal,
                    goal_node,
                    agent,
                    cycle=cycle,
                    goal_iteration=goal_iteration,
                    agent_index=agent_index,
                )
                if agent_reply:
                    summary = agent_reply

        goal_node.finish(LoopStatus.COMPLETED)
        self._stats["goals_completed"] += 1
        self._active_path = self._path_for(goal_node)
        yield self._event("loop.completed", goal_node, "goal loop completed")
        return summary

    def _run_agent(
        self,
        mission: MissionLoopSpec,
        goal: GoalLoopSpec,
        goal_node: LoopNode,
        agent: AgentLoopSpec,
        *,
        cycle: int,
        goal_iteration: int,
        agent_index: int,
    ) -> Generator[MasterLoopEvent, None, str]:
        agent_node = self._create_node(
            LoopKind.AGENT,
            name=agent.name,
            objective=agent.objective or goal.objective,
            parent=goal_node,
        )
        agent_node.start(cycle=cycle, iteration=agent_index)
        agent_node.metrics["goal_iteration"] = goal_iteration
        self._stats["agents_started"] += 1
        self._active_path = self._path_for(agent_node)
        yield self._event("loop.started", agent_node, "agent loop started")

        summary = ""
        for workflow_index, workflow in enumerate(agent.workflows, start=1):
            workflow_reply = yield from self._run_workflow(
                mission,
                goal,
                agent,
                agent_node,
                workflow,
                cycle=cycle,
                goal_iteration=goal_iteration,
                workflow_index=workflow_index,
            )
            if workflow_reply:
                summary = workflow_reply

        agent_node.finish(LoopStatus.COMPLETED)
        self._stats["agents_completed"] += 1
        self._active_path = self._path_for(agent_node)
        yield self._event("loop.completed", agent_node, "agent loop completed")
        return summary

    def _run_workflow(
        self,
        mission: MissionLoopSpec,
        goal: GoalLoopSpec,
        agent: AgentLoopSpec,
        agent_node: LoopNode,
        workflow: WorkflowLoopSpec,
        *,
        cycle: int,
        goal_iteration: int,
        workflow_index: int,
    ) -> Generator[MasterLoopEvent, None, str]:
        workflow_node = self._create_node(
            LoopKind.WORKFLOW,
            name=workflow.name,
            objective=workflow.objective or goal.objective,
            parent=agent_node,
        )
        workflow_node.start(cycle=cycle, iteration=workflow_index)
        workflow_node.metrics["goal_iteration"] = goal_iteration
        self._stats["workflows_started"] += 1
        self._active_path = self._path_for(workflow_node)
        yield self._event("loop.started", workflow_node, "workflow loop started")

        prompt = self._render_workflow_prompt(
            mission,
            goal,
            agent,
            workflow,
            cycle=cycle,
            goal_iteration=goal_iteration,
        )
        runner = (
            self.coding_harness.run_tool_sequence(prompt, workflow.tool_sequence)
            if workflow.tool_sequence is not None
            else self.coding_harness.run(prompt)
        )

        reply, tool_errors, failure = yield from self._run_tool_loops(runner, workflow_node)
        workflow_node.metrics["tool_errors"] = tool_errors
        if reply:
            workflow_node.metrics["reply"] = reply[:500]

        if failure is not None:
            workflow_node.finish(LoopStatus.FAILED, error=str(failure))
            yield self._event("loop.failed", workflow_node, str(failure))
            if mission.stop_on_error:
                raise failure
            return reply

        workflow_node.finish(LoopStatus.COMPLETED)
        self._stats["workflows_completed"] += 1
        self._active_path = self._path_for(workflow_node)
        yield self._event("loop.completed", workflow_node, "workflow loop completed")
        return reply

    def _run_tool_loops(
        self,
        runner: Generator[AgentEvent, None, str],
        workflow_node: LoopNode,
    ) -> Generator[MasterLoopEvent, None, tuple[str, int, Exception | None]]:
        active_tools: dict[str, LoopNode] = {}
        tool_errors = 0

        while True:
            try:
                event = next(runner)
            except StopIteration as done:
                return str(done.value or ""), tool_errors, None
            except Exception as exc:
                return "", tool_errors, exc

            if isinstance(event, ToolCallStartedEvent):
                tool_node = self._create_node(
                    LoopKind.TOOL,
                    name=event.tool_name,
                    objective=event.call_id,
                    parent=workflow_node,
                    node_id=self._tool_node_id(event.call_id),
                )
                tool_node.start(cycle=workflow_node.cycle)
                tool_node.metrics.update({
                    "call_id": event.call_id,
                    "tool_name": event.tool_name,
                    "args": event.args,
                    "deltas": 0,
                })
                active_tools[event.call_id] = tool_node
                self._stats["tools_started"] += 1
                self._active_path = self._path_for(tool_node)
                yield self._event("loop.started", tool_node, "tool loop started")
                yield event
                continue

            if isinstance(event, ToolCallDeltaEvent):
                if tool_node := active_tools.get(event.call_id):
                    tool_node.metrics["deltas"] = int(tool_node.metrics.get("deltas", 0)) + 1
                    tool_node.touch()
                yield event
                continue

            if isinstance(event, ToolCallCompletedEvent):
                yield event
                tool_node = active_tools.pop(event.call_id, None)
                if tool_node is not None:
                    tool_node.metrics["result_keys"] = sorted(event.result.keys())
                    if event.error:
                        tool_errors += 1
                        self._stats["tools_failed"] += 1
                        tool_node.finish(LoopStatus.FAILED, error=event.error)
                        self._active_path = self._path_for(tool_node)
                        yield self._event("loop.failed", tool_node, event.error)
                    else:
                        self._stats["tools_completed"] += 1
                        tool_node.finish(LoopStatus.COMPLETED)
                        self._active_path = self._path_for(tool_node)
                        yield self._event("loop.completed", tool_node, "tool loop completed")
                continue

            yield event

    def _normalize_spec(self, spec: MissionLoopSpec) -> MissionLoopSpec:
        if not spec.goals:
            spec.goals = [GoalLoopSpec(name="primary-goal", objective=spec.objective)]

        for goal in spec.goals:
            if not goal.agents:
                goal.agents = [AgentLoopSpec()]
            for agent in goal.agents:
                if not agent.workflows:
                    agent.workflows = [WorkflowLoopSpec()]

        return spec

    def _render_workflow_prompt(
        self,
        mission: MissionLoopSpec,
        goal: GoalLoopSpec,
        agent: AgentLoopSpec,
        workflow: WorkflowLoopSpec,
        *,
        cycle: int,
        goal_iteration: int,
    ) -> str:
        values = _SafeFormat(
            mission=mission.objective,
            goal=goal.objective,
            agent=agent.name,
            workflow=workflow.name,
            cycle=cycle,
            goal_iteration=goal_iteration,
        )
        if workflow.prompt:
            return workflow.prompt.format_map(values)
        if workflow.objective:
            return workflow.objective.format_map(values)
        return (
            f"Mission loop: {mission.objective}\n"
            f"Goal loop: {goal.objective}\n"
            f"Agent loop: {agent.name} ({agent.objective or goal.objective})\n"
            f"Workflow loop: {workflow.name}\n"
            f"Cycle: {cycle}, goal iteration: {goal_iteration}\n\n"
            "Run the workflow to move this goal forward. Use tools when useful, "
            "then return a concise status with what changed and what remains."
        )

    def _create_node(
        self,
        kind: LoopKind,
        *,
        name: str,
        objective: str = "",
        parent: LoopNode | None = None,
        node_id: str | None = None,
    ) -> LoopNode:
        resolved_id = node_id or _short_id(kind.value)
        while resolved_id in self._nodes:
            resolved_id = _short_id(kind.value)
        node = LoopNode(
            id=resolved_id,
            kind=kind.value,
            name=name,
            objective=objective,
            parent_id=parent.id if parent else None,
        )
        if parent is not None:
            parent.children.append(node)
        self._nodes[node.id] = node
        return node

    def _path_for(self, node: LoopNode) -> list[str]:
        path = [node.id]
        parent_id = node.parent_id
        while parent_id:
            parent = self._nodes.get(parent_id)
            if parent is None:
                break
            path.append(parent.id)
            parent_id = parent.parent_id
        return list(reversed(path))

    def _event(self, event_type: str, node: LoopNode, message: str = "") -> LoopLifecycleEvent:
        return LoopLifecycleEvent(
            event_type=event_type,
            node=node.to_json(),
            snapshot=self.snapshot(),
            message=message,
        )

    def _reset(self) -> None:
        self._root = None
        self._nodes = {}
        self._active_path = []
        self._stats = self._empty_stats()

    def _should_run_cycle(self, spec: MissionLoopSpec, cycles_completed: int) -> bool:
        if spec.perpetual:
            if self.should_continue is None:
                return True
            return self.should_continue(self.snapshot())
        max_cycles = spec.max_cycles if spec.max_cycles is not None else 1
        return cycles_completed < max_cycles

    def _should_continue_after_cycle(self, spec: MissionLoopSpec) -> bool:
        if not spec.perpetual:
            return False
        if self.should_continue is None:
            return True
        return self.should_continue(self.snapshot())

    def _tool_node_id(self, call_id: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in call_id)
        return f"tool_{safe or uuid.uuid4().hex[:10]}"

    @staticmethod
    def _empty_stats() -> dict[str, int]:
        return {
            "cycles_started": 0,
            "cycles_completed": 0,
            "goals_started": 0,
            "goals_completed": 0,
            "agents_started": 0,
            "agents_completed": 0,
            "workflows_started": 0,
            "workflows_completed": 0,
            "tools_started": 0,
            "tools_completed": 0,
            "tools_failed": 0,
        }


__all__ = [
    "AgentLoopSpec",
    "GoalLoopSpec",
    "LoopKind",
    "LoopLifecycleEvent",
    "LoopNode",
    "LoopStatus",
    "MasterLoopEvent",
    "MasterLoopHarness",
    "MissionLoopSpec",
    "WorkflowLoopSpec",
]
