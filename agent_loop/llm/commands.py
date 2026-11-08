"""Runtime slash commands, inherited from hermes-agent's command system.

Commands (dispatched before the LLM sees the prompt):

  /model                          show current model + how to switch
  /model <id> [--provider slug] [--global]
                                  switch model in-place; --global persists
  /provider <slug>                switch to a provider's default model
  /apikey <slug> <key>            set/update a provider API key (persisted)
  /addprovider <slug> <base_url> [model]
                                  register a custom OpenAI-compatible provider
  /addmodel <alias> <model_id> [--provider slug]
                                  register a model alias (hermes model_aliases)
  /models | /providers            list providers, keys, models, aliases
  /status                         current model/provider/config path
  /help                           command reference

Like hermes-agent: ``/model x`` is session-only (the live client is swapped
in-place); ``--global`` writes ``model.default``/``model.provider`` to config.
"""

from __future__ import annotations

from dataclasses import dataclass

from .chat import OpenAICompatibleChatClient
from .config import (
    BUILTIN_PROVIDERS,
    config_path,
    list_provider_slugs,
    load_config,
    provider_entry,
    resolve_alias,
    resolve_api_key,
    save_config,
)

HELP_TEXT = """Commands:
  /model <id> [--provider <slug>] [--global]   switch model (session; --global persists)
  /provider <slug>                             switch to provider's default model
  /apikey <slug> <key>                         set provider API key (saved to config)
  /addprovider <slug> <base_url> [model]       add a custom provider endpoint
  /addmodel <alias> <model_id> [--provider s]  add a model alias
  /models                                      list providers, models, aliases
  /status                                      show active model + config
  /shell <command>                             run a shell command
  /mission <objective>                         drive the master loop
  /help                                        this help"""


@dataclass
class CommandResult:
    reply: str
    model_label: str | None = None  # set when the active model changed
    client: object | None = None    # new chat client when switched


def is_command(text: str) -> bool:
    return text.startswith("/") and text.split(None, 1)[0].lstrip("/") in {
        "model", "provider", "apikey", "addprovider", "addmodel",
        "models", "providers", "status", "help",
    }


def handle_command(text: str, *, current_label: str) -> CommandResult:
    parts = text.split()
    cmd = parts[0].lstrip("/")
    args = parts[1:]

    if cmd == "help":
        return CommandResult(reply=HELP_TEXT)
    if cmd == "status":
        return CommandResult(
            reply=f"model: {current_label}\nconfig: {config_path()}"
        )
    if cmd in {"models", "providers"}:
        return CommandResult(reply=_list_models())
    if cmd == "model":
        return _cmd_model(args, current_label=current_label)
    if cmd == "provider":
        if not args:
            return CommandResult(reply="Usage: /provider <slug>")
        return _cmd_model(["--provider", args[0]], current_label=current_label)
    if cmd == "apikey":
        return _cmd_apikey(args)
    if cmd == "addprovider":
        return _cmd_addprovider(args)
    if cmd == "addmodel":
        return _cmd_addmodel(args)
    return CommandResult(reply=f"Unknown command: /{cmd}\n\n{HELP_TEXT}")


# ─── /model ───────────────────────────────────────────────────────────


def _parse_model_flags(args: list[str]) -> tuple[str | None, str | None, bool]:
    """hermes parse_model_flags: -> (model_input, explicit_provider, is_global)."""
    model_input: str | None = None
    provider: str | None = None
    is_global = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--provider" and i + 1 < len(args):
            provider = args[i + 1]
            i += 2
        elif arg == "--global":
            is_global = True
            i += 1
        elif model_input is None:
            model_input = arg
            i += 1
        else:
            i += 1
    return model_input, provider, is_global


def _cmd_model(args: list[str], *, current_label: str) -> CommandResult:
    cfg = load_config()
    model_input, slug, is_global = _parse_model_flags(args)

    if not model_input and not slug:
        return CommandResult(
            reply=f"Current model: {current_label}\n\n{_list_models()}\n"
            "Switch with: /model <id> [--provider <slug>] [--global]"
        )

    # Alias resolution (hermes model_aliases) before anything else.
    if model_input:
        alias = resolve_alias(cfg, model_input)
        if alias:
            slug = slug or alias.get("provider")
            model_input = alias.get("model", model_input)

    slug = slug or _infer_provider(cfg, current_label)
    entry = provider_entry(cfg, slug)
    if entry is None:
        return CommandResult(
            reply=f"Unknown provider '{slug}'. Known: {', '.join(list_provider_slugs(cfg))}\n"
            "Add one with /addprovider <slug> <base_url>."
        )

    model = model_input or entry["model"]
    if not model:
        return CommandResult(reply=f"Provider '{slug}' has no default model; use /model <id> --provider {slug}")

    api_key = resolve_api_key(entry)
    # Custom/local endpoints (ollama etc.) may legitimately be keyless.
    if not api_key and slug in BUILTIN_PROVIDERS and slug != "ollama":
        return CommandResult(
            reply=f"No API key for '{slug}'. Set it with /apikey {slug} <key> "
            f"or export {entry.get('key_env') or 'an API key env var'}."
        )

    client = OpenAICompatibleChatClient(model=model, api_key=api_key, base_url=entry["base_url"])
    label = f"{slug}:{model}"

    persisted = ""
    if is_global:
        cfg.setdefault("model", {})
        cfg["model"] = {"default": model, "provider": slug, "base_url": entry["base_url"]}
        save_config(cfg)
        persisted = " (saved as default)"

    return CommandResult(reply=f"Switched to {label}{persisted}", model_label=label, client=client)


def _infer_provider(cfg: dict, current_label: str) -> str:
    if ":" in current_label:
        return current_label.split(":", 1)[0]
    model_cfg = cfg.get("model")
    if isinstance(model_cfg, dict) and model_cfg.get("provider"):
        return model_cfg["provider"]
    return "openai"


# ─── /apikey, /addprovider, /addmodel ────────────────────────────────


def _cmd_apikey(args: list[str]) -> CommandResult:
    if len(args) != 2:
        return CommandResult(reply="Usage: /apikey <provider-slug> <key>")
    slug, key = args
    cfg = load_config()
    cfg.setdefault("providers", {}).setdefault(slug, {})["api_key"] = key
    save_config(cfg)
    return CommandResult(
        reply=f"API key saved for '{slug}' ({config_path()}, mode 600).\n"
        f"Activate with: /provider {slug}"
    )


def _cmd_addprovider(args: list[str]) -> CommandResult:
    if len(args) < 2:
        return CommandResult(reply="Usage: /addprovider <slug> <base_url> [default_model]")
    slug, base_url = args[0], args[1]
    if not base_url.startswith(("http://", "https://")):
        return CommandResult(reply=f"base_url must be an http(s) URL, got: {base_url}")
    cfg = load_config()
    entry = cfg.setdefault("providers", {}).setdefault(slug, {})
    entry["name"] = entry.get("name", slug)
    entry["base_url"] = base_url
    if len(args) > 2:
        entry["model"] = args[2]
    save_config(cfg)
    return CommandResult(
        reply=f"Provider '{slug}' registered → {base_url}\n"
        f"Set a key with /apikey {slug} <key>, then /provider {slug}"
    )


def _cmd_addmodel(args: list[str]) -> CommandResult:
    if len(args) < 2:
        return CommandResult(reply="Usage: /addmodel <alias> <model_id> [--provider <slug>]")
    name = args[0]
    model_id, provider, _ = _parse_model_flags(args[1:])
    if not model_id:
        return CommandResult(reply="Usage: /addmodel <alias> <model_id> [--provider <slug>]")
    cfg = load_config()
    alias: dict[str, str] = {"model": model_id}
    if provider:
        alias["provider"] = provider
    cfg.setdefault("model_aliases", {})[name] = alias
    save_config(cfg)
    return CommandResult(reply=f"Alias '{name}' → {model_id}" + (f" via {provider}" if provider else "") + "\nUse it with: /model " + name)


# ─── listings ────────────────────────────────────────────────────────


def _list_models() -> str:
    cfg = load_config()
    lines = ["Providers (✓ = API key available):"]
    for slug in list_provider_slugs(cfg):
        entry = provider_entry(cfg, slug) or {}
        has_key = "✓" if (resolve_api_key(entry) or slug == "ollama") else "✗"
        line = f"  {has_key} {slug:<12} default: {entry.get('model', '-')}"
        models = entry.get("models") or []
        if models:
            line += f"  models: {', '.join(models)}"
        lines.append(line)
    aliases = cfg.get("model_aliases") or {}
    if aliases:
        lines.append("Aliases:")
        for name, a in aliases.items():
            lines.append(f"  {name} → {a.get('model')}" + (f" ({a['provider']})" if a.get("provider") else ""))
    return "\n".join(lines)


__all__ = ["CommandResult", "handle_command", "is_command", "HELP_TEXT"]
