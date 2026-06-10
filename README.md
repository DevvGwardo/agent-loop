# agent-loop

A reference implementation of a streaming AI coding agent protocol.

Inspired by the architecture used by modern coding agents, `agent-loop` is designed to be readable, extensible, and a solid foundation for building your own AI coding tools.

## Architecture

<p align="center">
  <img src="docs/assets/agent-loop-architecture.svg" alt="agent-loop architecture diagram" width="100%" />
</p>

<p align="center">
  <img src="docs/assets/agent-loop-streaming.svg" alt="agent-loop streaming lifecycle diagram" width="100%" />
</p>

Every tool call follows a streaming lifecycle:
1. `ToolCallStartedEvent` - about to run X
2. `ToolCallDeltaEvent` - incremental progress (stdout, stderr, thinking)
3. `ToolCallCompletedEvent` - final result

## Quick Start

```python
from agent_loop import Agent
from agent_loop.tools import ShellExecutor, ReadExecutor

agent = Agent()
agent.register_tool(ShellExecutor())
agent.register_tool(ReadExecutor())

for event in agent.run("list the current directory"):
    print(f"[{event.event_type}] {event.tool_name}")
    if event.data:
        print(f"  {event.data}")
```

## Tool Executors

| Tool | Name | Args | Streaming |
|------|------|------|-----------|
| **Shell** | `shell` | command, working_directory, timeout, env | ✅ stdout/stderr deltas |
| **Read** | `read` | path, offset, limit | No |
| **Edit** | `edit` | path, mode (str_replace/replace/stream_content) | No |
| **Web Fetch** | `web_fetch` | url, timeout, max_size | No |
| **Grep** | `grep` | pattern, path, file_glob, context | No |
| **Web Search** | `web_search` | query | No |

## Connecting an LLM

The base `Agent` is model-agnostic — you hand it a `tool_sequence` to replay.
To let a real model decide which tools to call, use `LLMAgent`, which drives a
call-and-respond loop against a provider of your choice. Pick a provider by
name and a model id:

```python
from agent_loop.llm import LLMAgent
from agent_loop.tools import ShellExecutor, ReadExecutor

agent = LLMAgent(
    provider="openrouter",                      # see list_providers()
    model="anthropic/claude-sonnet-4-6",
    executors=[ShellExecutor(), ReadExecutor()],
)

for event in agent.run("List the Python files and read the smallest one"):
    print(f"[{type(event).__name__}] {getattr(event, 'tool_name', '')}")
```

Providers are read from environment variables for their API keys. No extra
SDKs are needed — everything runs over `httpx` (already a dependency).

| Provider | Wire format | API key env var |
|----------|-------------|-----------------|
| `openai` | OpenAI chat | `OPENAI_API_KEY` |
| `openrouter` | OpenAI chat | `OPENROUTER_API_KEY` |
| `groq` | OpenAI chat | `GROQ_API_KEY` |
| `deepseek` | OpenAI chat | `DEEPSEEK_API_KEY` |
| `xai` | OpenAI chat | `XAI_API_KEY` |
| `mistral` | OpenAI chat | `MISTRAL_API_KEY` |
| `together` | OpenAI chat | `TOGETHER_API_KEY` |
| `fireworks` | OpenAI chat | `FIREWORKS_API_KEY` |
| `ollama` | OpenAI chat | _(local, none)_ |
| `anthropic` | Anthropic messages | `ANTHROPIC_API_KEY` |

Dangerous tool calls (flagged by `executor.needs_approval`) are denied unless
you pass `auto_approve=True` or an `approver=callable`. For tests and offline
demos, `ScriptedProvider` returns canned responses with no network:

```python
from agent_loop.llm import LLMAgent, ScriptedProvider, LLMResponse, LLMToolCall

provider = ScriptedProvider([
    LLMResponse(tool_calls=[LLMToolCall(id="1", name="shell", args={"command": "echo hi"})]),
    LLMResponse(text="the shell printed hi"),
])
agent = LLMAgent(provider=provider, model="demo", executors=[ShellExecutor()])
```

Run the full example (offline by default; set `LLM_PROVIDER`/`LLM_MODEL` for a real model):

```bash
python examples/llm_agent.py
```

## MCP Snapshot Cache

Caches MCP server tool definitions with **generation tracking** — only fetches from servers when their definitions change.

```python
from agent_loop.mcp import McpSnapshotCache

cache = McpSnapshotCache()
cache.register_server("sqlite")
cache.add_tool("sqlite", "query", {
    "name": "query",
    "description": "Run a SQL query",
    "inputSchema": {"type": "object", "properties": {}}
})
snapshot = cache.get_snapshot()
assert snapshot.checksum == cache.get_checksum("sqlite")
```

## Approval Gates

Three-tier security model (AUTO / PRE_CHECK / POST_CHECK) that gates tool calls based on risk classification:

```python
from agent_loop.approval import ApprovalGate

gate = ApprovalGate()
result = gate.evaluate("shell", {"command": "rm -rf /"})
assert result.status == "requires_approval"
```

## Context Builder

Lazy-loading context that defers expensive fetches until they're needed:

```python
from agent_loop.context import RequestContext

ctx = RequestContext()
ctx.set_git_diff("+new code")
ctx.set_environ({"PWD": "/workspace"})
payload = ctx.build()
```

## Agent Skills (from Cursor protocol)

Skills provide reusable, shareable agent instructions loaded at runtime:

```python
from agent_loop.skills import SkillRegistry

registry = SkillRegistry()
registry.load_skill("deploy", "Run `npm run build && npm run deploy`")
active = registry.for_tool("shell")
```

## Coding Agent Harness

`CodingAgentHarness` is the integration layer for building your own agent
surface. It exposes the local coding tools to an OpenAI-compatible tool-calling
model, keeps conversation/tool history, and yields the same streaming tool
events as `Agent.run()`.

```python
from agent_loop import CodingAgentHarness, OpenAICompatibleChatClient

model = OpenAICompatibleChatClient(model="your-tool-calling-model")
harness = CodingAgentHarness(
    model_client=model,
    working_directory="/path/to/repo",
)

runner = harness.run("inspect the repo and run the tests")
while True:
    try:
        event = next(runner)
        print(event)
    except StopIteration as done:
        print("reply:", done.value)
        break
```

For controller processes, `scripts/run-as-child.py` accepts JSON on stdin and
streams NDJSON on stdout:

```bash
echo '{
  "task": "read README.md and summarize it",
  "model": "your-tool-calling-model",
  "working_directory": "'$PWD'"
}' | python3 scripts/run-as-child.py
```

Without a model, the same bridge can run deterministic tool sequences:

```bash
echo '{
  "task": "check current directory",
  "working_directory": "'$PWD'",
  "tool_sequence": [
    {"tool": "shell", "args": {"command": "pwd"}}
  ]
}' | python3 scripts/run-as-child.py
```

## Master Loop Harness

`MasterLoopHarness` adds the long-running orchestration layer:

```text
master loop
  mission loop
    goal loop
      agent loop
        workflow loop
          tool loop
```

This is useful when a single prompt is too small for the job. A mission can run
for one cycle, several cycles, or perpetually with a `should_continue`
callback. Every layer emits `LoopLifecycleEvent` snapshots, and tool calls still
stream through the existing `ToolCallStartedEvent` / `ToolCallDeltaEvent` /
`ToolCallCompletedEvent` protocol.

```python
from agent_loop import (
    AgentLoopSpec,
    CodingAgentHarness,
    GoalLoopSpec,
    MasterLoopHarness,
    MissionLoopSpec,
    WorkflowLoopSpec,
)
from agent_loop.tools import ShellExecutor

coding = CodingAgentHarness(executors=[ShellExecutor()])
master = MasterLoopHarness(coding)

mission = MissionLoopSpec(
    objective="Keep the repo healthy",
    max_cycles=2,
    goals=[
        GoalLoopSpec(
            name="verify",
            objective="Run a lightweight health check",
            agents=[
                AgentLoopSpec(
                    name="maintainer",
                    workflows=[
                        WorkflowLoopSpec(
                            name="tests",
                            tool_sequence=[
                                {"tool": "shell", "args": {"command": "pytest -q"}}
                            ],
                        )
                    ],
                )
            ],
        )
    ],
)

for event in master.run(mission):
    print(event)
```

Headless controllers can run the same hierarchy by passing `mode: "mission"` to
the child bridge:

```bash
echo '{
  "mode": "mission",
  "task": "check current directory",
  "tool_sequence": [
    {"tool": "shell", "args": {"command": "pwd"}}
  ]
}' | python3 scripts/run-as-child.py
```

The Ink TUI exposes the hierarchy as a mission-control panel. Prefix a prompt
with `/mission` to route it through the master loop. Set
`AGENT_LOOP_MISSION_CYCLES` for finite repeated missions, or
`AGENT_LOOP_PERPETUAL=1` for a perpetual local loop.

The Telegram adapter in `examples/telegram_agent.py` exposes a Codex-style
controller around the same harness. It persists sessions, supports slash
commands, and keeps explicit user shell commands separate from model-driven
tool calls.

```bash
export TELEGRAM_BOT_TOKEN=...
export OPENAI_API_KEY=...
export AGENT_LOOP_MODEL=your-tool-calling-model
export AGENT_LOOP_WORKDIR=/path/to/repo
python3 examples/telegram_agent.py
```

Useful Telegram commands:

| Command | Purpose |
| --- | --- |
| `/status` | Show thread id, model, cwd, permission mode, tools, and plan |
| `/permissions read-only\|workspace\|full-access` | Switch Codex-style permission mode |
| `/model <name>` | Switch the active tool-calling model |
| `/cd <path>` | Change the active workspace |
| `/shell <command>` | Run an explicit user shell command |
| `/diff` / `/gitstatus` | Inspect local git changes |
| `/review [focus]` | Ask the agent to review local changes without editing |
| `/plan [prompt]` | Ask the agent to plan before implementation |
| `/sessions`, `/resume <thread-id\|last>`, `/new`, `/clear` | Manage persistent conversations |
| `/init` | Create a starter `AGENTS.md` |
| `/tools`, `/mcp`, `/help` | Inspect available capabilities |
| `/confirm <code>` | Pair this Telegram chat (printed on bot startup) |

The controller code lives in `agent_loop.telegram.TelegramCodexAgent`, so tests
and other chat surfaces can reuse the command router without calling Telegram.

On first run the bot prints a pairing code. Only the paired chat (or
`AGENT_LOOP_TELEGRAM_CHAT_ID`) can drive the agent.

### MCP tools

Copy `examples/mcp.example.json` to `~/.agent-loop/mcp.json` and register
handlers with `CallableMcpClient`, or point `AGENT_LOOP_MCP_URL` at an HTTP
bridge that accepts `POST /call` with `{server, tool, arguments}`.

MCP tools are exposed to the model as `mcp__<server>__<tool>` executors and
show up in `/mcp`.

The harness also injects `AGENTS.md` and a short git status into the system
prompt automatically when present in the workspace.

## License

MIT — use freely, build on it, ship it.
