"""Run one named pipeline stage, so a consumer binds to a name not a file path.

The installed wheel carries the ledger; the pipeline scripts live in a
checkout. A studio driving this compiler should not have to know that, nor
where a stage's script sits, nor how Blender wants its arguments. It names a
stage and reads a receipt.

Stages are a registry rather than an arbitrary path, for two reasons: a
consumer asking for a name cannot ask this compiler to execute anything else,
and the files can move without breaking anyone downstream.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .resources import checkout_root

BLENDER_ENVIRONMENT = "RAC_BLENDER"
"""Where the Blender executable is named, matching workflow_doctor."""

DEFAULT_TIMEOUT_SECONDS = 3600
"""An hour. A stage that has not finished by then is a stage to investigate."""

STAGES: dict[str, dict[str, Any]] = {
    "browser-payload": {
        "runner": "blender",
        "script": "scripts/blender/export_browser_payload.py",
        "arguments": ("source", "output", "report"),
        "options": ("textures",),
        "summary": "Export the staged asset as a self-contained browser GLB, +Y up and metric.",
        "produces": "reference-asset-compiler.browser-payload.v1",
    },
}


class StageError(ValueError):
    """A stage cannot be run, and nothing is half-run in its place."""


def describe_stages(repo_root: Path | None = None, blender: str | None = None) -> dict[str, Any]:
    """What can be run here, and what is missing if it cannot.

    A consumer calls this before queueing work, so that a missing tool is a
    refusal with a reason rather than a job that fails an hour later.
    """
    root = repo_root or checkout_root()
    runner = resolve_blender(blender, required=False)
    stages = []
    for name, stage in sorted(STAGES.items()):
        script = (root / stage["script"]) if root else None
        missing = []
        if root is None:
            missing.append("checkout")
        elif script is None or not script.is_file():
            missing.append("script")
        if stage["runner"] == "blender" and runner is None:
            missing.append("blender")
        stages.append({
            "stage": name,
            "runner": stage["runner"],
            "summary": stage["summary"],
            "produces": stage["produces"],
            "arguments": list(stage["arguments"]),
            "options": list(stage.get("options", ())),
            "available": not missing,
            "missing": missing,
        })
    return {
        "ok": True,
        "checkout": str(root) if root else None,
        "blender": runner,
        "stages": stages,
    }


def resolve_blender(blender: str | None, required: bool = True) -> str | None:
    """The Blender to run, named explicitly or through the environment.

    No filesystem hunting: a guessed executable is a different Blender than the
    one an asset was gated with, and that difference is invisible in a receipt.
    """
    candidate = blender or os.environ.get(BLENDER_ENVIRONMENT)
    if candidate and Path(candidate).is_file():
        return str(Path(candidate))
    if not required:
        return None
    raise StageError(
        "This stage needs Blender. Pass --blender or set {0} to its executable.".format(
            BLENDER_ENVIRONMENT))


def run_stage(
    stage_name: str,
    source: Path,
    output: Path,
    report: Path,
    repo_root: Path | None = None,
    blender: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    textures: Path | None = None,
) -> dict[str, Any]:
    """Run one stage to completion and return what it produced."""
    stage = STAGES.get(stage_name)
    if stage is None:
        raise StageError("Unknown stage {0}. Known stages: {1}".format(
            stage_name, ", ".join(sorted(STAGES))))

    root = repo_root or checkout_root()
    if root is None:
        raise StageError(
            "Running a stage needs the pipeline scripts: pass --repo-root pointing to a "
            "Reference Asset Compiler checkout.")
    script = root / stage["script"]
    if not script.is_file():
        raise StageError("This checkout has no {0}.".format(stage["script"]))
    if not Path(source).is_file():
        raise StageError("The stage source does not exist: {0}".format(source))

    arguments = [
        str(Path(source).resolve()), str(Path(output).resolve()), str(Path(report).resolve()),
    ]
    if textures is not None:
        if "textures" not in stage.get("options", ()):
            raise StageError("Stage {0} takes no texture manifest.".format(stage_name))
        if not Path(textures).is_file():
            raise StageError("The named texture manifest does not exist: {0}".format(textures))
        arguments += ["--textures", str(Path(textures).resolve())]
    if stage["runner"] == "blender":
        runner = resolve_blender(blender)
        # Blender's own argument convention: its flags, then the script, then a
        # bare -- after which the arguments belong to the script.
        command = [runner, "-b", "--factory-startup", "--python", str(script), "--", *arguments]
    else:
        runner = blender or sys.executable
        command = [runner, str(script), "--", *arguments]

    started = time.monotonic()
    try:
        finished = subprocess.run(
            command, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise StageError("Stage {0} did not finish within {1} seconds.".format(stage_name, timeout))
    seconds = round(time.monotonic() - started, 3)

    payload: dict[str, Any] = {
        "ok": finished.returncode == 0,
        "schema": "reference-asset-compiler.stage-run.v1",
        "stage": stage_name,
        "runner": stage["runner"],
        "blender": runner,
        "exit_code": finished.returncode,
        "seconds": seconds,
        "report": str(report),
    }

    if finished.returncode != 0:
        # The failure travels with the payload. Hunting a log on another
        # machine is not diagnosis.
        payload["stdout_tail"] = tail(finished.stdout)
        payload["stderr_tail"] = tail(finished.stderr)
        return payload

    report_path = Path(report)
    if not report_path.is_file():
        payload["ok"] = False
        payload["error"] = "The stage exited cleanly but wrote no report."
        payload["stdout_tail"] = tail(finished.stdout)
        return payload
    try:
        payload["receipt"] = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as problem:
        payload["ok"] = False
        payload["error"] = "The stage's report could not be read: {0}".format(problem)
    return payload


def tail(text: str, lines: int = 20) -> list[str]:
    return [line for line in (text or "").splitlines() if line.strip()][-lines:]
