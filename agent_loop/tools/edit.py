"""File write/patch executor with str_replace and stream_content modes."""

import os
from pathlib import Path

from .base import ToolExecutor


class EditExecutor(ToolExecutor):
    """Write or patch file content on disk.

    Two modes
    ---------
    **str_replace** — find a unique string in the file and replace it.
       Parameters: ``path``, ``old_string``, ``new_string``.
       The old_string must appear exactly once (uniqueness check).

    **stream_content** — write the entire file content, overwriting
       whatever is there.  Parameters: ``path``, ``content``.
    """

    MAX_WRITE_SIZE = 10 * 1024 * 1024  # 10 MB safety cap

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "Write or patch file content. Supports two modes: "
            "'str_replace' — find a unique string and replace it (safe partial edit); "
            "'stream_content' — overwrite the entire file. "
            "Returns success: bool and optional error message."
        )

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        if context is None:
            context = {}
        mode: str = ""
        if args:
            mode = args.get("mode", "stream_content")

        if mode == "str_replace":
            return await self._str_replace(args, context)
        elif mode == "stream_content":
            return await self._stream_content(args, context)
        else:
            return {"success": False, "error": f"Unknown edit mode: {mode}"}

    # ------------------------------------------------------------------
    # str_replace mode
    # ------------------------------------------------------------------

    async def _str_replace(self, args: dict, context: dict) -> dict:
        file_path = self._resolve_path(args.get("path", ""), context)
        old_string: str = args.get("old_string", "")
        new_string: str = args.get("new_string", "")

        if not file_path:
            return {"success": False, "error": "No path provided"}
        if not old_string:
            return {"success": False, "error": "No old_string provided for str_replace"}

        path = Path(file_path)

        # Read existing content
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        try:
            existing = path.read_text(encoding="utf-8")
        except PermissionError as exc:
            return {"success": False, "error": f"Permission denied reading: {exc}"}
        except UnicodeDecodeError:
            return {"success": False, "error": "File is not UTF-8 text; cannot patch"}

        # Uniqueness check
        count = existing.count(old_string)
        if count == 0:
            return {"success": False, "error": "old_string not found in file"}
        if count > 1:
            return {
                "success": False,
                "error": f"old_string appears {count} times (must be unique). "
                "Include more surrounding context to disambiguate.",
            }

        new_content = existing.replace(old_string, new_string, 1)

        if len(new_content.encode("utf-8")) > self.MAX_WRITE_SIZE:
            return {"success": False, "error": f"Resulting file exceeds {self.MAX_WRITE_SIZE} byte limit"}

        try:
            path.write_text(new_content, encoding="utf-8")
        except PermissionError as exc:
            return {"success": False, "error": f"Permission denied writing: {exc}"}
        except OSError as exc:
            return {"success": False, "error": f"OS error writing file: {exc}"}

        return {"success": True, "mode": "str_replace"}

    # ------------------------------------------------------------------
    # stream_content mode
    # ------------------------------------------------------------------

    async def _stream_content(self, args: dict, context: dict) -> dict:
        file_path = self._resolve_path(args.get("path", ""), context)
        content: str = args.get("content", "")

        if not file_path:
            return {"success": False, "error": "No path provided"}

        path = Path(file_path)

        # Enforce size limit before writing
        encoded = content.encode("utf-8")
        if len(encoded) > self.MAX_WRITE_SIZE:
            return {"success": False, "error": f"Content exceeds {self.MAX_WRITE_SIZE} byte limit"}

        # Create parent directories if they don't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            path.write_text(content, encoding="utf-8")
        except PermissionError as exc:
            return {"success": False, "error": f"Permission denied writing: {exc}"}
        except OSError as exc:
            return {"success": False, "error": f"OS error writing file: {exc}"}

        return {"success": True, "mode": "stream_content"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(file_path: str, context: dict) -> str:
        if not file_path:
            return ""
        working_dir = context.get("working_directory")
        if working_dir and not os.path.isabs(file_path):
            return os.path.join(working_dir, file_path)
        return file_path
