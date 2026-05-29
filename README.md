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

## License

MIT — use freely, build on it, ship it.
