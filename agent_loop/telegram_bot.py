"""Always-on Telegram bot runner for the finetuner agent.

Long-polls Telegram, streams the agent's progress back to the chat as it works,
and runs prompts/missions in a per-chat worker thread so a `/stop` (or any other
command) stays responsive while a long autonomous mission is running.

Run it directly::

    python -m agent_loop.telegram_bot

Required env: ``TELEGRAM_BOT_TOKEN`` plus a model provider key (e.g.
``OPENAI_API_KEY``) or ``AGENT_LOOP_MODEL``. A repo-root ``.env`` is loaded
automatically if present.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from agent_loop.telegram import TelegramCodexAgent
from agent_loop.telegram_pairing import TelegramPairing

API = "https://api.telegram.org/bot{token}/{method}"
MAX_CHARS = 3500
SEND_THROTTLE_S = 0.35  # stay under Telegram's per-chat rate limit


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from a nearby .env without external deps."""
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


class TelegramBot:
    def __init__(self) -> None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not token:
            raise SystemExit("Set TELEGRAM_BOT_TOKEN")
        self.token = token
        self.agent = TelegramCodexAgent()
        self.pairing = TelegramPairing()
        self._busy: dict[str, bool] = {}
        self._last_send: dict[str, float] = {}

    # --- Telegram transport -------------------------------------------------
    def _call(self, method: str, **params: Any) -> dict[str, Any]:
        resp = httpx.post(API.format(token=self.token, method=method), json=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def send(self, chat_id: int | str, text: str) -> None:
        if not text:
            return
        # Gentle per-chat throttle so streamed updates don't trip rate limits.
        last = self._last_send.get(str(chat_id), 0.0)
        wait = SEND_THROTTLE_S - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        for i in range(0, len(text), MAX_CHARS):
            chunk = text[i : i + MAX_CHARS] or " "
            try:
                self._call("sendMessage", chat_id=chat_id, text=chunk)
            except Exception as exc:  # never let a send failure kill the loop
                print(f"send error: {exc}", file=sys.stderr)
        self._last_send[str(chat_id)] = time.monotonic()

    # --- Dispatch -----------------------------------------------------------
    @staticmethod
    def _is_heavy(text: str) -> bool:
        text = text.strip()
        if not text.startswith("/"):
            return True
        return text.split(maxsplit=1)[0].lower() in {"/mission", "/auto"}

    def dispatch(self, chat_id: int | str, text: str) -> None:
        cid = str(chat_id)
        if self._is_heavy(text):
            if self._busy.get(cid):
                self.send(cid, "⏳ Busy with a task. Send /stop to cancel it first.")
                return
            self._busy[cid] = True
            threading.Thread(target=self._run_worker, args=(cid, text), daemon=True).start()
        else:
            self._stream_to_chat(cid, text)

    def _run_worker(self, chat_id: str, text: str) -> None:
        try:
            self._stream_to_chat(chat_id, text)
        finally:
            self._busy[chat_id] = False

    def _stream_to_chat(self, chat_id: str, text: str) -> None:
        try:
            for chunk in self.agent.stream(chat_id, text):
                self.send(chat_id, chunk)
        except Exception as exc:
            self.send(chat_id, f"Agent error: {exc}")

    # --- Main loop ----------------------------------------------------------
    def run(self) -> None:
        if not self.pairing.allowed_chat_id():
            print(f"Telegram pairing code: send  /confirm {self.pairing.pairing_code}", file=sys.stderr)
        print(f"finetuner telegram bot online — model: {self.agent.model_label}", file=sys.stderr)

        offset = 0
        while True:
            try:
                updates = self._call("getUpdates", offset=offset, timeout=30).get("result", [])
            except Exception as exc:
                print(f"getUpdates error: {exc}", file=sys.stderr)
                time.sleep(3)
                continue

            for update in updates:
                offset = max(offset, update["update_id"] + 1)
                message = update.get("message") or update.get("edited_message") or {}
                text = (message.get("text") or "").strip()
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                if not chat_id or not text:
                    continue

                allowed, gate_reply = self.pairing.authorize(chat_id, text)
                if not allowed:
                    self.send(chat_id, gate_reply or "Unauthorized chat.")
                    continue
                if gate_reply and text.lower().startswith("/confirm "):
                    self.send(chat_id, gate_reply)
                    continue

                self.dispatch(chat_id, text)


def main() -> None:
    _load_dotenv()
    TelegramBot().run()


if __name__ == "__main__":
    main()
