"""Reduce and re-bake a library of painted props, CPU only, resumable.

A commission delivers its props painted at full density; the runtime wants a
fraction of the triangles and the same look. For each item this runs:

  1. ``reduce-mesh --triangle-budget auto --runtime-derivative`` -- the budget
     table decides from the name, notes and real size, and climbs while the
     surface gates refuse;
  2. ``rebake-maps`` on the reduction's native .blend -- the paint baked back
     from the dense original, judged against the appearance reference, climbing
     the same ladder while the views refuse.

A source the budget table says is already close enough is kept and nothing is
baked. Every item's result goes into a progress file as it finishes, so a run
that is stopped picks up where it was; a summary (JSON and a Markdown table)
is rewritten at the end. Nothing an item was made from is written to.

Items are a JSON list:

  [{"name": "floor-brazier", "dense": ".../floor-brazier.blend",
    "reference": ".../floor-brazier.glb", "notes": "...", "work": ".../05/floor-brazier"}]

``reference`` (what it must look like; default the dense file), ``notes``
(text that may promote the budget role), ``role`` and ``work`` (default
``<out>/<name>``) are optional.

Usage:
  python scripts/rebake_library.py --items items.json --out <dir> \
      [--workers 2] [--threads 8] [--blender <exe>] [--only a,b] [--limit N] [--progress <file>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.stages import run_stage  # noqa: E402

SCHEMA = "reference-asset-compiler.rebake-library.v1"
LOCK = threading.Lock()


class LibraryError(ValueError):
    """An item list that cannot be run as it stands."""


def load_items(path: Path, out: Path) -> list[dict[str, Any]]:
    items = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(items, list) or not items:
        raise LibraryError("The item list must be a non-empty JSON list.")
    seen = set()
    checked = []
    for index, item in enumerate(items):
        name = item.get("name")
        if not name or name in seen:
            raise LibraryError("Item {0} needs a unique name (got {1!r}).".format(index, name))
        seen.add(name)
        dense = Path(item.get("dense") or "")
        if not dense.is_file():
            raise LibraryError("{0}: the dense original does not exist: {1}".format(name, dense))
        reference = Path(item["reference"]) if item.get("reference") else None
        if reference is not None and not reference.is_file():
            raise LibraryError("{0}: the appearance reference does not exist: {1}".format(
                name, reference))
        checked.append({"name": name, "dense": dense, "reference": reference,
                        "notes": item.get("notes") or "", "role": item.get("role"),
                        "work": Path(item.get("work") or (out / name))})
    return checked


def read_progress(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def record(path: Path, name: str, entry: dict[str, Any]) -> None:
    with LOCK:
        progress = read_progress(path)
        progress[name] = entry
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")


def process(item: dict[str, Any], blender: str, threads: int, progress: Path,
            run: Callable[..., dict[str, Any]] = run_stage) -> dict[str, Any]:
    """One prop: reduce by the budget table, then re-bake and judge."""
    work = item["work"]
    work.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    entry: dict[str, Any] = {"name": item["name"], "dense": str(item["dense"]),
                             "reference": str(item["reference"] or item["dense"]),
                             "work": str(work)}
    reduction_report = work / "reduction-report.json"
    if not reduction_report.is_file():
        options = {"triangle_budget": "auto", "runtime_derivative": True,
                   "asset_name": item["name"], "asset_notes": item["notes"]}
        if item.get("role"):
            options["role"] = item["role"]
        payload = run("reduce-mesh", item["dense"], work / "reduced.glb", reduction_report,
                      repo_root=ROOT, blender=blender, timeout=7200, options=options)
        entry["reduction_attempt"] = payload.get("attempt_directory")
        if not payload.get("ok") or not reduction_report.is_file():
            entry.update(status="reduction_refused", error=payload.get("error"),
                         seconds=round(time.monotonic() - started, 1))
            record(progress, item["name"], entry)
            return entry
    reduction = json.loads(reduction_report.read_text(encoding="utf-8-sig"))
    decision = reduction.get("budget_decision") or {}
    entry["budget"] = {key: decision.get(key) for key in
                       ("role", "role_reason", "size_class", "triangle_budget", "ladder")}
    if decision.get("keep_source"):
        entry.update(status="kept_source", reason=decision.get("summary"),
                     seconds=round(time.monotonic() - started, 1))
        record(progress, item["name"], entry)
        return entry

    options = {"dense": item["dense"], "reduction_report": reduction_report, "threads": threads}
    if item["reference"] is not None:
        options["appearance_reference"] = item["reference"]
    # The reduction's native .blend rather than its GLB: the receipt binds both,
    # and the native mesh has not been split along every seam by an exporter.
    payload = run("rebake-maps", Path(reduction["output"]["path"]), work / "runtime.glb",
                  work / "rebake-report.json", repo_root=ROOT, blender=blender,
                  timeout=4 * 3600, options=options)
    entry["rebake_attempt"] = payload.get("attempt_directory")
    report = work / "rebake-report.json"
    if report.is_file():
        rebake = json.loads(report.read_text(encoding="utf-8"))
        entry["status"] = rebake["status"]
        entry["attempts"] = [{"rung": attempt.get("rung"), "triangles": attempt.get("triangles"),
                              "uv_layout": attempt.get("uv_layout"),
                              "painted_surface_reached_share":
                                  attempt.get("painted_surface_reached_share"),
                              "appearance": (attempt.get("appearance") or {}).get("summary"),
                              "passed": (attempt.get("appearance") or {}).get("passed"),
                              "failure": attempt.get("failure")}
                             for attempt in rebake["attempts"]]
        entry["accepted"] = rebake.get("accepted")
        entry["savings"] = rebake.get("savings")
        entry["failures"] = rebake.get("failures")
    else:
        entry.update(status="rebake_failed", error=payload.get("error"))
    entry["seconds"] = round(time.monotonic() - started, 1)
    record(progress, item["name"], entry)
    return entry


def summarise(progress: dict[str, Any]) -> dict[str, Any]:
    """Totals and one row per prop, for the person deciding what to keep."""
    rows, dense_total, runtime_total = [], 0, 0
    counts: dict[str, int] = {}
    for name, entry in sorted(progress.items()):
        status = entry.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
        savings = entry.get("savings") or {}
        accepted = entry.get("accepted") or {}
        last = (entry.get("attempts") or [{}])[-1]
        appearance = last.get("appearance") or {}
        row = {"name": name, "status": status,
               "dense_triangles": savings.get("dense_triangles"),
               "runtime_triangles": accepted.get("triangles"),
               "share_saved": savings.get("share_saved"),
               "rungs_tried": [attempt.get("rung") for attempt in entry.get("attempts") or []],
               "uv_layout": accepted.get("uv_layout"),
               "lit_ssim": (appearance.get("beauty") or {}).get("minimum_ssim"),
               "unlit_ssim": (appearance.get("albedo") or {}).get("minimum_ssim"),
               "sheet": accepted.get("comparison_sheet"),
               "runtime_glb": accepted.get("delivered_to")}
        if status == "accepted":
            dense_total += int(row["dense_triangles"] or 0)
            runtime_total += int(row["runtime_triangles"] or 0)
        rows.append(row)
    return {
        "schema": SCHEMA,
        "counts": counts,
        "accepted_dense_triangles": dense_total,
        "accepted_runtime_triangles": runtime_total,
        "accepted_share_saved": round(1 - runtime_total / dense_total, 4) if dense_total else 0.0,
        "rows": rows,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = ["| Prop | Result | Triangles | Saved | Lit / unlit SSIM | UVs |",
             "|---|---|---|---|---|---|"]
    for row in summary["rows"]:
        triangles = ("{0:,} -> {1:,}".format(row["dense_triangles"], row["runtime_triangles"])
                     if row["runtime_triangles"] else "")
        saved = "{0:.0%}".format(row["share_saved"]) if row["share_saved"] else ""
        scores = ("{0:.3f} / {1:.3f}".format(row["lit_ssim"], row["unlit_ssim"])
                  if row["lit_ssim"] is not None else "")
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
            row["name"], row["status"], triangles, saved, scores, row["uv_layout"] or ""))
    lines.append("")
    lines.append("Accepted: {0:,} -> {1:,} triangles ({2:.0%} saved). {3}".format(
        summary["accepted_dense_triangles"], summary["accepted_runtime_triangles"],
        summary["accepted_share_saved"],
        ", ".join("{0} {1}".format(count, status) for status, count in
                  sorted(summary["counts"].items()))))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--progress", type=Path, help="Default: <out>/progress.json")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--blender", default=os.environ.get("RAC_BLENDER"))
    parser.add_argument("--only", default="")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    if not args.blender or not Path(args.blender).is_file():
        print("[LIBRARY] FAILED: pass --blender or set RAC_BLENDER")
        return 1
    if not 1 <= args.workers <= 8 or not 1 <= args.threads <= 64:
        print("[LIBRARY] FAILED: workers run from 1 to 8 and threads from 1 to 64")
        return 1
    try:
        items = load_items(args.items, args.out)
    except LibraryError as problem:
        print("[LIBRARY] FAILED: {0}".format(problem))
        return 1
    progress = args.progress or (args.out / "progress.json")
    only = {name for name in args.only.split(",") if name}
    done = read_progress(progress)
    todo = [item for item in items if item["name"] not in done
            and (not only or item["name"] in only)]
    if args.limit:
        todo = todo[:args.limit]
    print("[LIBRARY] {0} items, {1} already done, {2} to run, {3} at a time on {4} threads each"
          .format(len(items), len(done), len(todo), args.workers, args.threads), flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for entry in pool.map(lambda item: process(item, args.blender, args.threads, progress),
                              todo):
            accepted = entry.get("accepted") or {}
            print("DONE {0}: {1} {2} -> {3} in {4}s".format(
                entry["name"], entry.get("status"),
                (entry.get("savings") or {}).get("dense_triangles"), accepted.get("triangles"),
                entry.get("seconds")), flush=True)
    summary = summarise(read_progress(progress))
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (args.out / "summary.md").write_text(markdown(summary), encoding="utf-8")
    print("RAC_REBAKE_LIBRARY_OK summary={0}".format(args.out / "summary.json"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
