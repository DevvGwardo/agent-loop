"""Persisted provider/model configuration, Hermes-agent style.

Mirrors the hermes-agent config schema (``model``, ``providers``,
``model_aliases``) but stored as JSON at ``~/.agent-loop/config.json`` so no
yaml dependency is needed:

.. code-block:: json

    {
      "model": {"default": "gpt-4o-mini", "provider": "openai", "base_url": ""},
      "providers": {
        "my-ollama": {
          "name": "Ollama local",
          "base_url": "http://localhost:11434/v1",
          "api_key": "",
          "key_env": "OLLAMA_API_KEY",
          "model": "qwen3:8b",
          "models": ["qwen3:8b", "llama3:70b"]
        }
      },
      "model_aliases": {
        "fast": {"model": "llama-3.3-70b-versatile", "provider": "groq"}
      }
    }

Resolution order for a provider's API key: explicit ``api_key`` in config →
``key_env`` env var → the provider's builtin env var (e.g. ``GROQ_API_KEY``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Builtin providers: slug -> (base_url, api_key_env, default_model)
BUILTIN_PROVIDERS: dict[str, tuple[str, str, str]] = {
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "anthropic/claude-3.5-sonnet"),
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "deepseek-chat"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY", "grok-2-latest"),
    "mistral": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY", "mistral-large-latest"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY", "accounts/fireworks/models/llama-v3p3-70b-instruct"),
    "ollama": ("http://localhost:11434/v1", "OLLAMA_API_KEY", "qwen2.5-coder:7b"),
}


def config_path() -> Path:
    base = os.environ.get("AGENT_LOOP_CONFIG_DIR") or os.path.join(Path.home(), ".agent-loop")
    return Path(base) / "config.json"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(path)


def provider_entry(cfg: dict[str, Any], slug: str) -> dict[str, Any] | None:
    """Return a normalized provider entry for *slug* (config or builtin)."""
    entry = (cfg.get("providers") or {}).get(slug)
    if isinstance(entry, dict):
        builtin = BUILTIN_PROVIDERS.get(slug)
        return {
            "name": entry.get("name", slug),
            "base_url": entry.get("base_url") or (builtin[0] if builtin else ""),
            "api_key": entry.get("api_key", ""),
            "key_env": entry.get("key_env") or (builtin[1] if builtin else ""),
            "model": entry.get("model") or (builtin[2] if builtin else ""),
            "models": _normalize_models(entry.get("models")),
        }
    builtin = BUILTIN_PROVIDERS.get(slug)
    if builtin:
        base_url, key_env, default_model = builtin
        return {
            "name": slug,
            "base_url": base_url,
            "api_key": "",
            "key_env": key_env,
            "model": default_model,
            "models": [],
        }
    return None


def list_provider_slugs(cfg: dict[str, Any]) -> list[str]:
    return sorted({*BUILTIN_PROVIDERS, *(cfg.get("providers") or {})})


def resolve_api_key(entry: dict[str, Any]) -> str | None:
    """api_key in config → key_env env var → None."""
    if entry.get("api_key"):
        return str(entry["api_key"])
    key_env = entry.get("key_env")
    if key_env and os.environ.get(key_env):
        return os.environ[key_env]
    return None


def resolve_alias(cfg: dict[str, Any], name: str) -> dict[str, Any] | None:
    alias = (cfg.get("model_aliases") or {}).get(name)
    return alias if isinstance(alias, dict) else None


def _normalize_models(models: Any) -> list[str]:
    if isinstance(models, dict):
        return list(models)
    if isinstance(models, list):
        return [str(m) for m in models]
    return []


__all__ = [
    "BUILTIN_PROVIDERS",
    "config_path",
    "load_config",
    "save_config",
    "provider_entry",
    "list_provider_slugs",
    "resolve_api_key",
    "resolve_alias",
]
