"""Persistent session state for Codex-style agent surfaces."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PermissionMode(str, Enum):
    """Coarse Codex-style permission profiles."""

    READ_ONLY = "read-only"
    WORKSPACE = "workspace"
    FULL_ACCESS = "full-access"

    @classmethod
    def parse(cls, value: str) -> "PermissionMode":
        normalized = value.strip().lower().replace("_", "-")
        aliases = {
            "readonly": cls.READ_ONLY,
            "read-only": cls.READ_ONLY,
            "ro": cls.READ_ONLY,
            "auto": cls.WORKSPACE,
            "workspace": cls.WORKSPACE,
            "workspace-write": cls.WORKSPACE,
            "full": cls.FULL_ACCESS,
            "full-access": cls.FULL_ACCESS,
            "danger-full-access": cls.FULL_ACCESS,
            "yolo": cls.FULL_ACCESS,
        }
        if normalized not in aliases:
            valid = ", ".join(mode.value for mode in cls)
            raise ValueError(f"unknown permission mode '{value}'. Valid modes: {valid}")
        return aliases[normalized]


@dataclass
class PlanStep:
    step: str
    status: str = "pending"


@dataclass
class AgentSessionState:
    """Serializable state for one external chat/thread."""

    thread_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chat_id: str = ""
    model: str = ""
    working_directory: str = field(default_factory=os.getcwd)
    permission_mode: str = PermissionMode.WORKSPACE.value
    messages: list[dict[str, Any]] = field(default_factory=list)
    plan: list[PlanStep] = field(default_factory=list)
    archived: bool = False

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["plan"] = [asdict(step) if isinstance(step, PlanStep) else step for step in self.plan]
        return data

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "AgentSessionState":
        plan = [
            step if isinstance(step, PlanStep) else PlanStep(**step)
            for step in data.get("plan", [])
        ]
        return cls(
            thread_id=data.get("thread_id") or str(uuid.uuid4()),
            chat_id=str(data.get("chat_id") or ""),
            model=data.get("model") or "",
            working_directory=data.get("working_directory") or os.getcwd(),
            permission_mode=data.get("permission_mode") or PermissionMode.WORKSPACE.value,
            messages=list(data.get("messages") or []),
            plan=plan,
            archived=bool(data.get("archived", False)),
        )


class SessionStore:
    """Small JSON-backed store for Telegram and other channel adapters."""

    def __init__(self, path: str | Path | None = None) -> None:
        default = Path.home() / ".agent-loop" / "sessions.json"
        self.path = Path(path or os.environ.get("AGENT_LOOP_SESSION_STORE", default))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, AgentSessionState] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for item in raw.get("sessions", []):
            state = AgentSessionState.from_json(item)
            self._sessions[state.thread_id] = state

    def save(self) -> None:
        payload = {
            "sessions": [state.to_json() for state in self._sessions.values()],
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def upsert(self, state: AgentSessionState) -> None:
        self._sessions[state.thread_id] = state
        self.save()

    def get(self, thread_id: str) -> AgentSessionState | None:
        return self._sessions.get(thread_id)

    def latest_for_chat(self, chat_id: str | int) -> AgentSessionState | None:
        chat = str(chat_id)
        matches = [
            state for state in self._sessions.values()
            if state.chat_id == chat and not state.archived
        ]
        return matches[-1] if matches else None

    def list_for_chat(self, chat_id: str | int) -> list[AgentSessionState]:
        chat = str(chat_id)
        return [
            state for state in self._sessions.values()
            if state.chat_id == chat and not state.archived
        ]


__all__ = [
    "AgentSessionState",
    "PermissionMode",
    "PlanStep",
    "SessionStore",
]
