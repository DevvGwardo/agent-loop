"""Tests for the glob tool executor."""

from __future__ import annotations

import asyncio

from agent_loop.tools import GlobExecutor


def test_glob_finds_files(tmp_path) -> None:
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "b.txt").write_text("y", encoding="utf-8")

    result = asyncio.run(
        GlobExecutor().execute({"pattern": "*.py"}, {"working_directory": str(tmp_path)}),
    )
    assert result["success"] is True
    assert result["files"] == ["a.py"]
