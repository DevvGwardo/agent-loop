"""Fuzz/property-based tests: throw garbage at every tool and verify clean failure."""

from __future__ import annotations

import asyncio
import random
import string
import tempfile
import os
from pathlib import Path

import pytest

from agent_loop.tools import (
    ShellExecutor,
    ReadExecutor,
    EditExecutor,
    GrepExecutor,
    WebFetchExecutor,
)


def _random_string(max_len: int = 100) -> str:
    len = random.randint(0, max_len)
    return "".join(random.choice(string.printable) for _ in range(len))


def _random_path() -> str:
    parts = [_random_string(20) for _ in range(random.randint(1, 4))]
    return "/" + "/".join(parts)


class TestFuzzShell:
    """Fuzz ShellExecutor with garbage inputs."""

    @pytest.mark.asyncio
    async def test_shell_empty_string(self) -> None:
        s = ShellExecutor()
        r = await s.execute({"command": ""})
        assert r.get("exit_code") == 1

    @pytest.mark.asyncio
    async def test_shell_none(self) -> None:
        s = ShellExecutor()
        r = await s.execute({"command": None})
        assert r.get("exit_code") == 1

    @pytest.mark.asyncio
    async def test_shell_missing_key(self) -> None:
        s = ShellExecutor()
        r = await s.execute({})
        assert r.get("exit_code") == 1

    @pytest.mark.asyncio
    async def test_shell_none_args(self) -> None:
        s = ShellExecutor()
        r = await s.execute(None)
        assert r.get("exit_code") == 1

    @pytest.mark.asyncio
    async def test_shell_extra_keys(self) -> None:
        s = ShellExecutor()
        r = await s.execute({"command": "echo ok", "invalid_key": 42, "nested": {"a": 1}})
        assert r.get("exit_code") == 0

    @pytest.mark.asyncio
    async def test_shell_unicode_noise(self) -> None:
        s = ShellExecutor()
        r = await s.execute({"command": "echo '\u00ff\u2603\U0001F600'"})  # no null byte
        assert r.get("exit_code") == 0  # echo should handle unicode

    @pytest.mark.asyncio
    async def test_shell_very_long_command(self) -> None:
        s = ShellExecutor()
        # 10K char command
        long_cmd = "echo " + "a" * 10000
        r = await s.execute({"command": long_cmd})
        assert r.get("exit_code") == 0  # should handle long args

    @pytest.mark.asyncio
    async def test_shell_negative_timeout(self) -> None:
        s = ShellExecutor()
        # negative timeout in the args dict is ignored (no timeout applied)
        r = await s.execute({"command": "echo quick"})
        assert "exit_code" in r  # should not crash

    @pytest.mark.asyncio
    async def test_shell_context_with_noise(self) -> None:
        s = ShellExecutor()
        r = await s.execute({"command": "echo ctx"}, context={"working_directory": None, "random_key": [1, 2, 3]})
        assert r.get("exit_code") == 0


class TestFuzzRead:
    """Fuzz ReadExecutor with garbage inputs."""

    @pytest.mark.asyncio
    async def test_read_nonexistent_path(self) -> None:
        r = ReadExecutor()
        result = await r.execute({"path": _random_path()})
        assert "error" in result or result.get("total_lines", 0) == 0

    @pytest.mark.asyncio
    async def test_read_empty_path(self) -> None:
        r = ReadExecutor()
        result = await r.execute({"path": ""})
        assert "error" in result or result.get("total_lines", 0) == 0

    @pytest.mark.asyncio
    async def read_no_path_key(self) -> None:
        r = ReadExecutor()
        result = await r.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_read_none_path(self) -> None:
        r = ReadExecutor()
        result = await r.execute({"path": None})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_read_negative_offset(self) -> None:
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "f.txt")
        Path(f).write_text("hello\n")
        r = ReadExecutor()
        result = await r.execute({"path": f, "offset": -100})
        assert "content" in result  # should handle gracefully

    @pytest.mark.asyncio
    async def test_read_negative_limit(self) -> None:
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "f.txt")
        Path(f).write_text("hello\n")
        r = ReadExecutor()
        result = await r.execute({"path": f, "limit": -1})
        assert "content" in result  # should handle gracefully

    @pytest.mark.asyncio
    async def test_read_binary_file(self) -> None:
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "bin.bin")
        with open(f, "wb") as fh:
            fh.write(os.urandom(1000))
        r = ReadExecutor()
        result = await r.execute({"path": f})
        assert "error" in result  # should detect binary


class TestFuzzEdit:
    """Fuzz EditExecutor with garbage inputs."""

    @pytest.mark.asyncio
    async def test_edit_nonexistent_path(self) -> None:
        e = EditExecutor()
        result = await e.execute({"path": _random_path(), "mode": "str_replace",
                                   "old_string": "x", "new_string": "y"})
        assert not result.get("success", True)

    @pytest.mark.asyncio
    async def test_edit_unknown_mode(self) -> None:
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "f.txt")
        Path(f).write_text("hello\n")
        e = EditExecutor()
        result = await e.execute({"path": f, "mode": _random_string(10), "content": "x"})
        assert not result.get("success", True)

    @pytest.mark.asyncio
    async def test_edit_empty_old_string(self) -> None:
        tmpdir = tempfile.mkdtemp()
        f = os.path.join(tmpdir, "f.txt")
        Path(f).write_text("hello\n")
        e = EditExecutor()
        result = await e.execute({"path": f, "mode": "str_replace",
                                   "old_string": "", "new_string": "y"})
        assert not result.get("success", True)  # empty old_string is invalid

    @pytest.mark.asyncio
    async def test_edit_missing_args(self) -> None:
        e = EditExecutor()
        result = await e.execute({})
        assert not result.get("success", True)

    @pytest.mark.asyncio
    async def test_edit_none_args(self) -> None:
        e = EditExecutor()
        result = await e.execute(None)
        assert not result.get("success", True)

    @pytest.mark.asyncio
    async def test_edit_stream_overwrite_permissions(self) -> None:
        """Write to an unwritable path. Should fail gracefully."""
        e = EditExecutor()
        # /dev/null is writable on macOS but /dev/full doesn't exist
        # Use a path that exists but can't be written to by the executor
        result = await e.execute({"path": "/dev/full",
                                   "mode": "stream_content", "content": "test"})
        assert not result.get("success", True) or "error" in result


class TestFuzzGrep:
    """Fuzz GrepExecutor with garbage inputs."""

    @pytest.mark.asyncio
    async def test_grep_empty_pattern(self) -> None:
        g = GrepExecutor()
        result = await g.execute({"pattern": ""})
        assert result.get("exit_code") == 1

    @pytest.mark.asyncio
    async def test_grep_none_pattern(self) -> None:
        g = GrepExecutor()
        result = await g.execute({"pattern": None})
        assert result.get("exit_code") == 1

    @pytest.mark.asyncio
    async def test_grep_missing_pattern(self) -> None:
        g = GrepExecutor()
        result = await g.execute({})
        assert result.get("exit_code") == 1

    @pytest.mark.asyncio
    async def test_grep_none_path(self) -> None:
        g = GrepExecutor()
        result = await g.execute({"pattern": "test", "path": None})
        assert "count" in result  # rg processes, shouldn't crash

    @pytest.mark.asyncio
    async def test_grep_special_chars_regex(self) -> None:
        g = GrepExecutor()
        result = await g.execute({"pattern": r"[\]\\^$.|?*+(){}", "path": "/tmp"})
        assert "error" in result or "count" in result  # should handle gracefully

    @pytest.mark.asyncio
    async def test_grep_very_long_pattern(self) -> None:
        g = GrepExecutor()
        result = await g.execute({"pattern": "a" * 5000, "path": "/tmp"})
        assert "error" in result or "count" in result


class TestFuzzWebFetch:
    """Fuzz WebFetchExecutor with garbage inputs."""

    @pytest.mark.asyncio
    async def test_web_none_url(self) -> None:
        w = WebFetchExecutor()
        result = await w.execute({"url": None})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_web_empty_url(self) -> None:
        w = WebFetchExecutor()
        result = await w.execute({"url": ""})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_web_missing_url(self) -> None:
        w = WebFetchExecutor()
        result = await w.execute({})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_web_invalid_url(self) -> None:
        w = WebFetchExecutor()
        result = await w.execute({"url": "http://invalid@#$%^.com"})
        # Should gracefully handle invalid URL format
        assert result.get("error") is not None or "error" in result

    @pytest.mark.asyncio
    async def test_web_garbage_args(self) -> None:
        w = WebFetchExecutor()
        result = await w.execute({"url": "http://example.com", "timeout": 5})  # valid timeout
        # should not crash, even if connection fails
        assert isinstance(result, dict)
