"""Approval gates: pre/post-execution validation with three-tier policy."""

from __future__ import annotations

import enum
from typing import Any

# ---------------------------------------------------------------------------
# Approval levels
# ---------------------------------------------------------------------------


class ApprovalLevel(str, enum.Enum):
    """Three-tier approval classification for tool invocations."""

    # Auto-approve — tool runs without any human intervention.
    AUTO = "auto"
    # Pre-check — pause *before* execution and ask for confirmation.
    PRE_CHECK = "pre_check"
    # Post-check — run the tool, then present the result for confirmation.
    POST_CHECK = "post_check"


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

Policy = dict[str, ApprovalLevel]
"""Mapping from tool name → approval level.

Example::

    {
        "shell": ApprovalLevel.PRE_CHECK,
        "read": ApprovalLevel.AUTO,
        "edit": ApprovalLevel.PRE_CHECK,
        "web_fetch": ApprovalLevel.AUTO,
    }
"""


# ---------------------------------------------------------------------------
# Approval gates
# ---------------------------------------------------------------------------

class ApprovalGates:
    """Pre- and post-execution approval gates.

    The gates enforce a configurable policy that maps tool names to one of
    three tiers:

    - ``AUTO`` — no approval needed; the tool runs freely.
    - ``PRE_CHECK`` — human must approve *before* the tool runs.
    - ``POST_CHECK`` — tool runs, but the result is held for confirmation.

    **Smart mode** (``smart_mode=True``) downgrades ``PRE_CHECK`` to
    ``AUTO`` for tool calls that the executor itself marks as low-risk
    (i.e. ``executor.needs_approval(args)`` returns ``False``).  This lets
    you set a conservative default policy (e.g. always pre-check shell)
    while still auto-running innocuous commands like ``ls`` or ``echo``.
    """

    def __init__(
        self,
        policy: Policy | None = None,
        *,
        smart_mode: bool = False,
    ) -> None:
        """
        Parameters
        ----------
        policy : Policy, optional
            Tool-name → ApprovalLevel mapping.  Tools not listed default
            to ``AUTO``.  If ``None`` the policy is empty (all AUTO).
        smart_mode : bool
            If ``True``, call ``executor.needs_approval(args)`` to decide
            whether a ``PRE_CHECK`` rule actually needs human review.
        """
        self._policy: Policy = dict(policy or {})
        self._smart_mode = smart_mode

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    @property
    def policy(self) -> Policy:
        """Read-only view of the current policy."""
        return dict(self._policy)

    def set_policy(self, policy: Policy) -> None:
        """Replace the entire policy."""
        self._policy = dict(policy)

    def update_policy(self, overrides: Policy) -> None:
        """Merge *overrides* into the existing policy."""
        self._policy.update(overrides)

    def get_level(self, tool_name: str) -> ApprovalLevel:
        """Return the configured level for *tool_name* (default AUTO)."""
        return self._policy.get(tool_name, ApprovalLevel.AUTO)

    # ------------------------------------------------------------------
    # Core gate logic
    # ------------------------------------------------------------------

    async def check_pre_execution(
        self,
        tool_name: str,
        args: dict,
        executor: Any | None = None,
    ) -> ApprovalLevel:
        """Determine the actual approval level *before* a tool runs.

        Returns
        -------
        ApprovalLevel
            - ``AUTO`` — proceed without approval.
            - ``PRE_CHECK`` — require human approval before running.
        """
        level = self.get_level(tool_name)

        # Smart mode: downgrade PRE_CHECK → AUTO for low-risk invocations
        if self._smart_mode and level == ApprovalLevel.PRE_CHECK:
            if executor is not None and hasattr(executor, "needs_approval"):
                if not executor.needs_approval(args):
                    return ApprovalLevel.AUTO

        return level

    async def check_post_execution(
        self,
        tool_name: str,
        args: dict,
        result: dict,
        executor: Any | None = None,
    ) -> ApprovalLevel:
        """Determine the approval level *after* a tool has executed.

        Returns
        -------
        ApprovalLevel
            - ``AUTO`` — result is accepted immediately.
            - ``POST_CHECK`` — result should be presented for confirmation.
        """
        level = self.get_level(tool_name)
        if level == ApprovalLevel.POST_CHECK:
            return ApprovalLevel.POST_CHECK

        # Smart mode: also check PRE_CHECK tools post-hoc if we skipped
        # the pre-check (can be useful for audit-style approval).
        if self._smart_mode and level == ApprovalLevel.PRE_CHECK:
            if executor is not None and hasattr(executor, "needs_approval"):
                if executor.needs_approval(args):
                    # This one originally would have been pre-checked
                    # but wasn't (smart mode downgraded it); still fine
                    # to let it through since smart-mode said it's safe.
                    pass

        return ApprovalLevel.AUTO

    def requires_confirmation(self, level: ApprovalLevel) -> bool:
        """Return ``True`` if *level* requires user interaction."""
        return level in (ApprovalLevel.PRE_CHECK, ApprovalLevel.POST_CHECK)

    # ------------------------------------------------------------------
    # High-level helpers for orchestrators
    # ------------------------------------------------------------------

    async def should_auto_approve(
        self,
        tool_name: str,
        args: dict,
        executor: Any | None = None,
    ) -> bool:
        """Convenience: ``True`` if the tool can run without any approval."""
        level = await self.check_pre_execution(tool_name, args, executor)
        return level == ApprovalLevel.AUTO
