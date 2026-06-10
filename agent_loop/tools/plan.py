"""Plan/update tool used by Codex-style harnesses."""

from __future__ import annotations

from agent_loop.session import PlanStep

from .base import ToolExecutor


class PlanExecutor(ToolExecutor):
    """Update the current task plan with short steps and statuses."""

    def __init__(self) -> None:
        self.plan: list[PlanStep] = []

    @property
    def name(self) -> str:
        return "update_plan"

    @property
    def description(self) -> str:
        return "Update the visible task plan. Each item has step and status."

    def args_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                        },
                        "required": ["step", "status"],
                    },
                },
                "explanation": {"type": "string"},
            },
            "required": ["plan"],
        }

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        items = (args or {}).get("plan") or []
        parsed: list[PlanStep] = []
        for item in items:
            step = str(item.get("step", "")).strip()
            status = str(item.get("status", "pending")).strip() or "pending"
            if step:
                parsed.append(PlanStep(step=step, status=status))
        self.plan = parsed
        return {
            "success": True,
            "message": "Plan updated",
            "plan": [step.__dict__ for step in self.plan],
        }


__all__ = ["PlanExecutor"]
