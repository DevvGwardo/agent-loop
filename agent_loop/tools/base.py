"""Abstract base class for all tool executors."""

from abc import ABC, abstractmethod


class ToolExecutor(ABC):
    """Base class that every tool executor must subclass.

    Lifecycle
    ---------
    1. on_start()             — called once before execution
    2. execute(args, context) — the main execution (may stream via on_delta)
    3. on_complete(result)    — called after execute returns

    All lifecycle methods are async and may be no-ops.
    """

    # ------------------------------------------------------------------
    # Required interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. ``"shell"``, ``"read"``."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        return self.__class__.__doc__ or ""

    @abstractmethod
    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        """Run the tool with *args* and return a result dict.

        Parameters
        ----------
        call_id : str
            Unique identifier for this tool invocation.
        args : dict
            Tool-specific arguments parsed from the model.
        context : dict, optional
            Shared execution context (e.g. ``{"working_directory": "/tmp"}``).

        Returns
        -------
        dict
            Must at minimum contain ``{"success": bool}``.  Additional keys
            are tool-specific (e.g. ``stdout``, ``content``, ``error``).
        """
        ...

    # ------------------------------------------------------------------
    # Lifecycle hooks  (default no-ops)
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        """Called once before :meth:`execute`."""

    async def on_delta(self, data: str | bytes) -> None:
        """Called with partial output during streaming execution.

        Not all executors stream; the default implementation is a no-op.
        """

    async def on_complete(self, result: dict) -> None:
        """Called after :meth:`execute` returns (even on failure)."""

    # ------------------------------------------------------------------
    # Approval gates
    # ------------------------------------------------------------------

    def needs_approval(self, args: dict) -> bool:
        """Return ``True`` if this invocation requires human approval.

        Override in subclasses to implement tool-specific heuristics.
        The default returns ``False`` (no approval needed).
        """
        return False
