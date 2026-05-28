# agent-loop

A reference implementation of a streaming AI coding agent protocol.

Inspired by the architecture used by modern coding agents — designed to be readable, extensible, and a solid foundation for building your own AI coding tools.

## Architecture

```
LLM → plans → ToolCall (with description, approval)
         ↓
    dispatches to executor (shell/read/edit/MCP/browser)
         ↓
    streams back: deltas in real-time
         ↓
    ToolCallCompleted → LLM gets full result → next turn
```

Every tool call follows a **streaming lifecycle**:
1. `ToolCallStartedEvent` — "about to run X"
2. `ToolCallDeltaEvent` — incremental progress (stdout, stderr, thinking)
3. `ToolCallCompletedEvent` — final result

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

## MCP Snapshot Cache

Caches MCP server tool definitions with **generation tracking** — only fetches from servers when their definitions change.

```python
from agent_loop.mcp import McpSnapshotCache

cache = McpSnapshotCache()
cache.register_server("sqlite")
cache.add_tool("sqlite", "query", {
    "description": "Run a SQL query",
    "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}}
})

tools = cache.get_tools("sqlite")  # Cached until generation bumps
changed = cache.get_changed_servers()  # Returns servers that changed
```

## Approval Gates

Three-tier safety system:

1. **AUTO** — low-risk operations (read file, fetch URL)
2. **PRE_CHECK** — ask before running (shell command, edit file)
3. **POST_CHECK** — confirm after seeing result

Plus smart mode: auto-downgrades PRE_CHECK to AUTO for trivially safe ops.

```python
from agent_loop.approval import ApprovalGates, ApprovalLevel

gates = ApprovalGates()
gates.set_policy("shell", ApprovalLevel.PRE_CHECK)
gates.set_policy("read", ApprovalLevel.AUTO)

# Smart mode: executor.needs_approval() can override
result = gates.check_pre("shell", {"command": "ls"}, executor)
```

## Project Structure

```
agent_loop/
├── __init__.py          # Package exports
├── agent.py             # Main Agent class with event-driven run loop
├── models.py            # All Pydantic protocol models
├── dispatcher.py        # Tool name → executor routing
├── exceptions.py        # Custom exceptions
├── tools/
│   ├── __init__.py      # Tool registry + BUILTIN_TOOLS
│   ├── base.py          # ToolExecutor ABC
│   ├── shell.py         # Shell command execution with streaming
│   ├── read.py          # File reading with range support
│   ├── edit.py          # File editing (str_replace, stream_content)
│   └── web_fetch.py     # URL fetching with markdown conversion
├── mcp/
│   ├── __init__.py
│   └── cache.py         # McpSnapshotCache with generation tracking
├── approval/
│   ├── __init__.py
│   └── gates.py         # Three-tier approval system
├── context/
│   ├── __init__.py
│   ├── builder.py       # Lazy-loading RequestContextBuilder
│   └── models.py        # RequestContext, InvocationContext, etc.
tests/
├── test_agent.py        # 13 tests for Agent class
└── test_tools.py        # 20 tests for tool executors
examples/
├── basic_agent.py       # Agent with shell + read
└── mcp_cache_demo.py    # MCP cache generation tracking demo
```

## Key Patterns

### Streaming Protocol
Every tool call emits 3 events: started → delta(s) → completed. The UI can show "thinking..." then live output then the final result. No polling, no "wait for response."

### MCP Snapshot Caching
Instead of calling MCP servers on every request, snapshot their tool definitions with a generation number. Only re-fetch when the generation changes.

### Approval Gate Pattern
Three-tier with smart auto-downgrade. Declare per-tool policies. Executors can self-classify their risk level.

### Context Lazy Loading
The RequestContext has `_complete` flags for every section. Build incrementally — only load what the model needs for this turn.

## License

MIT
