"""Shell command executor with streaming output, timeout, and env support."""
from __future__ import annotations


import asyncio
import os
import shlex
import signal
from datetime import datetime, timezone

from .base import ToolExecutor


class ShellExecutor(ToolExecutor):
    """Execute shell commands via ``asyncio.create_subprocess_exec``.

    Capabilities
    ------------
    - Runs arbitrary commands with configurable working directory, timeout,
      and environment variables.
    - Streams stdout/stderr line-by-line through :meth:`on_delta`.
    - Returns combined exit code, stdout, and stderr.
    """

    @property
    def name(self) -> str:
        return "shell"

    @property
    def description(self) -> str:
        return (
            "Execute a shell command. Supports working_directory, "
            "timeout (seconds), and environment variable overrides."
        )

    # ------------------------------------------------------------------
    # Approval heuristics
    # ------------------------------------------------------------------

    def needs_approval(self, args: dict) -> bool:
        """Flag high-risk commands that should always require approval."""
        cmd = args.get("command", "")
        dangerous_prefixes = (
            "rm -rf /", "rm -rf --no-preserve-root", "mkfs",
            "dd if=", ":(){ :|:& };:", "chmod 000", "chown",
            "reboot", "shutdown", "poweroff", "halt",
            "wget ", "curl ", "nc ", "ncat ",
        )
        return cmd.strip().startswith(dangerous_prefixes)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        command: str = ""
        if args:
            command = args.get("command", "")
        if not command:
            return {"exit_code": 1, "stdout": "", "stderr": "No command provided", "success": False}

        working_directory: str | None = None
        timeout: int | None = None
        env_overrides: dict | None = None
        if args:
            working_directory = args.get("working_directory")
            timeout = args.get("timeout")
            env_overrides = args.get("env")
        if working_directory is None and context:
            working_directory = context.get("working_directory")

        # Build environment
        env = dict(os.environ)
        if env_overrides:
            env.update(env_overrides)

        # Shell out via exec so we don't need a shell wrapper
        executable = os.environ.get("SHELL", "/bin/bash")
        proc_args = [executable, "-c", command]

        try:
            proc = await asyncio.create_subprocess_exec(
                *proc_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
                env=env,
            )
        except (FileNotFoundError, PermissionError) as exc:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "success": False,
                "error": str(exc),
            }

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        async def _reader(stream: asyncio.StreamReader, lines: list[str], is_stderr: bool) -> None:
            while True:
                line_bytes = await stream.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                lines.append(line + "\n")
                await self.on_delta(line_bytes if is_stderr else line)

        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(
                    _reader(proc.stdout, stdout_lines, is_stderr=False),
                    _reader(proc.stderr, stderr_lines, is_stderr=True),
                )
        except TimeoutError:
            # Kill the process group
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                proc.kill()
            await proc.wait()
            return {
                "exit_code": -1,
                "stdout": "".join(stdout_lines),
                "stderr": "".join(stderr_lines) + f"\n[timed out after {timeout}s]",
                "success": False,
                "error": f"Command timed out after {timeout}s",
            }

        exit_code = await proc.wait()
        stdout_text = "".join(stdout_lines)
        stderr_text = "".join(stderr_lines)

        result = {
            "exit_code": exit_code,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "success": exit_code == 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return result

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        pass

    async def on_complete(self, result: dict) -> None:
        pass
