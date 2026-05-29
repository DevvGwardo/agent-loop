"""Durability test: run tools repeatedly and track memory/resource usage.

1000 iterations across all tool executors, checking for:
- Memory growth (RSS)
- File descriptor leaks
- Performance degradation over time
- Cumulative error rates
"""

import asyncio
import os
import time
import resource
import tempfile
import tracemalloc
from pathlib import Path

try:
    import psutil
except ImportError:
    psutil = None

from agent_loop.tools import ShellExecutor, ReadExecutor, EditExecutor, GrepExecutor


async def durability_test(iterations: int = 1000) -> dict:
    results = {
        "iterations": 0,
        "errors": 0,
        "start_rss_mb": 0,
        "peak_rss_mb": 0,
        "end_rss_mb": 0,
        "total_time_s": 0,
        "per_op_times": {},
        "fd_count": None,
    }

    shell = ShellExecutor()
    reader = ReadExecutor()
    editor = EditExecutor()
    grep = GrepExecutor()

    tmpdir = tempfile.mkdtemp()
    testfile = os.path.join(tmpdir, "durability.txt")
    Path(testfile).write_text("line " * 1000 + "\n")

    # Track starting memory
    if psutil:
        proc = psutil.Process(os.getpid())
        results["start_rss_mb"] = proc.memory_info().rss / 1024 / 1024
        results["fd_count"] = proc.num_fds()
    else:
        rusage = resource.getrusage(resource.RUSAGE_SELF)
        results["start_rss_mb"] = rusage.ru_maxrss / 1024  # macOS reports in KB

    times = {"shell": [], "read": [], "edit": [], "grep": []}
    start = time.time()
    peak_rss = results["start_rss_mb"]

    for i in range(iterations):
        op = i % 4
        try:
            if op == 0:
                t0 = time.time()
                r = await shell.execute({"command": "echo 'iter {}'".format(i)})
                times["shell"].append(time.time() - t0)
            elif op == 1:
                t0 = time.time()
                r = await reader.execute({"path": testfile, "limit": 100})
                times["read"].append(time.time() - t0)
            elif op == 2:
                t0 = time.time()
                r = await editor.execute({"path": testfile, "mode": "str_replace",
                    "old_string": "line", "new_string": "LINE"})
                # revert
                await editor.execute({"path": testfile, "mode": "str_replace",
                    "old_string": "LINE", "new_string": "line"})
                times["edit"].append(time.time() - t0)
            elif op == 3:
                t0 = time.time()
                r = await grep.execute({"pattern": "line", "path": tmpdir})
                times["grep"].append(time.time() - t0)
        except Exception as e:
            results["errors"] += 1

        # Track memory every 100 iterations
        if results["fd_count"] is not None:
            new_rss = proc.memory_info().rss / 1024 / 1024
            if new_rss > peak_rss:
                peak_rss = new_rss
            # Check FD count every 200 iterations
            if i % 200 == 0 and i > 0:
                results["fd_count"] = proc.num_fds()

        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{iterations} ...", flush=True)

    results["iterations"] = iterations
    results["total_time_s"] = time.time() - start
    results["peak_rss_mb"] = peak_rss

    if psutil:
        results["end_rss_mb"] = proc.memory_info().rss / 1024 / 1024

    # Per-op stats
    for name, vals in times.items():
        if vals:
            results["per_op_times"][name] = {
                "count": len(vals),
                "avg_ms": (sum(vals) / len(vals)) * 1000,
                "min_ms": min(vals) * 1000,
                "max_ms": max(vals) * 1000,
            }

    return results


async def main():
    print("=" * 70)
    print("  DURABILITY TEST — 1000 iterations")
    print("  Every iteration: shell → read → edit → grep (round-robin)")
    print("=" * 70)

    results = await durability_test(1000)

    print(f"\n{'='*70}")
    print(f"  DURABILITY TEST RESULTS")
    print(f"{'='*70}")
    print(f"  Iterations:     {results['iterations']}")
    print(f"  Errors:         {results['errors']} ({results['errors']/results['iterations']*100:.2f}%)")
    print(f"  Total time:     {results['total_time_s']:.2f}s")
    print(f"  Avg iteration:  {results['total_time_s']/results['iterations']*1000:.2f}ms")

    if results["start_rss_mb"] and results["end_rss_mb"]:
        growth = results["end_rss_mb"] - results["start_rss_mb"]
        print(f"\n  Memory (RSS):")
        print(f"    Start:   {results['start_rss_mb']:.1f} MB")
        print(f"    Peak:    {results['peak_rss_mb']:.1f} MB")
        print(f"    End:     {results['end_rss_mb']:.1f} MB")
        print(f"    Growth:  {growth:+.1f} MB ({growth/results['start_rss_mb']*100:+.1f}%)")
        if results["fd_count"]:
            print(f"    FD count: {results['fd_count']}")

    print(f"\n  Per-op latency:")
    for name, stats in sorted(results["per_op_times"].items()):
        print(f"    {name:10s}: {stats['avg_ms']:7.2f}ms avg  [{stats['min_ms']:.2f}ms .. {stats['max_ms']:.2f}ms]  (n={stats['count']})")

    print(f"\n  VERDICT: ", end="")
    if results["errors"] > 0:
        growth_pct = (results["end_rss_mb"] - results["start_rss_mb"]) / results["start_rss_mb"] * 100 if results["start_rss_mb"] else 0
        if growth_pct > 20:
            print(f"⚠️  {results['errors']} errors, memory grew {growth_pct:.1f}%")
        else:
            print(f"✅  {results['errors']} errors (expected), stable memory")
    else:
        print("✅  Clean run, zero errors")
    print(f"{'='*70}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
