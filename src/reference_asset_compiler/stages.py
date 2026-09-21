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
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .geometry_stage import (
    GeometryStageError,
    geometry_missing,
    paint_missing,
    prepare_single_view_request,
    resolve_legacy_root,
)
from .human_scale import HumanScaleError, named_sizes, resolve_height
from .resources import checkout_root

BLENDER_ENVIRONMENT = "RAC_BLENDER"
"""Where the Blender executable is named, matching workflow_doctor."""

POWERSHELL = "powershell.exe"
"""Windows PowerShell 5.1, which the launchers are written against."""

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
    "geometry": {
        "runner": "powershell",
        "script": "scripts/run_hy3d_geometry.ps1",
        "arguments": ("source", "output", "report"),
        "options": ("asset_name", "seed", "steps", "octree_resolution", "chunks"),
        "prepare": "geometry",
        "needs": ("studio-tree",),
        "summary": "Turn one reference image into a candidate mesh with Hunyuan3D. Needs a GPU.",
        "produces": "reference-asset-compiler.geometry-candidate.v1",
    },
    "stage-mesh": {
        "runner": "blender",
        "script": "scripts/blender/stage_generated_mesh.py",
        "arguments": ("source", "output", "report"),
        "options": ("size", "size_adjust"),
        "prepare": "staged-mesh",
        "needs": ("blender",),
        # A .blend, not transport: the reduction stage opens one and is right
        # to insist, because glTF may split shared vertices at face-corner
        # normals and is not an editable topology authority.
        "output_suffix": ".blend",
        "summary": "Give a generated mesh its real size, as a .blend a reviewed stage can open.",
        "produces": "reference-asset-compiler.staged-mesh.v1",
    },
    "reduce-mesh": {
        "runner": "powershell",
        "script": "scripts/run_feature_qem_reduction.ps1",
        "arguments": ("source", "output", "report"),
        "options": ("triangle_budget", "weight_factor", "maximum_p99_m", "maximum_max_m"),
        "prepare": "reduction",
        "needs": ("blender",),
        "summary": "Collapse a staged mesh to a runtime budget, and measure what that cost.",
        "produces": "reference-asset-compiler.production-retopology-candidate.v1",
    },
    "uv-unwrap": {
        "runner": "powershell",
        "script": "scripts/run_texture_uv_prep.ps1",
        "arguments": ("source", "output", "report"),
        "options": ("allow_triangulated_glb",),
        "prepare": "uv-unwrap",
        "needs": ("blender",),
        "output_suffix": ".obj",
        "summary": "Unfold a mesh onto a map, moving no vertex, so it can be painted.",
        "produces": "reference-asset-compiler.texture-uv-transport.v1",
    },
    "texture": {
        "runner": "powershell",
        "script": "scripts/run_hy3d21_texture.ps1",
        "arguments": ("source", "output", "report"),
        "options": ("reference", "views", "resolution"),
        "prepare": "texture",
        "needs": ("paint-stack",),
        # The painter's own teardown can fault after it has written everything
        # and passed its geometry and UV gate. The launcher says so in as many
        # words -- process health is separate from whether the paint is sound --
        # so what this stage produced is the verdict, not how its runner died.
        "verdict": "produced",
        "summary": "Paint a UV-mapped mesh from its reference image. Needs a GPU with 21 GiB free.",
        "produces": "reference-asset-compiler.paint-validation.v1",
    },
}


class StageError(ValueError):
    """A stage cannot be run, and nothing is half-run in its place."""


def describe_stages(repo_root: Path | None = None, blender: str | None = None,
                    legacy_root: Path | None = None) -> dict[str, Any]:
    """What can be run here, and what is missing if it cannot.

    A consumer calls this before queueing work, so that a missing tool is a
    refusal with a reason rather than a job that fails an hour later.
    """
    root = repo_root or checkout_root()
    runner = resolve_blender(blender, required=False)
    legacy = resolve_legacy_root(legacy_root, required=False)
    stages = []
    for name, stage in sorted(STAGES.items()):
        script = (root / stage["script"]) if root else None
        missing = []
        if root is None:
            missing.append("checkout")
        elif script is None or not script.is_file():
            missing.append("script")
        # A Blender-run stage needs Blender by definition. Stages say what they
        # need *beyond* their runner -- reduce-mesh runs a PowerShell launcher
        # that drives Blender itself, and geometry needs weights instead.
        needs = set(stage.get("needs", ()))
        if stage["runner"] == "blender":
            needs.add("blender")
        if "blender" in needs and runner is None:
            missing.append("blender")
        if "studio-tree" in needs:
            # The weights and their environment are a separate install from
            # this checkout, and most machines running the studio have neither.
            missing += [item for item in geometry_missing(root, legacy) if item not in missing]
        if "paint-stack" in needs:
            # A second install again: painting has its own environment, its own
            # upstream checkout and its own weights, and a machine that can
            # generate geometry often cannot paint it.
            missing += [item for item in paint_missing(legacy) if item not in missing]
        described = {
            "stage": name,
            "runner": stage["runner"],
            "summary": stage["summary"],
            "produces": stage["produces"],
            "arguments": list(stage["arguments"]),
            "options": list(stage.get("options", ())),
            "available": not missing,
            "missing": missing,
            # What this stage writes. A consumer chaining stages has to name
            # the file before the stage runs, and a staged mesh is a .blend
            # where everything else is a .glb.
            "output_suffix": stage.get("output_suffix", ".glb"),
        }
        if "size" in stage.get("options", ()):
            # The vocabulary belongs here, with the table that turns a landmark
            # into metres. A consumer offering these as choices reads them;
            # keeping its own copy would be two lists to maintain and one day
            # two different answers.
            described["sizes"] = named_sizes()
        stages.append(described)
    return {
        "ok": True,
        "checkout": str(root) if root else None,
        "blender": runner,
        "legacy_root": str(legacy) if legacy else None,
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
    legacy_root: Path | None = None,
    options: dict[str, Any] | None = None,
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
    # A stage that needs more than the three paths prepares it here. Nothing a
    # prepare step does touches hardware: it writes what a launcher insists on
    # and works out what a caller asked for, so a run that could never have
    # been accepted is refused before anything is queued.
    context: dict[str, Any] = {}
    prepare = stage.get("prepare")
    if prepare == "geometry":
        context = prepare_geometry(Path(source), root, legacy_root, options or {})
    elif prepare == "staged-mesh":
        context = prepare_staged_mesh(options or {})
    elif prepare == "reduction":
        context = prepare_reduction(
            Path(source), Path(output), options or {}, resolve_blender(blender, required=False))
    elif prepare == "uv-unwrap":
        context = prepare_uv_unwrap(
            Path(source), Path(output), options or {}, resolve_blender(blender, required=False))
    elif prepare == "texture":
        context = prepare_texture(
            Path(source), Path(output), options or {}, resolve_legacy_root(legacy_root))
    extra = [str(item) for item in context.get("arguments", ())]

    if stage["runner"] == "blender":
        runner = resolve_blender(blender)
        # Blender's own argument convention: its flags, then the script, then a
        # bare -- after which the arguments belong to the script.
        command = [runner, "-b", "--factory-startup", "--python", str(script), "--",
                   *arguments, *extra]
    elif stage["runner"] == "powershell":
        # These launchers take named parameters and decide their own output
        # paths, so the prepare step builds the whole argument list.
        runner = POWERSHELL
        command = [
            runner, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script), *extra,
        ]
    else:
        runner = blender or sys.executable
        command = [runner, str(script), "--", *arguments]

    started = time.monotonic()
    try:
        finished = subprocess.run(
            command, capture_output=True, text=True, errors="replace", timeout=timeout,
            # Nothing here may ever wait to be typed at. A stage is run by a
            # queue worker whose own input is whatever its parent happened to
            # hand it -- under a service that is a pipe nobody will ever write
            # to -- and a child that reads it waits for ever, holding a lease
            # and spending no CPU, which looks exactly like slow work.
            stdin=subprocess.DEVNULL)
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

    payload.update(context.get("payload", {}))

    # Most stages are judged by their exit code. One is judged by what it left
    # behind, because its painter can fault during teardown after writing
    # everything and passing its own gate -- and a run whose promised output
    # and validated receipt are both on disk did the work, however it died.
    delivered = bool(context.get("produced")) and all(
        Path(item).is_file() for item in context["produced"].values())
    survivable = stage.get("verdict") == "produced" and delivered

    if finished.returncode != 0 and not survivable:
        # The failure travels with the payload. Hunting a log on another
        # machine is not diagnosis.
        payload["stdout_tail"] = tail(finished.stdout)
        payload["stderr_tail"] = tail(finished.stderr)
        return payload
    if finished.returncode != 0:
        # Recorded rather than hidden: the next person reading this receipt
        # should know the process died even though the work stands.
        payload["ok"] = True
        payload["runner_exit_code"] = finished.returncode
        payload["runner_exit_note"] = (
            "The runner exited abnormally after producing and validating its output.")
        payload["stderr_tail"] = tail(finished.stderr)

    if context.get("produced"):
        try:
            collect_produced(context["produced"], Path(output), Path(report))
        except (OSError, GeometryStageError) as problem:
            payload["ok"] = False
            payload["error"] = "The run finished but its result could not be collected: {0}".format(
                problem)
            payload["stdout_tail"] = tail(finished.stdout)
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


def prepare_geometry(source: Path, root: Path, legacy_root: Path | None,
                     options: dict[str, Any]) -> dict[str, Any]:
    """Everything a geometry run needs, written before the GPU is asked for."""
    legacy = resolve_legacy_root(legacy_root)
    missing = geometry_missing(root, legacy)
    if missing:
        raise StageError(
            "This machine cannot run geometry; it is missing: {0}".format(", ".join(missing)))
    prepared = prepare_single_view_request(
        source, root,
        asset_name=options.get("asset_name"),
        parameters={key: options.get(key) for key in
                    ("seed", "steps", "octree_resolution", "chunks")},
    )
    return {
        "arguments": [
            "-Request", str(prepared["request"]),
            "-LegacyRoot", str(legacy),
            "-RepoRoot", str(root),
        ],
        "produced": {"output": prepared["candidate"], "report": prepared["receipt"]},
        "payload": {
            "asset_id": prepared["asset_id"],
            "workspace": str(prepared["workspace"]),
            "attempt_directory": str(prepared["attempt_directory"]),
            "attempt_report": str(prepared["attempt_report"]),
            "request_path": str(prepared["request"]),
            "source_sha256": prepared["source_sha256"],
            "parameters": prepared["parameters"],
        },
    }


def prepare_staged_mesh(options: dict[str, Any]) -> dict[str, Any]:
    """Work out the real-world height a named size means, before Blender runs.

    The size is a landmark on a person rather than a number of metres, because
    that is the question an artist can answer. Resolving it here means an
    unknown one is refused in the caller's own terms rather than inside a
    Blender process whose stderr somebody has to go and read.
    """
    size = options.get("size")
    if not size:
        raise StageError(
            "Staging a mesh needs its real size: say where it comes up to on a person "
            "with --size, for example --size knee.")
    try:
        resolved = resolve_height(str(size), float(options.get("size_adjust") or 1.0))
    except HumanScaleError as problem:
        raise StageError(str(problem)) from problem
    return {
        "arguments": ["--height-m", repr(resolved["height_m"]), "--size", resolved["size"]],
        "payload": {"scale": resolved},
    }


def prepare_reduction(source: Path, output: Path, options: dict[str, Any],
                      blender: str | None = None) -> dict[str, Any]:
    """Claim an attempt directory for a reducer that refuses to overwrite one.

    Attempts are kept rather than replaced, for the same reason generation
    attempts are: a rejected reduction and the settings that produced it are
    the record of what was tried, and the next budget is chosen by reading it.
    """
    output = Path(output).resolve()
    for number in range(1, 1000):
        attempt = output.parent / "{0}-reduction-attempt{1:03d}".format(output.stem, number)
        if not attempt.exists():
            break
    else:
        raise StageError("There are already 999 reduction attempts beside {0}".format(output))

    arguments = ["-InputMesh", str(Path(source).resolve()), "-OutputDirectory", str(attempt)]
    if blender:
        # Otherwise the launcher finds its own, which may not be the Blender
        # the studio named -- a difference nothing in a receipt would show.
        arguments += ["-Blender", str(blender)]
    for flag, name in (("-TriangleBudget", "triangle_budget"),
                       ("-WeightFactor", "weight_factor"),
                       ("-MaximumP99M", "maximum_p99_m"),
                       ("-MaximumMaxM", "maximum_max_m")):
        if options.get(name) is not None:
            arguments += [flag, str(options[name])]
    return {
        "arguments": arguments,
        "produced": {
            "output": attempt / "feature-qem-candidate.glb",
            "report": attempt / "reduction-report.json",
        },
        "payload": {"attempt_directory": str(attempt)},
    }


def _attempt(output: Path, label: str) -> Path:
    """The next unused attempt directory beside a caller's chosen output.

    These launchers all refuse to overwrite an attempt, for the same reason:
    a rejected result and the settings that produced it are the record by which
    the next settings are chosen.
    """
    output = Path(output).resolve()
    for number in range(1, 1000):
        attempt = output.parent / "{0}-{1}-attempt{2:03d}".format(output.stem, label, number)
        if not attempt.exists():
            return attempt
    raise StageError("There are already 999 {0} attempts beside {1}".format(label, output))


def prepare_uv_unwrap(source: Path, output: Path, options: dict[str, Any],
                      blender: str | None = None) -> dict[str, Any]:
    """Unfold a mesh onto a map so a painter can read it.

    A generated mesh has no UVs at all: nothing in generation makes them and
    nothing in reduction keeps them. The painter needs them and says so in the
    least helpful way available, by failing on a missing attribute deep inside
    a library, so this runs first and refuses in its own terms.
    """
    attempt = _attempt(output, "uv")
    arguments = ["-InputMesh", str(Path(source).resolve()), "-OutputDirectory", str(attempt)]
    if blender:
        arguments += ["-Blender", str(blender)]
    if options.get("allow_triangulated_glb"):
        # An already-approved static triangle mesh is accepted as it stands
        # rather than welded or remeshed, which is what a generated prop is.
        arguments.append("-AllowTriangulatedGlb")
    return {
        "arguments": arguments,
        "produced": {
            "output": attempt / "texture-transport.obj",
            "report": attempt / "uv-transport-report.json",
        },
        "payload": {"attempt_directory": str(attempt)},
    }


def prepare_texture(source: Path, output: Path, options: dict[str, Any],
                    legacy: Path) -> dict[str, Any]:
    """Everything the painter insists on, including the picture it paints from.

    The painter conditions on the same reference the geometry came from, which
    is a second input and the only stage here that takes one. Naming it is the
    caller's job because only the caller knows which picture an asset is of.
    """
    reference = options.get("reference")
    if not reference:
        raise StageError(
            "Painting needs the reference image it paints from: pass --reference.")
    reference = Path(reference).resolve()
    if not reference.is_file():
        raise StageError("The paint reference does not exist: {0}".format(reference))

    missing = paint_missing(legacy)
    if missing:
        raise StageError(
            "This machine cannot paint; it is missing: {0}".format(", ".join(missing)))

    attempt = _attempt(output, "paint")
    attempt.mkdir(parents=True, exist_ok=True)
    arguments = [
        "-Mesh", str(Path(source).resolve()),
        "-Reference", str(reference),
        # The launcher insists on an .obj path and derives every other name
        # from it, including the GLB a browser studio actually wants.
        "-OutputObj", str(attempt / "painted.obj"),
        "-LegacyRoot", str(legacy),
    ]
    for flag, name in (("-Views", "views"), ("-Resolution", "resolution")):
        if options.get(name) is not None:
            arguments += [flag, str(options[name])]
    return {
        "arguments": arguments,
        "produced": {
            "output": attempt / "painted.glb",
            "report": attempt / "painted.validation.json",
        },
        "payload": {
            "attempt_directory": str(attempt),
            "reference": str(reference),
            "execution_receipt": str(attempt / "painted.execution.json"),
        },
    }


def collect_produced(produced: dict[str, Path], output: Path, report: Path) -> None:
    """Put what a launcher wrote where the caller asked for it.

    These launchers write into their own attempt directories and will not be
    told otherwise, which is deliberate: an attempt stays beside the settings
    that produced it. Copying rather than moving keeps that record intact while
    still answering the caller in the terms it asked the question.
    """
    for key, destination in (("output", output), ("report", report)):
        source = Path(produced[key])
        if not source.is_file():
            raise GeometryStageError(
                "The run reported success but did not write {0}".format(source))
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def tail(text: str, lines: int = 20) -> list[str]:
    return [line for line in (text or "").splitlines() if line.strip()][-lines:]
