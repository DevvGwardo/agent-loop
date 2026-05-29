import asyncio
import time
import tempfile
import os
import sys
sys.path.insert(0, os.path.expanduser("~/agent-loop"))

from agent_loop.tools import ShellExecutor, ReadExecutor, EditExecutor, GrepExecutor
from agent_loop.mcp import McpSnapshotCache, McpToolDefinition
from agent_loop.approval import ApprovalGates

shell = ShellExecutor()
reader = ReadExecutor()
editor = EditExecutor()
grep = GrepExecutor()
results = []

async def run():
    tmpdir = tempfile.mkdtemp()
    
    # 1. Spam shell: 100 commands
    t0 = time.time()
    for i in range(100):
        r = await shell.execute({'command': f'echo "line {i}" && echo "err {i}" >&2'})
    results.append(('shell 100x seq', time.time()-t0, f'x={r["exit_code"]}'))
    
    # 2. Parallel shell: 50
    t0 = time.time()
    rs = await asyncio.gather(*[shell.execute({'command': f'echo p{i}'}) for i in range(50)])
    results.append(('shell 50x parallel', time.time()-t0, f'allok={all(r["exit_code"]==0 for r in rs)}'))
    
    # 3. Big file read: 100K lines
    big = os.path.join(tmpdir, 'big.txt')
    with open(big, 'w') as f:
        for i in range(100000):
            f.write(f'line {i} with padding data xxxxxxxxxxxxxxxxxxxxxxxxxx\n')
    t0 = time.time()
    r = await reader.execute({'path': big})
    results.append(('read 100K-line file', time.time()-t0, f'lines={r.get("total_lines","?")}'))
    
    # 4. Partial reads
    t0 = time.time()
    for offset in [0, 500000, 2000000]:
        await reader.execute({'path': big, 'offset': offset, 'limit': 100000})
    results.append(('3x partial reads', time.time()-t0, 'offset range'))
    
    # 5. Edit stress: 100 str_replace
    editp = os.path.join(tmpdir, 'ed.txt')
    with open(editp, 'w') as f:
        for i in range(1000):
            f.write(f'target_{i}: placeholder\n')
    t0 = time.time()
    for i in range(100):
        await editor.execute({'path': editp, 'mode': 'str_replace', 'old_string': f'target_{i}: placeholder', 'new_string': f'target_{i}: REPLACED'})
    results.append(('edit 100x str_replace', time.time()-t0, ''))
    
    # 6. Grep regex 100 matches
    t0 = time.time()
    r = await grep.execute({'pattern': 'target_9[0-9]', 'path': tmpdir})
    results.append(('grep 100 regex matches', time.time()-t0, f'count={r.get("count","?")}'))
    
    # 7. Grep many files
    for j in range(50):
        fp = os.path.join(tmpdir, f'hs_{j}.txt')
        with open(fp, 'w') as f:
            for k in range(200):
                f.write(f'NEEDLE_{j}_FOUND\n' if k==99 else f'filler {k}\n')
    t0 = time.time()
    r = await grep.execute({'pattern': 'NEEDLE_', 'path': tmpdir, 'context': 2})
    results.append(('grep 50 files x 200L', time.time()-t0, f'count={r.get("count","?")}'))
    
    # 8. MCP cache: 20K tool defs (200 servers x 100 tools)
    cache = McpSnapshotCache()
    t0 = time.time()
    for sid in range(200):
        for tid in range(100):
            cache.register(McpToolDefinition(
                server_name=f'server-{sid}',
                tool_name=f'tool-{tid}',
                description='',
                input_schema={'type': 'object', 'properties': {}}
            ))
    results.append(('MCP 20K tool defs', time.time()-t0, f'gen={cache.generation}'))
    
    # 9. Approval stress: 500 iterations x 6 policies
    gates = ApprovalGates()
    t0 = time.time()
    for _ in range(500):
        gates.get_level('shell')
        gates.get_level('read')
        shell.needs_approval({'command': 'rm -rf /'})
        shell.needs_approval({'command': 'ls -la'})
        shell.needs_approval({'command': 'echo hi'})
        shell.needs_approval({'command': 'reboot'})
    results.append(('approval 500x6', time.time()-t0, ''))
    
    # 10. Large shell output 5K lines (via temp script to avoid quoting issues)
    script10 = os.path.join(tmpdir, 'bigout.py')
    with open(script10, 'w') as f:
        f.write("import sys\nfor i in range(5000): sys.stdout.write(f'line {i} ' + 'x'*50 + chr(10))\nprint('DONE', flush=True)")
    t0 = time.time()
    r = await shell.execute({'command': f'python3 {script10}'})
    results.append(('shell 5K lines stdout', time.time()-t0, f'len={len(r.get("stdout",""))}c exit={r["exit_code"]}'))
    
    # 11. Concurrent mixed tools
    t0 = time.time()
    rs = await asyncio.gather(
        shell.execute({'command': 'echo s1'}),
        reader.execute({'path': big, 'offset': 0, 'limit': 1000}),
        reader.execute({'path': editp, 'offset': 0, 'limit': 1000}),
        grep.execute({'pattern': 'NEEDLE_1', 'path': tmpdir}),
        shell.execute({'command': 'echo s2'}),
    )
    results.append(('5 concurrent mixed tools', time.time()-t0, f'ok={all(isinstance(r,dict) for r in rs)}'))
    
    # 12. Edit stream 10K lines (stays under 10MB safety cap)
    huge = os.path.join(tmpdir, 'huge.txt')
    t0 = time.time()
    lines = '\n'.join(f'line {i}: ' + 'x'*200 for i in range(10000))
    r = await editor.execute({'path': huge, 'mode': 'stream_content', 'content': lines})
    results.append(('edit stream 10K lines', time.time()-t0, f'ok={r.get("success")}'))
    
    # 13. Shell 100x with context injection
    t0 = time.time()
    for i in range(100):
        await shell.execute({'command': f'echo ctx{i}'}, context={'working_directory': tmpdir})
    results.append(('shell 100x with ctx', time.time()-t0, ''))
    
    # 14. Binary detection on 1MB random data
    binp = os.path.join(tmpdir, 'bin.bin')
    with open(binp, 'wb') as f:
        f.write(os.urandom(1000000))
    t0 = time.time()
    r = await reader.execute({'path': binp})
    results.append(('read 1MB binary file', time.time()-t0, f'err={"binary" in r.get("error","").lower()}'))
    
    # 15. Grep last line in 10K-line file
    t0 = time.time()
    r = await grep.execute({'pattern': 'line 9999', 'path': tmpdir, 'file_glob': 'huge.txt'})
    results.append(('grep last line 10K file', time.time()-t0, f'found={r.get("count",0)}'))
    
    # Print results
    total = sum(r[1]*1000 for r in results)
    print(f'{"="*75}')
    print(f'  AGENT-LOOP STRESS BENCHMARK — 15 heavy ops')
    print(f'{"="*75}')
    print(f'  {"Operation":35s} {"Time":>8s}  Detail')
    print(f'  {"-"*35} {"-"*8}  {"-"*40}')
    for op, t, d in sorted(results, key=lambda x: x[1]*1000, reverse=True):
        print(f'  {op:35s} {t*1000:8.1f}ms  {d[:40]}')
    print(f'{"-"*75}')
    print(f'  TOTAL:    {total:8.1f}ms  ({total/1000:.2f}s)')
    print(f'  AVG:      {total/len(results):8.1f}ms')
    print(f'  FASTEST:  {min(r[1]*1000 for r in results):.1f}ms')
    print(f'  SLOWEST:  {max(r[1]*1000 for r in results):.1f}ms')
    print(f'{"="*75}')

asyncio.run(run())
