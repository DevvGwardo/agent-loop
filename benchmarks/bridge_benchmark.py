"""Benchmark for the run-as-child.py bridge script."""
import asyncio
import json
import time
import sys

sys.path.insert(0, '.')

async def bench():
    # 1. Direct executor benchmark (baseline)
    from agent_loop.tools import ShellExecutor
    shell = ShellExecutor()
    t0 = time.time()
    for i in range(100):
        r = await shell.execute({'command': 'echo "{}"'.format(i)})
    direct_ms = (time.time() - t0) * 1000
    print(f'Direct 100x shell: {direct_ms:.1f}ms total, {direct_ms/100:.2f}ms avg')

    # 2. Bridge script benchmark
    t0 = time.time()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'scripts/run-as-child.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    payload = json.dumps({
        'task': 'echo bridge-benchmark && echo second-line',
        'tools': ['shell']
    }).encode()
    stdout, stderr = await proc.communicate(payload)
    bridge_ms = (time.time() - t0) * 1000
    events = [json.loads(l) for l in stdout.decode().strip().split('\n') if l]
    print(f'Bridge 1 run:  {bridge_ms:.1f}ms total, {len(events)} events')
    for e in events:
        d = e.get('result', {})
        if e['type'] == 'tool_completed':
            print(f'  [{e["type"]}] exit={d.get("exit_code")} out={d.get("stdout","")[:40]}')
        else:
            print(f'  [{e["type"]}]')

    # 3. Bridge with working_directory
    import tempfile, os
    tmpdir = tempfile.mkdtemp()
    t0 = time.time()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'scripts/run-as-child.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    payload = json.dumps({
        'task': 'pwd && ls -la',
        'tools': ['shell'],
        'working_directory': tmpdir
    }).encode()
    stdout, stderr = await proc.communicate(payload)
    wd_ms = (time.time() - t0) * 1000
    events = [json.loads(l) for l in stdout.decode().strip().split('\n') if l]
    print(f'Bridge w/ wd:   {wd_ms:.1f}ms total')
    for e in events:
        if e['type'] == 'tool_completed':
            out = e['result'].get('stdout', '')
            print(f'  pwd first line: {out.split(chr(10))[0]}')
            assert tmpdir in out.split(chr(10))[0], f"Working dir mismatch: expected {tmpdir}"
            print(f'  ✅ working_directory respected')

    # 4. Multiple tools
    t0 = time.time()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'scripts/run-as-child.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    payload = json.dumps({
        'task': 'echo hello',
        'tools': ['shell', 'read', 'edit', 'grep']
    }).encode()
    stdout, stderr = await proc.communicate(payload)
    multi_ms = (time.time() - t0) * 1000
    print(f'Bridge multi-tool: {multi_ms:.1f}ms')

    # 5. Error path: unknown tool
    t0 = time.time()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, 'scripts/run-as-child.py',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    payload = json.dumps({
        'task': 'something',
        'tools': ['nonexistent_tool']
    }).encode()
    stdout, stderr = await proc.communicate(payload)
    err_ms = (time.time() - t0) * 1000
    output = stdout.decode()
    print(f'Bridge error path: {err_ms:.1f}ms')
    if 'No valid' in output or 'Unknown' in output:
        print(f'  ✅ Unknown tool handled gracefully')
    else:
        print(f'  Output: {output[:200]}')

    # 6. Stress: spawn bridge 10 times sequentially
    t0 = time.time()
    for i in range(10):
        proc = await asyncio.create_subprocess_exec(
            sys.executable, 'scripts/run-as-child.py',
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        payload = json.dumps({
            'task': 'echo spawn{}'.format(i),
            'tools': ['shell']
        }).encode()
        await proc.communicate(payload)
    sequential_ms = (time.time() - t0) * 1000
    print(f'Bridge 10x sequential: {sequential_ms:.1f}ms total, {sequential_ms/10:.1f}ms avg')

    # Summary
    print(f'\n{"="*60}')
    print(f'  BRIDGE BENCHMARK SUMMARY')
    print(f'{"="*60}')
    print(f'  Direct 100x shell:        {direct_ms:8.1f}ms')
    print(f'  Bridge single run:        {bridge_ms:8.1f}ms')
    print(f'  Bridge w/ working_dir:    {wd_ms:8.1f}ms')
    print(f'  Bridge multi-tool:        {multi_ms:8.1f}ms')
    print(f'  Bridge error path:        {err_ms:8.1f}ms')
    print(f'  Bridge 10x sequential:    {sequential_ms:8.1f}ms')
    print(f'  Bridge overhead:          {bridge_ms - direct_ms/100:6.1f}ms')
    print(f'{"="*60}')

asyncio.run(bench())
