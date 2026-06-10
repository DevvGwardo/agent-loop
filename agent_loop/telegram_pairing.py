"""Fail-closed Telegram chat pairing for agent-loop bots."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path


class TelegramPairing:
    """Lock a Telegram bot to a single chat after ``/confirm <code>``."""

    def __init__(self, path: str | Path | None = None) -> None:
        default = Path.home() / ".agent-loop" / "telegram-pairing.json"
        self.path = Path(path or os.environ.get("AGENT_LOOP_TELEGRAM_PAIRING_FILE", default))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()
        env_code = os.environ.get("AGENT_LOOP_TELEGRAM_PAIRING_CODE")
        if env_code:
            self._data["code"] = env_code
        elif not self._data.get("code"):
            self._data["code"] = secrets.token_hex(3)
            self._save()

    @property
    def pairing_code(self) -> str:
        return str(self._data["code"])

    def allowed_chat_id(self) -> str | None:
        env_chat = os.environ.get("AGENT_LOOP_TELEGRAM_CHAT_ID")
        if env_chat:
            return str(env_chat)
        chat_id = self._data.get("chat_id")
        return str(chat_id) if chat_id else None

    def is_allowed(self, chat_id: int | str) -> bool:
        allowed = self.allowed_chat_id()
        return allowed is not None and str(chat_id) == allowed

    def authorize(self, chat_id: int | str, text: str) -> tuple[bool, str | None]:
        """Return ``(allowed, optional_reply)`` for an incoming message."""
        if self.is_allowed(chat_id):
            return True, None

        lowered = text.strip().lower()
        if lowered.startswith("/confirm "):
            code = text.strip().split(maxsplit=1)[1].strip()
            if code == self.pairing_code:
                self._data["chat_id"] = str(chat_id)
                self._save()
                return True, "Chat paired. You can now use the bot."
            return False, "Invalid pairing code."

        return False, (
            f"Unpaired chat. Send /confirm {self.pairing_code} to link this device.\n"
            f"(Pairing code is also printed on bot startup.)"
        )

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")


__all__ = ["TelegramPairing"]
