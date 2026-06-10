#!/usr/bin/env python3
"""Run a Codex-style agent-loop controller behind Telegram."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent_loop.telegram import TelegramCodexAgent
from agent_loop.telegram_pairing import TelegramPairing


API = "https://api.telegram.org/bot{token}/{method}"


def telegram(method: str, **params: Any) -> dict[str, Any]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    response = httpx.post(API.format(token=token, method=method), json=params, timeout=60)
    response.raise_for_status()
    return response.json()


def send(chat_id: int, text: str) -> None:
    for i in range(0, len(text), 3500):
        telegram("sendMessage", chat_id=chat_id, text=text[i : i + 3500] or " ")


def main() -> None:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    if not os.environ.get("AGENT_LOOP_MODEL"):
        raise SystemExit("Set AGENT_LOOP_MODEL")

    agent = TelegramCodexAgent()
    pairing = TelegramPairing()
    if not pairing.allowed_chat_id():
        print(f"Telegram pairing code: /confirm {pairing.pairing_code}", file=sys.stderr)
    offset = 0

    while True:
        updates = telegram("getUpdates", offset=offset, timeout=30).get("result", [])
        for update in updates:
            offset = max(offset, update["update_id"] + 1)
            message = update.get("message") or {}
            text = message.get("text") or ""
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if not chat_id or not text:
                continue
            allowed, gate_reply = pairing.authorize(chat_id, text)
            if not allowed:
                send(chat_id, gate_reply or "Unauthorized chat.")
                continue
            if gate_reply and text.strip().lower().startswith("/confirm "):
                send(chat_id, gate_reply)
                continue
            try:
                reply = agent.handle_text(chat_id, text)
            except Exception as exc:
                reply = f"Agent error: {exc}"
            if reply:
                send(chat_id, reply)
        time.sleep(1)


if __name__ == "__main__":
    main()
