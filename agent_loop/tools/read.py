"""File reader with offset/limit range support and graceful error handling."""
from __future__ import annotations


import os
from pathlib import Path

from .base import ToolExecutor


class ReadExecutor(ToolExecutor):
    """Read file contents with optional byte-range support.

    Handles ``offset`` (byte) and ``limit`` (byte) to read a portion of
    the file without loading the whole thing into memory.
    Gracefully returns structured errors for missing files, permission
    issues, and binary-content detection.
    """

    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB safety cap

    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return (
            "Read a file from disk. Supports offset (byte position to start at) "
            "and limit (max bytes to read). Returns content, total_lines, and "
            "an optional error field."
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        file_path: str = ""
        if args:
            file_path = args.get("path", "")
        if not file_path:
            return {"content": "", "total_lines": 0, "success": False, "error": "No path provided"}

        # Resolve relative to working directory from context if provided
        working_dir = context.get("working_directory") if context else None
        if working_dir and not os.path.isabs(file_path):
            file_path = os.path.join(working_dir, file_path)

        path = Path(file_path)

        # --- Path validation ------------------------------------------------
        if not path.exists():
            return {
                "content": "",
                "total_lines": 0,
                "success": False,
                "error": f"File not found: {file_path}",
            }

        if not path.is_file():
            return {
                "content": "",
                "total_lines": 0,
                "success": False,
                "error": f"Not a file: {file_path}",
            }

        try:
            stat = path.stat()
        except PermissionError as exc:
            return {
                "content": "",
                "total_lines": 0,
                "success": False,
                "error": f"Permission denied: {exc}",
            }

        if stat.st_size > self.MAX_FILE_SIZE:
            return {
                "content": "",
                "total_lines": 0,
                "success": False,
                "error": (
                    f"File too large ({stat.st_size} bytes > {self.MAX_FILE_SIZE} limit). "
                    f"Use offset/limit to read portions."
                ),
            }

        # --- Range parameters -----------------------------------------------
        offset: int = args.get("offset", 0)
        limit: int | None = args.get("limit")

        if offset < 0:
            offset = 0

        try:
            if limit is not None:
                with open(path, "rb") as f:
                    f.seek(offset)
                    raw = f.read(limit)
            else:
                if offset == 0:
                    raw = path.read_bytes()
                else:
                    with open(path, "rb") as f:
                        f.seek(offset)
                        raw = f.read()
        except PermissionError as exc:
            return {
                "content": "",
                "total_lines": 0,
                "success": False,
                "error": f"Permission denied reading file: {exc}",
            }
        except OSError as exc:
            return {
                "content": "",
                "total_lines": 0,
                "success": False,
                "error": f"OS error reading file: {exc}",
            }

        # Try to decode as UTF-8; fall back to showing byte count
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "content": "",
                "total_lines": 0,
                "success": False,
                "error": f"Binary file (not UTF-8 decodable), size={len(raw)} bytes",
            }

        total_lines = content.count("\n")
        if content and not content.endswith("\n"):
            total_lines += 1

        return {
            "content": content,
            "total_lines": total_lines,
            "success": True,
            "file_size": stat.st_size,
            "path": str(path.resolve()),
        }
