"""How long a model took, front to back, from the receipts `rac run-stage` leaves.

Every `rac run-stage` prints a stage-run receipt (schema
`reference-asset-compiler.stage-run.v1`) with the seconds the stage ran, and a
caller keeps it beside the stage's output as a `.log` or `.json`. This reads
every such receipt under a model's folder and lays them out in order: what ran,
when, for how long, and how long the model waited between stages (someone
looking at views or writing a vocabulary, or the machine busy with another
model).

A receipt written from 26 November 2026 on carries `started_utc` and
`finished_utc`. An older one has only its seconds, so its end is taken from the
file's modification time: when the caller finished writing it. A copied file
has lost that time, so such runs are marked as timed by file time.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

STAGE_RUN = "reference-asset-compiler.stage-run.v1"
SCHEMA = "reference-asset-compiler.time-to-model.v1"
# A receipt is a few kilobytes; a .json or .log far larger than this is
# something else (a painter log, a mesh report) and is not opened.
LARGEST_RECEIPT = 2_000_000
# A wait longer than this is reported as a pause, not as time between stages:
# a model left overnight and finished the next day did not take a day.
PAUSE_SECONDS = 1800.0


def _receipt(path: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > LARGEST_RECEIPT:
            return None
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    candidates = [text]
    # A log that captured something before the receipt (a launcher's banner)
    # still holds the receipt from its first line that opens an object.
    start = text.find("\n{")
    if start >= 0:
        candidates.append(text[start + 1:])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(payload, dict) and payload.get("schema") == STAGE_RUN:
            return payload
    return None


def _when(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def stage_runs(folder: Path) -> list[dict[str, Any]]:
    """Every stage-run receipt under `folder`, in the order the stages started."""
    folder = Path(folder)
    runs: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in (".log", ".json") or not path.is_file():
            continue
        payload = _receipt(path)
        if payload is None:
            continue
        seconds = float(payload.get("seconds") or 0.0)
        finished = _when(payload.get("finished_utc"))
        started = _when(payload.get("started_utc"))
        timed_by = "receipt"
        if finished is None:
            finished = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            timed_by = "file time"
        if started is None:
            started = finished - timedelta(seconds=seconds)
        # The same receipt kept twice (as .log and as .json) is one run.
        key = (payload.get("stage"), round(seconds, 3), payload.get("report"))
        if key in seen:
            continue
        seen.add(key)
        runs.append({
            "stage": payload.get("stage") or "?",
            "ok": bool(payload.get("ok")),
            "seconds": round(seconds, 1),
            "started_utc": started.isoformat(),
            "finished_utc": finished.isoformat(),
            "timed_by": timed_by,
            "receipt": str(path.relative_to(folder)),
            "_start": started.timestamp(),
            "_end": finished.timestamp(),
        })
    runs.sort(key=lambda run: (run["_start"], run["_end"]))
    return runs


def summarise(folder: Path, pause_seconds: float = PAUSE_SECONDS) -> dict[str, Any]:
    """A model's run front to back: its stages, the time they took, and the time between them."""
    folder = Path(folder).resolve()
    runs = stage_runs(folder)
    by_stage: dict[str, dict[str, float]] = {}
    for run in runs:
        entry = by_stage.setdefault(run["stage"], {"runs": 0, "seconds": 0.0})
        entry["runs"] += 1
        entry["seconds"] = round(entry["seconds"] + run["seconds"], 1)
    working = between = paused = 0.0
    pauses: list[dict[str, Any]] = []
    reach = None
    for run in runs:
        start, end = run["_start"], run["_end"]
        if reach is None:
            working += end - start
            reach = end
            continue
        if start > reach:
            gap = start - reach
            if gap > pause_seconds:
                paused += gap
                pauses.append({"after": run["started_utc"], "seconds": round(gap, 1)})
            else:
                between += gap
            working += end - start
            reach = end
        elif end > reach:
            # Two stages that ran at once count once: the clock ran once.
            working += end - reach
            reach = end
    wall = (runs[-1]["_end"] - runs[0]["_start"]) if runs else 0.0
    for run in runs:
        run.pop("_start")
        run.pop("_end")
    return {
        "schema": SCHEMA,
        "folder": str(folder),
        "runs": runs,
        "stage_runs": len(runs),
        "failed_runs": sum(1 for run in runs if not run["ok"]),
        "first_started_utc": runs[0]["started_utc"] if runs else None,
        "last_finished_utc": runs[-1]["finished_utc"] if runs else None,
        "seconds": {
            # Front to back, as a clock on the wall saw it, pauses left out.
            "front_to_back": round(working + between, 1),
            "in_stages": round(working, 1),
            "between_stages": round(between, 1),
            "paused": round(paused, 1),
            "wall_clock": round(wall, 1),
            "sum_of_stages": round(sum(run["seconds"] for run in runs), 1),
        },
        "pause_threshold_seconds": pause_seconds,
        "pauses": pauses,
        "by_stage": dict(sorted(by_stage.items(), key=lambda item: -item[1]["seconds"])),
        "timed_by_file_time": sum(1 for run in runs if run["timed_by"] == "file time"),
    }


def models_under(root: Path) -> list[Path]:
    """The folders directly under `root` that hold at least one stage-run receipt."""
    return [child for child in sorted(Path(root).iterdir())
            if child.is_dir() and stage_runs(child)]


def _clock(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return "{0}h {1:02d}m".format(hours, minutes)
    return "{0}m {1:02d}s".format(minutes, seconds)


def render(summaries: Iterable[dict[str, Any]], detail: bool = True) -> str:
    """The summaries as text a person reads."""
    summaries = list(summaries)
    lines: list[str] = []
    if len(summaries) > 1:
        lines.append("{0:<44} {1:>10} {2:>10} {3:>10} {4:>6}".format(
            "model", "front-back", "in stages", "between", "runs"))
        for summary in summaries:
            seconds = summary["seconds"]
            lines.append("{0:<44} {1:>10} {2:>10} {3:>10} {4:>6}".format(
                Path(summary["folder"]).name[:44], _clock(seconds["front_to_back"]),
                _clock(seconds["in_stages"]), _clock(seconds["between_stages"]), summary["stage_runs"]))
        lines.append("")
    if not detail:
        return "\n".join(lines).rstrip() + "\n"
    for summary in summaries:
        seconds = summary["seconds"]
        lines.append(summary["folder"])
        if not summary["runs"]:
            lines.append("  no stage-run receipts here")
            lines.append("")
            continue
        lines.append("  front to back {0}: {1} in stages, {2} between them{3}".format(
            _clock(seconds["front_to_back"]), _clock(seconds["in_stages"]), _clock(seconds["between_stages"]),
            "; {0} paused in {1} pause(s) left out".format(_clock(seconds["paused"]), len(summary["pauses"]))
            if summary["pauses"] else ""))
        for run in summary["runs"]:
            started = _when(run["started_utc"]).astimezone()
            lines.append("  {0}  {1:>8}  {2:<20} {3}{4}".format(
                started.strftime("%m-%d %H:%M:%S"), _clock(run["seconds"]), run["stage"], run["receipt"],
                "" if run["ok"] else "  (failed)"))
        lines.append("  by stage: " + ", ".join(
            "{0} {1}".format(name, _clock(entry["seconds"])) for name, entry in summary["by_stage"].items()))
        if summary["timed_by_file_time"]:
            lines.append("  {0} of {1} runs timed by their file's time (receipts from before 26 November)".format(
                summary["timed_by_file_time"], summary["stage_runs"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
