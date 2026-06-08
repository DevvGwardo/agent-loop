"""LLM integration — connect a real model to the agent's tool loop.

Pick a provider by name and a model id, then run::

    from agent_loop.llm import LLMAgent
    from agent_loop.tools import ShellExecutor, ReadExecutor

    agent = LLMAgent(provider="openai", model="gpt-4.1",
                     executors=[ShellExecutor(), ReadExecutor()])
    for event in agent.run("list the python files"):
        print(event)
"""
from .agent import Approver, LLMAgent
from .providers import (
    AnthropicProvider,
    LLMResponse,
    LLMToolCall,
    OpenAICompatibleProvider,
    Provider,
    ScriptedProvider,
    get_provider,
    list_providers,
)

__all__ = [
    "LLMAgent",
    "Approver",
    "Provider",
    "OpenAICompatibleProvider",
    "AnthropicProvider",
    "ScriptedProvider",
    "LLMResponse",
    "LLMToolCall",
    "get_provider",
    "list_providers",
]
