"""Tests for ApprovalGates — three-tier policy, risk heuristics, pre/post check."""

from __future__ import annotations

import pytest

from agent_loop.approval import ApprovalGates, ApprovalLevel
from agent_loop.exceptions import ApprovalRequiredError


class TestApprovalGatesInit:
    """Default policy and constructor."""

    def test_default_policy_is_empty(self) -> None:
        gates = ApprovalGates()
        assert gates.policy == {}

    def test_smart_mode_default_off(self) -> None:
        gates = ApprovalGates()
        assert not hasattr(gates, '_smart_mode') or gates._smart_mode is False

    def test_policy_in_constructor(self) -> None:
        gates = ApprovalGates(policy={"shell": ApprovalLevel.PRE_CHECK})
        assert gates.get_level("shell") == ApprovalLevel.PRE_CHECK


class TestApprovalGatesPolicy:
    """set_policy(), update_policy(), get_level()."""

    def test_get_level_returns_valid_level(self) -> None:
        gates = ApprovalGates()
        level = gates.get_level("shell")
        assert isinstance(level, ApprovalLevel)
        assert level == ApprovalLevel.AUTO

    def test_get_level_unknown_tool_returns_auto(self) -> None:
        gates = ApprovalGates()
        level = gates.get_level("unknown_tool_xyz")
        assert level == ApprovalLevel.AUTO

    def test_set_policy_overrides(self) -> None:
        gates = ApprovalGates()
        gates.set_policy({"shell": ApprovalLevel.PRE_CHECK})
        assert gates.get_level("shell") == ApprovalLevel.PRE_CHECK

    def test_update_policy_merges(self) -> None:
        gates = ApprovalGates()
        gates.update_policy({"read": ApprovalLevel.POST_CHECK})
        assert gates.get_level("read") == ApprovalLevel.POST_CHECK
        # other defaults unchanged
        assert gates.get_level("grep") == ApprovalLevel.AUTO

    def test_set_policy_clears_previous(self) -> None:
        gates = ApprovalGates()
        gates.set_policy({"x": ApprovalLevel.PRE_CHECK})
        gates.set_policy({"y": ApprovalLevel.POST_CHECK})
        assert gates.get_level("x") == ApprovalLevel.AUTO  # wiped

    def test_policy_property_readonly_copy(self) -> None:
        gates = ApprovalGates()
        gates.set_policy({"a": ApprovalLevel.PRE_CHECK})
        pol = gates.policy
        pol["b"] = ApprovalLevel.POST_CHECK
        assert "b" not in gates.policy  # original unchanged


class TestApprovalGatesExecution:
    """check_pre_execution(), check_post_execution(), requires_confirmation()."""

    @pytest.mark.asyncio
    async def test_pre_execution_auto_approves(self) -> None:
        gates = ApprovalGates(policy={"shell": ApprovalLevel.AUTO})
        level = await gates.check_pre_execution("shell", {"command": "ls"})
        assert level == ApprovalLevel.AUTO

    @pytest.mark.asyncio
    async def test_pre_execution_blocks_pre_check(self) -> None:
        gates = ApprovalGates(policy={"shell": ApprovalLevel.PRE_CHECK})
        with pytest.raises(ApprovalRequiredError):
            await gates.check_pre_execution("shell", {"command": "rm -rf /"})

    @pytest.mark.asyncio
    async def test_requires_confirmation(self) -> None:
        gates = ApprovalGates()
        assert gates.requires_confirmation(ApprovalLevel.PRE_CHECK) is True
        assert gates.requires_confirmation(ApprovalLevel.POST_CHECK) is True
        assert gates.requires_confirmation(ApprovalLevel.AUTO) is False


class TestApprovalGatesEdgeCases:
    """Boundary conditions."""

    def test_empty_policy_set(self) -> None:
        gates = ApprovalGates()
        gates.set_policy({})
        assert gates.get_level("anything") == ApprovalLevel.AUTO

    def test_large_policy_set(self) -> None:
        gates = ApprovalGates()
        policy = {f"tool_{i}": ApprovalLevel.PRE_CHECK for i in range(100)}
        gates.set_policy(policy)
        assert gates.get_level("tool_50") == ApprovalLevel.PRE_CHECK
        assert gates.get_level("tool_99") == ApprovalLevel.PRE_CHECK

    def test_update_policy_empty_noop(self) -> None:
        gates = ApprovalGates()
        gates.set_policy({"x": ApprovalLevel.PRE_CHECK})
        gates.update_policy({})
        assert gates.get_level("x") == ApprovalLevel.PRE_CHECK

    def test_all_levels_coverage(self) -> None:
        gates = ApprovalGates()
        gates.set_policy({
            "shell": ApprovalLevel.AUTO,
            "edit": ApprovalLevel.PRE_CHECK,
            "read": ApprovalLevel.POST_CHECK,
        })
        assert gates.get_level("shell") == ApprovalLevel.AUTO
        assert gates.get_level("edit") == ApprovalLevel.PRE_CHECK
        assert gates.get_level("read") == ApprovalLevel.POST_CHECK
