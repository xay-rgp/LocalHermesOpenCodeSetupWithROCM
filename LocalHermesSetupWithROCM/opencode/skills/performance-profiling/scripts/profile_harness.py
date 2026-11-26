#!/usr/bin/env python3
"""Deterministic CPU (cProfile) + Memory (tracemalloc) profiling harness.

Runs a target callable (`module:function`) or script inside a target workspace,
collects exclusive (tottime) and inclusive (cumtime) CPU hotspots, peak memory
and top allocation sites, multi-iteration memory leak deltas, and optional
before/after speedup comparisons.
"""
from __future__ import annotations

import argparse
import cProfile
import gc
import importlib
import json
import pstats
import runpy
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any


def resolve_target(workdir: Path, target: str):
    if str(workdir) not in sys.path:
        sys.path.insert(0, str(workdir))
    if ":" in target:
        mod_name, attr_path = target.split(":", 1)
        mod = importlib.import_module(mod_name)
        obj: Any = mod
        for part in attr_path.split("."):
            obj = getattr(obj, part)
        return obj
    script_path = (workdir / target).resolve()
    if not script_path.exists():
        raise FileNotFoundError(f"Target script not found: {script_path}")
    return lambda: runpy.run_path(str(script_path), run_name="__main__")


def is_project_file(filename: str, workdir: Path) -> bool:
    try:
        p = Path(filename).resolve()
        return p.is_relative_to(workdir)
    except Exception:
        return False


def profile_once(fn, workdir: Path, top_n: int = 15, project_only: bool = False) -> dict[str, Any]:
    gc.collect()
    tracemalloc.start(10)
    snap_before = tracemalloc.take_snapshot()

    profiler = cProfile.Profile()
    t0 = time.perf_counter()
    profiler.enable()
    try:
        fn()
    finally:
        profiler.disable()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    snap_after = tracemalloc.take_snapshot()
    current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    stats = pstats.Stats(profiler)
    rows: list[dict[str, Any]] = []
    for (filename, lineno, funcname), (cc, nc, tt, ct, _callers) in stats.stats.items():
        if project_only and not is_project_file(filename, workdir):
            continue
        rel_file = filename
        try:
            p = Path(filename).resolve()
            if p.is_relative_to(workdir):
                rel_file = str(p.relative_to(workdir))
        except Exception:
            pass
        rows.append({
            "file": rel_file,
            "line": lineno,
            "function": funcname,
            "primitive_calls": cc,
            "total_calls": nc,
            "tottime_ms": round(tt * 1000.0, 3),
            "cumtime_ms": round(ct * 1000.0, 3),
        })

    top_tottime = sorted(rows, key=lambda r: r["tottime_ms"], reverse=True)[:top_n]
    top_cumtime = sorted(rows, key=lambda r: r["cumtime_ms"], reverse=True)[:top_n]

    top_diffs = snap_after.compare_to(snap_before, "lineno")
    alloc_rows: list[dict[str, Any]] = []
    for stat in top_diffs:
        frame = stat.traceback[0]
        if project_only and not is_project_file(frame.filename, workdir):
            continue
        rel_file = frame.filename
        try:
            p = Path(frame.filename).resolve()
            if p.is_relative_to(workdir):
                rel_file = str(p.relative_to(workdir))
        except Exception:
            pass
        alloc_rows.append({
            "file": rel_file,
            "line": frame.lineno,
            "size_delta_kib": round(stat.size_diff / 1024.0, 3),
            "count_delta": stat.count_diff,
        })
        if len(alloc_rows) >= top_n:
            break

    return {
        "elapsed_ms": round(elapsed_ms, 3),
        "total_calls": stats.total_calls,
        "primitive_calls": stats.prim_calls,
        "peak_memory_kib": round(peak_bytes / 1024.0, 3),
        " retained_memory_kib": round(current_bytes / 1024.0, 3),
        "top_tottime": top_tottime,
        "top_cumtime": top_cumtime,
        "top_memory_allocations": alloc_rows,
    }


def check_memory_leak(fn, iterations: int) -> dict[str, Any]:
    if iterations < 2:
        return {"enabled": False}
    gc.collect()
    tracemalloc.start(10)
    fn()  # warm up 1st call
    gc.collect()
    s1 = tracemalloc.take_snapshot()
    per_iter_retained_kib: list[float] = []
    for _ in range(iterations):
        fn()
        gc.collect()
        curr, _ = tracemalloc.get_traced_memory()
        per_iter_retained_kib.append(round(curr / 1024.0, 2))
    s2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    diffs = s2.compare_to(s1, "lineno")
    net_growth_bytes = sum(d.size_diff for d in diffs if d.size_diff > 0)
    avg_growth_per_iter_kib = round((per_iter_retained_kib[-1] - per_iter_retained_kib[0]) / max(1, iterations - 1), 3)
    return {
        "enabled": True,
        "iterations": iterations,
        "retained_kib_series": per_iter_retained_kib,
        "avg_growth_per_iter_kib": avg_growth_per_iter_kib,
        "net_positive_diff_kib": round(net_growth_bytes / 1024.0, 3),
        "leaking": avg_growth_per_iter_kib > 16.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", default=".", help="Workspace root directory")
    parser.add_argument("--target", required=True, help="module:callable or script.py")
    parser.add_argument("--top", type=int, default=12, help="Number of hotspot rows")
    parser.add_argument("--project-only", action="store_true", help="Filter frames to files inside workdir")
    parser.add_argument("--leak-iterations", type=int, default=4, help="Iterations to test monotonic memory growth")
    parser.add_argument("--compare", type=Path, help="Path to baseline JSON report for speedup comparison")
    parser.add_argument("--output", type=Path, help="Optional output file path for JSON report")
    args = parser.parse_args()

    workdir = Path(args.workdir).resolve()
    fn = resolve_target(workdir, args.target)

    profile_report = profile_once(fn, workdir, top_n=args.top, project_only=args.project_only)
    leak_report = check_memory_leak(fn, args.leak_iterations)

    result: dict[str, Any] = {
        "workdir": str(workdir),
        "target": args.target,
        "profile": profile_report,
        "memory_leak_check": leak_report,
    }

    if args.compare and args.compare.exists():
        base = json.loads(args.compare.read_text(encoding="utf-8"))
        base_ms = float(base.get("profile", {}).get("elapsed_ms", 0.0))
        curr_ms = float(profile_report["elapsed_ms"])
        base_peak = float(base.get("profile", {}).get("peak_memory_kib", 0.0))
        curr_peak = float(profile_report["peak_memory_kib"])
        result["comparison"] = {
            "baseline_elapsed_ms": base_ms,
            "current_elapsed_ms": curr_ms,
            "speedup_factor": round(base_ms / curr_ms, 2) if curr_ms > 0 else 0.0,
            "baseline_peak_memory_kib": base_peak,
            "current_peak_memory_kib": curr_peak,
            "memory_reduction_pct": round((1.0 - curr_peak / base_peak) * 100.0, 2) if base_peak > 0 else 0.0,
        }

    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
