"""RequestContextBuilder — incrementally builds a RequestContext with lazy-loading."""

from __future__ import annotations

from typing import Any

from .models import AgentSkill, RequestContext


class RequestContextBuilder:
    """Builds a :class:`RequestContext` section by section.

    Each section can be populated independently and is tracked with a
    ``_complete`` flag.  Use :meth:`is_complete` to check whether a section
    has been filled, and :meth:`build` to get the final dict.

    Sections
    --------
    - ``rules``
    - ``env``
    - ``repository_info``
    - ``tools``
    - ``mcp_instructions``
    - ``agent_skills``
    - ``custom_subagents``
    - ``git_status``
    """

    VALID_SECTIONS = frozenset({
        "rules",
        "env",
        "repository_info",
        "tools",
        "mcp_instructions",
        "agent_skills",
        "custom_subagents",
        "git_status",
    })

    def __init__(self) -> None:
        self._sections: dict[str, Any] = {s: None for s in self.VALID_SECTIONS}
        self._complete: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_section(self, name: str, data: Any) -> RequestContextBuilder:
        """Set the content for *name* and mark it complete.

        Parameters
        ----------
        name : str
            One of the valid section names (see class docs).
        data : Any
            The section payload.

        Returns
        -------
        RequestContextBuilder
            Self for chaining.
        """
        self._validate(name)
        self._sections[name] = data
        self._complete.add(name)
        return self

    def is_complete(self, section: str) -> bool:
        """Return ``True`` if *section* has been added via :meth:`add_section`."""
        self._validate(section)
        return section in self._complete

    def build(self) -> dict[str, Any]:
        """Return a flat dict with all sections and their ``_complete`` flags.

        The returned dict is suitable for constructing a :class:`RequestContext`
        or for sending as a JSON payload.
        """
        result: dict[str, Any] = {}
        for section in self.VALID_SECTIONS:
            value = self._sections[section]
            result[section] = value if value is not None else _default_for(section)
            result[f"{section}_complete"] = section in self._complete
        return result

    def build_model(self) -> RequestContext:
        """Return a fully populated :class:`RequestContext`."""
        return RequestContext(**self.build())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate(self, name: str) -> None:
        if name not in self.VALID_SECTIONS:
            valid = ", ".join(sorted(self.VALID_SECTIONS))
            raise ValueError(
                f"Unknown section {name!r}. Valid sections: {valid}"
            )


# ---------------------------------------------------------------------------
# Default values for each section (used when a section hasn't been set)
# ---------------------------------------------------------------------------

def _default_for(section: str) -> Any:
    defaults: dict[str, Any] = {
        "rules": "",
        "env": {},
        "repository_info": {},
        "tools": {},
        "mcp_instructions": "",
        "agent_skills": [],
        "custom_subagents": [],
        "git_status": "",
    }
    return defaults.get(section)
