"""Auto-detect an OpenAI-compatible chat client from the environment.

Shared by the TUI bridge and the Telegram bot so both work with zero manual
``AGENT_LOOP_MODEL`` setup: if any provider API key is present we pick a sane
default model for it.
"""

from __future__ import annotations

import os

from .chat import OpenAICompatibleChatClient

# (api_key_env, base_url, default_model, label) ordered by detection priority.
AUTO_PROVIDERS: list[tuple[str, str, str, str]] = [
    ("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o-mini", "openai"),
    ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "anthropic/claude-3.5-sonnet", "openrouter"),
    ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "groq"),
    ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "deepseek-chat", "deepseek"),
    ("XAI_API_KEY", "https://api.x.ai/v1", "grok-2-latest", "xai"),
    ("TOGETHER_API_KEY", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "together"),
    ("FIREWORKS_API_KEY", "https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/llama-v3p3-70b-instruct", "fireworks"),
]


def detect_chat_client(
    *,
    model: str | None = None,
    base_url: str | None = None,
) -> tuple[OpenAICompatibleChatClient | None, str]:
    """Resolve a chat client from env. Returns ``(client, label)``.

    An explicit ``model`` (or ``AGENT_LOOP_MODEL``) wins; otherwise the first
    provider whose API key is set is used. ``label`` is ``"none"`` when nothing
    is configured.
    """

    model = model or os.environ.get("AGENT_LOOP_MODEL")
    base_url = base_url or os.environ.get("AGENT_LOOP_BASE_URL")

    if model:
        return (
            OpenAICompatibleChatClient(
                model=model,
                base_url=base_url or "https://api.openai.com/v1",
            ),
            model,
        )

    for key_env, provider_url, default_model, label in AUTO_PROVIDERS:
        if os.environ.get(key_env):
            return (
                OpenAICompatibleChatClient(
                    model=default_model,
                    api_key=os.environ[key_env],
                    base_url=base_url or provider_url,
                ),
                f"{label}:{default_model}",
            )

    return None, "none"


__all__ = ["AUTO_PROVIDERS", "detect_chat_client"]
