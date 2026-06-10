"""Tests for workspace context injection."""

from __future__ import annotations

from agent_loop.harness import CodingAgentHarness
from agent_loop.workspace import build_workspace_context, compose_system_prompt, read_agents_md


def test_read_agents_md(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Rules\nAlways test.", encoding="utf-8")
    assert "Always test." in read_agents_md(str(tmp_path))


def test_build_workspace_context_includes_agents_and_path(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("Be careful.", encoding="utf-8")
    context = build_workspace_context(str(tmp_path))
    assert "AGENTS.md" in context
    assert "Be careful." in context
    assert str(tmp_path) in context


def test_harness_system_prompt_includes_agents_md(tmp_path) -> None:
    (tmp_path / "AGENTS.md").write_text("Use small diffs.", encoding="utf-8")
    harness = CodingAgentHarness(working_directory=str(tmp_path))
    system = harness.messages[0]["content"]
    assert "Use small diffs." in system


def test_compose_system_prompt_adds_mcp_instructions() -> None:
    prompt = compose_system_prompt("Base", mcp_instructions="Use sqlite for queries.")
    assert "Base" in prompt
    assert "Use sqlite for queries." in prompt
