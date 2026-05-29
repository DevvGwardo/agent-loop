"""Tests for RequestContextBuilder and RequestContext models."""

from __future__ import annotations

import pytest

from agent_loop.context import RequestContextBuilder
from agent_loop.context.models import (
    RequestContext,
    AgentSkill,
    CursorRule,
    SelectedContext,
    SelectedType,
    InvocationContext,
)


class TestRequestContextBuilder:
    """add_section(), is_complete(), build(), build_model()"""

    def test_build_empty(self) -> None:
        b = RequestContextBuilder()
        result = b.build()
        assert isinstance(result, dict)
        assert result["rules"] == ""
        assert result["rules_complete"] is False

    def test_add_section_marks_complete(self) -> None:
        b = RequestContextBuilder()
        b.add_section("rules", "all lowercase")
        assert b.is_complete("rules") is True
        assert b.is_complete("env") is False

    def test_is_complete_returns_false_before_add(self) -> None:
        b = RequestContextBuilder()
        assert b.is_complete("tools") is False

    def test_add_section_returns_self_for_chaining(self) -> None:
        b = RequestContextBuilder()
        ret = b.add_section("rules", "x")
        assert ret is b

    def test_build_after_multiple_sections(self) -> None:
        b = RequestContextBuilder()
        b.add_section("rules", "r1")
        b.add_section("env", {"K": "V"})
        b.add_section("tools", {"shell": True})
        result = b.build()
        assert result["rules"] == "r1"
        assert result["env"]["K"] == "V"
        assert result["tools"]["shell"] is True
        assert result["rules_complete"] is True
        assert result["env_complete"] is True
        assert result["tools_complete"] is True
        # sections not explicitly added
        assert result["mcp_instructions_complete"] is False
        assert result["mcp_instructions"] == ""

    def test_build_model_returns_requestcontext(self) -> None:
        b = RequestContextBuilder()
        b.add_section("rules", "use tabs")
        ctx = b.build_model()
        assert isinstance(ctx, RequestContext)
        assert ctx.rules == "use tabs"
        assert ctx.rules_complete is True

    def test_build_model_methods(self) -> None:
        b = RequestContextBuilder()
        b.add_section("env", {"PWD": "/tmp"})
        ctx = b.build_model()
        assert ctx.section_complete("env") is True
        assert ctx.section_complete("tools") is False

        ctx.mark_complete("tools")
        assert ctx.section_complete("tools") is True

    def test_invalid_section_raises_value_error(self) -> None:
        b = RequestContextBuilder()
        with pytest.raises(ValueError, match="Unknown section"):
            b.add_section("garbage", "x")

    def test_is_complete_invalid_section_raises(self) -> None:
        b = RequestContextBuilder()
        with pytest.raises(ValueError, match="Unknown section"):
            b.is_complete("fake")

    def test_all_sections_have_defaults(self) -> None:
        b = RequestContextBuilder()
        result = b.build()
        expected = {
            "rules", "env", "repository_info", "tools",
            "mcp_instructions", "agent_skills", "custom_subagents", "git_status",
        }
        for section in expected:
            assert section in result, f"missing section: {section}"
            assert f"{section}_complete" in result, f"missing _complete flag: {section}"


class TestRequestContextModel:
    """RequestContext Pydantic model field types and methods."""

    def test_default_values(self) -> None:
        ctx = RequestContext()
        assert ctx.rules == ""
        assert ctx.rules_complete is False
        assert ctx.env == {}
        assert ctx.env_complete is False
        assert isinstance(ctx.invocation, InvocationContext)
        assert ctx.invocation.working_directory == "."

    def test_section_complete_unknown_raises(self) -> None:
        ctx = RequestContext()
        with pytest.raises(KeyError, match="Unknown context section"):
            ctx.section_complete("not_a_section")

    def test_mark_complete_unknown_raises(self) -> None:
        ctx = RequestContext()
        with pytest.raises(KeyError, match="Unknown context section"):
            ctx.mark_complete("not_a_section")

    def test_mark_complete_then_check(self) -> None:
        ctx = RequestContext()
        assert ctx.rules_complete is False
        ctx.mark_complete("rules")
        assert ctx.rules_complete is True

    def test_section_complete_bool_coercion(self) -> None:
        ctx = RequestContext()
        ctx.mark_complete("env")
        assert ctx.section_complete("env") is True


class TestContextSubModels:
    """AgentSkill, CursorRule, SelectedContext, InvocationContext."""

    def test_agent_skill_defaults(self) -> None:
        skill = AgentSkill(name="repl", description="Python repl")
        assert skill.name == "repl"
        assert skill.description == "Python repl"
        assert skill.instructions == ""
        assert skill.enabled is True

    def test_agent_skill_disabled(self) -> None:
        skill = AgentSkill(name="danger", description="skip", enabled=False)
        assert skill.enabled is False

    def test_cursor_rule_global(self) -> None:
        rule = CursorRule(type="global", content="always import annotations")
        assert rule.type == "global"
        assert rule.file_pattern is None

    def test_cursor_rule_file_scoped(self) -> None:
        rule = CursorRule(type="file", content="noqa", file_pattern="*.py")
        assert rule.file_pattern == "*.py"

    def test_selected_context(self) -> None:
        sel = SelectedContext(type=SelectedType.TEXT, value="hello")
        assert sel.type == SelectedType.TEXT
        assert sel.label is None
        assert sel.path is None

    def test_selected_context_with_label(self) -> None:
        sel = SelectedContext(type=SelectedType.FILE, value="/tmp/x", label="x.py")
        assert sel.label == "x.py"

    def test_invocation_context_defaults(self) -> None:
        ctx = InvocationContext()
        assert ctx.working_directory == "."
        assert ctx.selected is None
        assert ctx.git_branch is None

    def test_invocation_context_full(self) -> None:
        ctx = InvocationContext(
            working_directory="/repo",
            git_branch="main",
            git_commit="abc123",
            git_diff="+new",
        )
        assert ctx.working_directory == "/repo"
        assert ctx.git_branch == "main"
        assert ctx.git_commit == "abc123"
        assert ctx.git_diff == "+new"
