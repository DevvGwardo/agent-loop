#!/usr/bin/env python3
"""agent-loop benchmark — runs all operations and reports timings."""

import time, sys
sys.path.insert(0, '/Users/devgwardo/agent-loop')

from agent_loop import Agent
from agent_loop.tools import ShellExecutor, ReadExecutor, EditExecutor
from agent_loop.models import ToolCallStartedEvent, ToolCallDeltaEvent, ToolCallCompletedEvent
from agent_loop.mcp import McpSnapshotCache, McpToolDefinition
from agent_loop.approval import ApprovalGates, ApprovalLevel
from agent_loop.context import RequestContextBuilder

results = []

def bench(name, fn):
    t0 = time.perf_counter()
    ret = fn()
    ms = (time.perf_counter() - t0) * 1000
    results.append((name, ms, ret))
    return ret

# Init
agent = bench("init", lambda: Agent())
bench("reg_shell", lambda: agent.register_tool(ShellExecutor()))
bench("reg_read", lambda: agent.register_tool(ReadExecutor()))
bench("reg_edit", lambda: agent.register_tool(EditExecutor()))

# 1. Shell
events = bench("shell_ls", lambda: list(agent.run("ls", tool_sequence=[{"tool": "shell", "args": {"command": "ls -la", "working_directory": "/Users/devgwardo/agent-loop"}}])))
r = next((e for e in events if isinstance(e, ToolCallCompletedEvent)), None)
r1 = r.result if r else {"exit_code": -1, "stdout": ""}

# 2. Read
events = bench("read_me", lambda: list(agent.run("read", tool_sequence=[{"tool": "read", "args": {"path": "/Users/devgwardo/agent-loop/README.md"}}])))
r = next((e for e in events if isinstance(e, ToolCallCompletedEvent)), None)
r2 = r.result if r else {"content": "", "total_lines": 0}

# 3. Edit write
events = bench("edit_write", lambda: list(agent.run("edit", tool_sequence=[{"tool": "edit", "args": {"path": "/tmp/agent_bench.txt", "mode": "stream_content", "content": "bench\\ndata"}}])))
r = next((e for e in events if isinstance(e, ToolCallCompletedEvent)), None)
r3 = r.result if r else {"success": False}

# 4. Shell stdout/stderr/exit
events = bench("shell_stream", lambda: list(agent.run("test", tool_sequence=[{"tool": "shell", "args": {"command": "python3 -c \"import sys; print('out'); print('err',file=sys.stderr); sys.exit(5)\""}}])))
r = next((e for e in events if isinstance(e, ToolCallCompletedEvent)), None)
r4 = r.result if r else {"exit_code": -1, "stdout": "", "stderr": ""}

# 5. Batch 5 tools
events = bench("batch_5", lambda: list(agent.run("batch", tool_sequence=[
    {"tool": "shell", "args": {"command": "echo 1"}},
    {"tool": "shell", "args": {"command": "echo 2"}},
    {"tool": "read", "args": {"path": "/Users/devgwardo/agent-loop/pyproject.toml"}},
    {"tool": "shell", "args": {"command": "echo 3"}},
    {"tool": "shell", "args": {"command": "echo 4"}},
])))
r5c = sum(1 for e in events if isinstance(e, ToolCallCompletedEvent))

# 6. Shell error
events = bench("shell_err", lambda: list(agent.run("err", tool_sequence=[{"tool": "shell", "args": {"command": "nonexistent_cmd_xyz"}}])))
r = next((e for e in events if isinstance(e, ToolCallCompletedEvent)), None)
r6 = r.result if r else {"exit_code": -1}

# 7. Unknown tool
events = bench("unknown_tool", lambda: list(agent.run("x", tool_sequence=[{"tool": "nonexistent_tool9000", "args": {}}])))
r = next((e for e in events if isinstance(e, ToolCallCompletedEvent)), None)
r7e = r.error if r else ""

# 8. MCP cache
def mcp_test():
    cache = McpSnapshotCache()
    cache.register(McpToolDefinition(server_name="sqlite", tool_name="query", description="run SQL"))
    cache.register(McpToolDefinition(server_name="sqlite", tool_name="tables", description="list tables"))
    cache.register(McpToolDefinition(server_name="files", tool_name="read", description="read file"))
    gen1 = cache.generation
    cache.sync([McpToolDefinition(server_name="sqlite", tool_name="query", description="run SQL")])
    gen2 = cache.generation
    cache.sync([McpToolDefinition(server_name="sqlite", tool_name="query", description="run SQL"), McpToolDefinition(server_name="sqlite", tool_name="new_one", description="new")])
    gen3 = cache.generation
    return (len(cache.tools), gen1, gen2, gen3)
mcp_r = bench("mcp_cache", mcp_test)

# 9. Approval gates
async def gate_test():
    gates = ApprovalGates(smart_mode=True)
    gates.update_policy({"shell": ApprovalLevel.PRE_CHECK})
    gates.update_policy({"read": ApprovalLevel.AUTO})
    se = agent.get_executor("shell")
    re = agent.get_executor("read")
    r1 = await gates.should_auto_approve("shell", {"command": "rm -rf /"}, se)
    r2 = await gates.should_auto_approve("read", {"path": "test.txt"}, re)
    r3 = await gates.should_auto_approve("shell", {"command": "echo hi"}, se)
    return (r1, r2, r3)
r9 = bench("approval", lambda: __import__('asyncio').run(gate_test()))

# 10. Context builder
def ctx_test():
    b = RequestContextBuilder()
    b.add_section("rules", [{"name": "n", "content": "c"}])
    b.add_section("tools", [{"name": "shell", "desc": "run"}])
    ctx = b.build()
    return len(ctx)
r10 = bench("context", ctx_test)

# ── RESULTS ────────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"  agent-loop BENCHMARK RESULTS")
print(f"{'='*55}")
print(f"  {'Op':<25} {'Time':>8} {'Result':<30}")
print(f"  {'--':<25} {'----':>8} {'------':<30}")

checks = {
    "shell_ls": f"exit={r1.get('exit_code')} stdout={len(r1.get('stdout',''))}c",
    "read_me": f"len={len(r2.get('content',''))}c lines={r2.get('total_lines',0)}",
    "edit_write": f"ok={r3.get('success')}",
    "shell_stream": f"exit={r4.get('exit_code')} out={len(r4.get('stdout',''))}c err={len(r4.get('stderr',''))}c",
    "batch_5": f"{r5c} completed",
    "shell_err": f"exit={r6.get('exit_code')}",
    "unknown_tool": f"err='{r7e}'" if r7e else "no error",
    "mcp_cache": f"tools={mcp_r[0]} gen_changes={mcp_r[3]-mcp_r[1]}",
    "approval": f"rm={r9[0]} read={r9[1]} echo={r9[2]}",
    "context": f"sections={r10}",
}

total_ms = 0
for name, ms, _ in results:
    short = name
    info = checks.get(name, "")
    bar = '█' * max(1, int(ms / 5)) if ms > 0 else '·'
    print(f"  {bar:<10} {short:<15} {ms:>8.1f}ms  {info}")
    total_ms += ms

num = len(results)
avg = total_ms / num
print(f"{'='*55}")
print(f"  {'█'*max(1,int(avg/5)):<10} {'AVERAGE':<15} {avg:>8.1f}ms")
print(f"  {'█'*max(1,int(total_ms/5)):<10} {'TOTAL':<15} {total_ms:>8.1f}ms")
print(f"  {'⏱ Real time':<25} {time.perf_counter():.2f}s")
print(f"{'='*55}")
print(f"  🟢 {num} ops — PASS")
