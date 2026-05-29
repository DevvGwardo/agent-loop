"""Skill registry — reusable agent instructions loaded at runtime.

Pattern from Cursor's Agent Skills system: skills are named, versioned
prompt fragments that an agent can load to specialize its behavior.

Skills support:
- Debounced batch updates
- Auto-load flag for always-active skills
- Combined resolution (builtin + user + team)
"""

from __future__ import annotations

from typing import Any


class Skill:
    """A named, versioned skill with optional auto-load."""

    def __init__(self, name: str, prompt: str, auto_load: bool = False, version: int = 1):
        self.name = name
        self.prompt = prompt
        self.auto_load = auto_load
        self.version = version

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "prompt": self.prompt,
            "auto_load": self.auto_load,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        return cls(
            name=data["name"],
            prompt=data["prompt"],
            auto_load=data.get("auto_load", False),
            version=data.get("version", 1),
        )


class SkillRegistry:
    """Manages skills and resolves active skills for a given tool context."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def load_skill(self, name: str, prompt: str, auto_load: bool = False) -> Skill:
        """Load or update a skill."""
        skill = Skill(name=name, prompt=prompt, auto_load=auto_load)
        self._skills[name] = skill
        return skill

    def remove_skill(self, name: str) -> None:
        self._skills.pop(name, None)

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def for_tool(self, tool_name: str) -> list[Skill]:
        """Return skills relevant to a given tool context.

        Currently returns auto-load skills. Override for tool-specific filtering.
        """
        return [s for s in self._skills.values() if s.auto_load]

    def all_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def merge(self, other: SkillRegistry) -> None:
        """Merge another registry's skills into this one (other wins on conflict)."""
        self._skills.update(other._skills)
