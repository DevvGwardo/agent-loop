"""Tests for Telegram chat pairing."""

from __future__ import annotations

from agent_loop.telegram_pairing import TelegramPairing


def test_pairing_requires_confirm_code(tmp_path) -> None:
    store = TelegramPairing(tmp_path / "pairing.json")
    allowed, reply = store.authorize(123, "hello")
    assert allowed is False
    assert "/confirm" in (reply or "")


def test_confirm_pairs_chat(tmp_path) -> None:
    store = TelegramPairing(tmp_path / "pairing.json")
    code = store.pairing_code
    allowed, reply = store.authorize(456, f"/confirm {code}")
    assert allowed is True
    assert store.is_allowed(456)
    assert reply and "paired" in reply.lower()
