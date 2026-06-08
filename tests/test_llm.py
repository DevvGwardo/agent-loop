"""Tests for the LLM integration: provider registry, wire translation, and loop."""
from __future__ import annotations

import json

import httpx
import pytest

from agent_loop.llm import (
    AnthropicProvider,
    LLMAgent,
    LLMResponse,
    LLMToolCall,
    OpenAICompatibleProvider,
    ScriptedProvider,
    get_provider,
    list_providers,
)
from agent_loop.tools import (
    EditExecutor,
    GrepExecutor,
    ReadExecutor,
    ShellExecutor,
    WebFetchExecutor,
    WebSearchExecutor,
)
from agent_loop.tools.base import ToolExecutor


# ── helpers ───────────────────────────────────────────────────────────


def drive(agent: LLMAgent, prompt: str):
    """Run an agent generator to completion; return (events, final_reply)."""
    events = []
    gen = agent.run(prompt)
    while True:
        try:
            events.append(next(gen))
        except StopIteration as exc:
            return events, exc.value


class FlaggedExecutor(ToolExecutor):
    """A harmless tool that always requires approval."""

    @property
    def name(self) -> str:
        return "flagged"

    def needs_approval(self, args: dict) -> bool:
        return True

    async def execute(self, args: dict | None = None, context: dict | None = None) -> dict:
        return {"success": True, "ran": True}


# ── registry ──────────────────────────────────────────────────────────


class TestRegistry:
    def test_list_providers_includes_known(self):
        names = list_providers()
        for expected in ("openai", "openrouter", "groq", "deepseek", "anthropic", "ollama", "scripted"):
            assert expected in names

    def test_get_openai_compatible(self):
        p = get_provider("openrouter", api_key="k")
        assert isinstance(p, OpenAICompatibleProvider)
        assert p.base_url == "https://openrouter.ai/api/v1"
        assert p.name == "openrouter"

    def test_get_anthropic(self):
        p = get_provider("anthropic", api_key="k")
        assert isinstance(p, AnthropicProvider)

    def test_missing_key_raises(self):
        with pytest.raises(RuntimeError):
            get_provider("openai")  # no api_key, no env var

    def test_ollama_needs_no_key(self):
        p = get_provider("ollama")  # local, key optional
        assert isinstance(p, OpenAICompatibleProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            get_provider("does-not-exist")


# ── OpenAI-compatible wire format ─────────────────────────────────────


class TestOpenAIWire:
    def test_parse_tool_call(self):
        data = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {"id": "x1", "function": {"name": "shell", "arguments": '{"command": "ls"}'}}
                        ],
                    }
                }
            ]
        }
        resp = OpenAICompatibleProvider._parse(data)
        assert resp.text == ""
        assert resp.tool_calls == [LLMToolCall(id="x1", name="shell", args={"command": "ls"})]

    def test_parse_text(self):
        data = {"choices": [{"message": {"content": "all done"}}]}
        resp = OpenAICompatibleProvider._parse(data)
        assert resp.text == "all done"
        assert resp.tool_calls == []

    def test_to_wire_tool_roundtrip(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "", "tool_calls": [LLMToolCall(id="x1", name="shell", args={"command": "ls"})]},
            {"role": "tool", "tool_call_id": "x1", "name": "shell", "content": "files"},
        ]
        wire = OpenAICompatibleProvider._to_wire("be helpful", messages)
        assert wire[0] == {"role": "system", "content": "be helpful"}
        assert wire[2]["tool_calls"][0]["function"]["name"] == "shell"
        assert wire[3] == {"role": "tool", "tool_call_id": "x1", "content": "files"}

    def test_chat_sends_request_and_parses(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"content": "pong"}}]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = OpenAICompatibleProvider(name="openai", base_url="https://api.test/v1", api_key="secret", client=client)
        resp = provider.chat(
            model="m", system="sys", messages=[{"role": "user", "content": "ping"}],
            tools=[{"name": "shell", "description": "run", "parameters": {"type": "object"}}],
        )
        assert resp.text == "pong"
        assert captured["headers"]["authorization"] == "Bearer secret"
        assert captured["body"]["tools"][0]["type"] == "function"
        assert captured["body"]["tools"][0]["function"]["name"] == "shell"

    def test_http_error_raises(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="nope")))
        provider = OpenAICompatibleProvider(name="openai", base_url="https://api.test/v1", api_key="k", client=client)
        with pytest.raises(RuntimeError, match="401"):
            provider.chat(model="m", system="", messages=[{"role": "user", "content": "x"}], tools=[])


# ── Anthropic wire format ─────────────────────────────────────────────


class TestAnthropicWire:
    def test_parse_blocks(self):
        data = {
            "content": [
                {"type": "text", "text": "thinking... "},
                {"type": "tool_use", "id": "t1", "name": "read", "input": {"path": "a.py"}},
            ]
        }
        resp = AnthropicProvider._parse(data)
        assert resp.text == "thinking... "
        assert resp.tool_calls == [LLMToolCall(id="t1", name="read", args={"path": "a.py"})]

    def test_to_wire_coalesces_tool_results(self):
        messages = [
            {"role": "user", "content": "go"},
            {"role": "assistant", "content": "", "tool_calls": [
                LLMToolCall(id="a", name="read", args={}),
                LLMToolCall(id="b", name="read", args={}),
            ]},
            {"role": "tool", "tool_call_id": "a", "name": "read", "content": "r1"},
            {"role": "tool", "tool_call_id": "b", "name": "read", "content": "r2"},
        ]
        wire = AnthropicProvider._to_wire(messages)
        # assistant turn has two tool_use blocks
        assert sum(1 for blk in wire[1]["content"] if blk["type"] == "tool_use") == 2
        # both tool results coalesced into ONE user message
        assert wire[2]["role"] == "user"
        assert [b["tool_use_id"] for b in wire[2]["content"]] == ["a", "b"]

    def test_chat_sends_headers(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = AnthropicProvider(api_key="abc", client=client)
        resp = provider.chat(
            model="claude", system="sys", messages=[{"role": "user", "content": "hi"}],
            tools=[{"name": "read", "description": "d", "parameters": {"type": "object"}}],
        )
        assert resp.text == "ok"
        assert captured["headers"]["x-api-key"] == "abc"
        assert captured["headers"]["anthropic-version"]
        assert captured["body"]["tools"][0]["input_schema"] == {"type": "object"}


# ── LLMAgent loop ─────────────────────────────────────────────────────


class TestLLMAgentLoop:
    def test_runs_tool_then_answers(self):
        scripted = ScriptedProvider([
            LLMResponse(tool_calls=[LLMToolCall(id="c1", name="shell", args={"command": "echo hi"})]),
            LLMResponse(text="the shell said hi"),
        ])
        agent = LLMAgent(provider=scripted, model="demo", executors=[ShellExecutor()])
        events, reply = drive(agent, "say hi via shell")

        assert reply == "the shell said hi"
        tool_names = [type(e).__name__ for e in events]
        assert "ToolCallStartedEvent" in tool_names
        assert "ToolCallCompletedEvent" in tool_names
        # result fed back to the model on the second call
        assert any(m["role"] == "tool" for m in scripted.calls[1]["messages"])
        # history records user + tool + assistant
        roles = [m.role.value for m in agent.history]
        assert "user" in roles and "tool" in roles and "assistant" in roles

    def test_unknown_tool_reports_error_and_continues(self):
        scripted = ScriptedProvider([
            LLMResponse(tool_calls=[LLMToolCall(id="c1", name="ghost", args={})]),
            LLMResponse(text="recovered"),
        ])
        agent = LLMAgent(provider=scripted, model="demo", executors=[ShellExecutor()])
        events, reply = drive(agent, "use a missing tool")
        completed = [e for e in events if type(e).__name__ == "ToolCallCompletedEvent"]
        assert completed[0].error and "Unknown tool" in completed[0].error
        assert reply == "recovered"

    def test_max_steps_guard(self):
        # model always asks for a tool → loop must stop at max_steps
        scripted = ScriptedProvider([
            LLMResponse(tool_calls=[LLMToolCall(id=f"c{i}", name="shell", args={"command": "echo x"})])
            for i in range(10)
        ])
        agent = LLMAgent(provider=scripted, model="demo", executors=[ShellExecutor()], max_steps=3)
        _, reply = drive(agent, "loop forever")
        assert "max_steps" in reply

    def test_tool_defs_use_args_schema(self):
        agent = LLMAgent(provider=ScriptedProvider([]), model="demo", executors=[ReadExecutor()])
        defs = agent._tool_defs()
        assert defs[0]["name"] == "read"
        assert "path" in defs[0]["parameters"]["properties"]


class TestApproval:
    def _scripted(self):
        return ScriptedProvider([
            LLMResponse(tool_calls=[LLMToolCall(id="c1", name="flagged", args={})]),
            LLMResponse(text="finished"),
        ])

    def test_denied_by_default(self):
        agent = LLMAgent(provider=self._scripted(), model="demo", executors=[FlaggedExecutor()])
        events, _ = drive(agent, "do the risky thing")
        completed = [e for e in events if type(e).__name__ == "ToolCallCompletedEvent"]
        assert completed[0].error and "approval" in completed[0].error.lower()

    def test_auto_approve_runs_it(self):
        agent = LLMAgent(provider=self._scripted(), model="demo", executors=[FlaggedExecutor()], auto_approve=True)
        events, _ = drive(agent, "do the risky thing")
        completed = [e for e in events if type(e).__name__ == "ToolCallCompletedEvent"]
        assert completed[0].error is None
        assert completed[0].result == {"success": True, "ran": True}

    def test_approver_callback(self):
        agent = LLMAgent(
            provider=self._scripted(), model="demo", executors=[FlaggedExecutor()],
            approver=lambda name, args: False,
        )
        events, _ = drive(agent, "do the risky thing")
        completed = [e for e in events if type(e).__name__ == "ToolCallCompletedEvent"]
        assert completed[0].error and "approval" in completed[0].error.lower()


# ── tool schemas ──────────────────────────────────────────────────────


class TestToolSchemas:
    @pytest.mark.parametrize(
        "executor, required",
        [
            (ReadExecutor(), "path"),
            (ShellExecutor(), "command"),
            (EditExecutor(), "path"),
            (WebFetchExecutor(), "url"),
            (GrepExecutor(), "pattern"),
            (WebSearchExecutor(), "query"),
        ],
    )
    def test_every_tool_exposes_schema(self, executor, required):
        schema = executor.args_schema()
        assert schema["type"] == "object"
        assert required in schema["properties"]
        assert required in schema["required"]
