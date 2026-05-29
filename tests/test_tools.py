"""Tests for tool executors — ReadExecutor, ShellExecutor, EditExecutor, WebFetchExecutor."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from agent_loop.tools import (
    EditExecutor,
    ReadExecutor,
    ShellExecutor,
    WebFetchExecutor,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir() -> str:
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def test_file(temp_dir: str) -> str:
    path = Path(temp_dir) / "test.txt"
    path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    return str(path)


@pytest.fixture
def context(temp_dir: str) -> dict:
    return {"working_directory": temp_dir}


# ── ReadExecutor ──────────────────────────────────────────────────────


class TestReadExecutor:
    @pytest.mark.asyncio
    async def test_reads_full_file(self, test_file: str) -> None:
        exec_ = ReadExecutor()
        result = await exec_.execute({"path": test_file}, {})
        assert result["success"] is True
        assert result["content"] == "line1\nline2\nline3\n"
        assert result["total_lines"] == 3

    @pytest.mark.asyncio
    async def test_read_with_offset(self, test_file: str) -> None:
        exec_ = ReadExecutor()
        result = await exec_.execute({"path": test_file, "offset": 6, "limit": 6}, {})
        assert result["success"] is True
        assert result["content"] == "line2\n"

    @pytest.mark.asyncio
    async def test_file_not_found(self) -> None:
        exec_ = ReadExecutor()
        result = await exec_.execute({"path": "/nonexistent/file.txt"}, {})
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_no_path(self) -> None:
        exec_ = ReadExecutor()
        result = await exec_.execute({}, {})
        assert result["success"] is False
        assert "No path" in result["error"]

    @pytest.mark.asyncio
    async def test_binary_file(self, temp_dir: str) -> None:
        binary = Path(temp_dir) / "binary.bin"
        binary.write_bytes(b"\x00\x01\x02\xff")
        exec_ = ReadExecutor()
        result = await exec_.execute({"path": str(binary)}, {})
        assert result["success"] is False
        assert "Binary" in result["error"]

    @pytest.mark.asyncio
    async def test_relative_path_resolved(self, temp_dir: str, context: dict) -> None:
        # Create file in temp_dir
        path = Path(temp_dir) / "sub" / "file.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content", encoding="utf-8")
        exec_ = ReadExecutor()
        result = await exec_.execute({"path": "sub/file.txt"}, context)
        assert result["success"] is True
        assert result["content"] == "content"


# ── ShellExecutor ─────────────────────────────────────────────────────


class TestShellExecutor:
    @pytest.mark.asyncio
    async def test_echo(self) -> None:
        exec_ = ShellExecutor()
        result = await exec_.execute({"command": "echo hello world"}, {})
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "hello world" in result["stdout"]

    @pytest.mark.asyncio
    async def test_exit_code(self) -> None:
        exec_ = ShellExecutor()
        result = await exec_.execute({"command": "exit 42"}, {})
        assert result["success"] is False
        assert result["exit_code"] == 42

    @pytest.mark.asyncio
    async def test_no_command(self) -> None:
        exec_ = ShellExecutor()
        result = await exec_.execute({}, {})
        assert result["success"] is False
        assert "No command" in result["stderr"]

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Timeout handling has issues on Python 3.14; needs investigation")
    async def test_timeout(self) -> None:
        """Use a command that hangs forever; timeout should kill it."""
        exec_ = ShellExecutor()
        result = await exec_.execute({"command": "while true; do :; done", "timeout": 1}, {})
        assert result["success"] is False
        err = (result.get("error") or "").lower()
        assert "timed out" in err or "timeout" in err

    @pytest.mark.asyncio
    async def test_needs_approval_dangerous(self) -> None:
        exec_ = ShellExecutor()
        assert exec_.needs_approval({"command": "rm -rf /"}) is True
        assert exec_.needs_approval({"command": "echo safe"}) is False

    @pytest.mark.asyncio
    async def test_working_directory(self, temp_dir: str) -> None:
        exec_ = ShellExecutor()
        result = await exec_.execute(
            {"command": "pwd", "working_directory": temp_dir}, {}
        )
        assert result["success"] is True
        assert temp_dir in result["stdout"]


# ── EditExecutor ──────────────────────────────────────────────────────


class TestEditExecutor:
    @pytest.mark.asyncio
    async def test_stream_content_writes_file(self, temp_dir: str) -> None:
        path = Path(temp_dir) / "new.txt"
        exec_ = EditExecutor()
        result = await exec_.execute(
            {"mode": "stream_content", "path": str(path), "content": "hello world"},
            {},
        )
        assert result["success"] is True
        assert path.read_text(encoding="utf-8") == "hello world"

    @pytest.mark.asyncio
    async def test_str_replace_modifies_file(self, test_file: str) -> None:
        exec_ = EditExecutor()
        result = await exec_.execute(
            {
                "mode": "str_replace",
                "path": test_file,
                "old_string": "line2",
                "new_string": "REPLACED",
            },
            {},
        )
        assert result["success"] is True
        content = Path(test_file).read_text(encoding="utf-8")
        assert "REPLACED" in content
        assert "line2" not in content

    @pytest.mark.asyncio
    async def test_str_replace_not_found(self, test_file: str) -> None:
        exec_ = EditExecutor()
        result = await exec_.execute(
            {
                "mode": "str_replace",
                "path": test_file,
                "old_string": "nonexistent",
                "new_string": "x",
            },
            {},
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_str_replace_not_unique(self, test_file: str) -> None:
        # Write file with duplicate content
        path = Path(test_file)
        path.write_text("dup\ndup\n")
        exec_ = EditExecutor()
        result = await exec_.execute(
            {"mode": "str_replace", "path": test_file, "old_string": "dup", "new_string": "x"},
            {},
        )
        assert result["success"] is False
        assert "appears 2 times" in result["error"]

    @pytest.mark.asyncio
    async def test_unknown_mode(self, test_file: str) -> None:
        exec_ = EditExecutor()
        result = await exec_.execute(
            {"mode": "unknown", "path": test_file}, {}
        )
        assert result["success"] is False
        assert "Unknown" in result["error"]

    @pytest.mark.asyncio
    async def test_no_path(self) -> None:
        exec_ = EditExecutor()
        result = await exec_.execute({"mode": "stream_content"}, {})
        assert result["success"] is False
        assert "No path" in result["error"]


# ── WebFetchExecutor (mock httpx) ─────────────────────────────────────


class TestWebFetchExecutor:
    """Tests for WebFetchExecutor using a mock MCP-like cache of URLs.

    Since WebFetchExecutor relies on httpx for real HTTP calls, we only
    test the validation paths here.  Full integration tests would require
    a live server or httpx mock.
    """

    @pytest.mark.asyncio
    async def test_no_url(self) -> None:
        exec_ = WebFetchExecutor()
        result = await exec_.execute({}, {})
        assert result["success"] is False
        assert "No url" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_url(self) -> None:
        exec_ = WebFetchExecutor()
        # This won't actually connect, but httpx might be missing
        result = await exec_.execute({"url": "http://invalid.example.test"}, {})
        # Should fail with some error (either httpx not installed or connection error)
        assert result["success"] is False
        assert result["error"]


class TestGrepExecutor:
    """Requires ripgrep (`brew install ripgrep`)."""

    @pytest.mark.asyncio
    async def test_name(self) -> None:
        from agent_loop.tools.grep import GrepExecutor
        exec_ = GrepExecutor()
        assert exec_.name == "grep"

    @pytest.mark.asyncio
    async def test_args_schema(self) -> None:
        from agent_loop.tools.grep import GrepExecutor
        exec_ = GrepExecutor()
        schema = exec_.args_schema()
        assert "pattern" in schema.get("required", [])

    @pytest.mark.asyncio
    async def test_search_no_matches(self) -> None:
        from agent_loop.tools.grep import GrepExecutor
        exec_ = GrepExecutor()
        result = await exec_.execute({"pattern": "XYZZY_NONEXISTENT_987654321", "path": "/dev/null"})
        assert result.get("count") == 0


class TestSkills:
    def test_load_and_get(self) -> None:
        from agent_loop.skills import SkillRegistry
        reg = SkillRegistry()
        reg.load_skill("test", "do something")
        skill = reg.get_skill("test")
        assert skill is not None
        assert skill.name == "test"
        assert skill.prompt == "do something"

    def test_auto_load_filter(self) -> None:
        from agent_loop.skills import SkillRegistry
        reg = SkillRegistry()
        reg.load_skill("auto1", "auto skill", auto_load=True)
        reg.load_skill("manual", "manual skill", auto_load=False)
        auto = reg.for_tool("shell")
        assert len(auto) == 1
        assert auto[0].name == "auto1"

    def test_merge(self) -> None:
        from agent_loop.skills import SkillRegistry
        a = SkillRegistry()
        b = SkillRegistry()
        a.load_skill("shared", "from a")
        b.load_skill("shared", "from b")
        b.load_skill("unique", "only b")
        a.merge(b)
        assert a.get_skill("shared").prompt == "from b"  # b wins
        assert a.get_skill("unique") is not None
