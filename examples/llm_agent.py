"""LLM-driven agent example.

Runs offline by default using a ScriptedProvider (no API key needed), so you
can see the full tool-calling loop immediately:

    python examples/llm_agent.py

To drive it with a real model, set environment variables and the matching
provider key, then run the same command:

    export LLM_PROVIDER=openrouter            # see agent_loop.llm.list_providers()
    export LLM_MODEL=anthropic/claude-sonnet-4-6
    export OPENROUTER_API_KEY=sk-...
    python examples/llm_agent.py

Providers: openai, openrouter, groq, deepseek, xai, mistral, together,
fireworks, ollama (local), anthropic.
"""
from __future__ import annotations

import os

from agent_loop.llm import LLMAgent, LLMResponse, LLMToolCall, ScriptedProvider, get_provider
from agent_loop.models import (
    ToolCallCompletedEvent,
    ToolCallDeltaEvent,
    ToolCallStartedEvent,
)
from agent_loop.tools import ReadExecutor, ShellExecutor


def build_agent() -> LLMAgent:
    executors = [ShellExecutor(), ReadExecutor()]
    provider_name = os.environ.get("LLM_PROVIDER")

    if provider_name:
        model = os.environ.get("LLM_MODEL")
        if not model:
            raise SystemExit("Set LLM_MODEL when using LLM_PROVIDER (e.g. gpt-4.1).")
        print(f"Provider: {provider_name}  Model: {model}\n")
        return LLMAgent(provider=get_provider(provider_name), model=model, executors=executors)

    # Offline demo: the scripted model asks for one shell call, then answers.
    print("Provider: scripted (offline demo — set LLM_PROVIDER to use a real model)\n")
    scripted = ScriptedProvider(
        [
            LLMResponse(tool_calls=[LLMToolCall(id="c1", name="shell", args={"command": "echo hello from the tool loop"})]),
            LLMResponse(text="Done — the shell printed: hello from the tool loop"),
        ]
    )
    return LLMAgent(provider=scripted, model="demo", executors=executors)


def main() -> None:
    agent = build_agent()
    prompt = "Run a shell command that prints a greeting, then tell me what it printed."
    print(f"Prompt: {prompt!r}\n\nEvents:")

    gen = agent.run(prompt)
    while True:
        try:
            event = next(gen)
        except StopIteration as exc:
            final_reply = exc.value
            break

        match event:
            case ToolCallStartedEvent():
                print(f"  [START]  {event.tool_name}  args={event.args}")
            case ToolCallDeltaEvent():
                print(f"  [DELTA]  {event.delta}")
            case ToolCallCompletedEvent():
                status = "OK" if event.error is None else f"ERROR: {event.error}"
                print(f"  [DONE]   {event.tool_name}  {status}")

    print(f"\nFinal reply:\n{final_reply}")


if __name__ == "__main__":
    main()
