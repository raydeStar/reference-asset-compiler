"""Turn one reference image into everything a geometry run needs.

The Hunyuan launcher already refuses well: it preflights the request, pins the
runner by hash, checks free VRAM, and will not write into an attempt directory
that exists. What it does not do is invent the request, and a studio holding a
reference image should not have to know about workspaces, intakes, source
authorities or attempt numbering to ask for a model.

So this module builds that paperwork from an image and nothing else, in the
exact shape ``validate_geometry_request`` insists on. Every piece of it is
ordinary filesystem work: no GPU, no inference, no provider. That matters for
more than tidiness -- it means the part most likely to be wrong is the part that
can be tested on any machine, and a request that would have been rejected an
hour into a run is rejected before the GPU is touched at all.

A workspace is reused across attempts and its intake is immutable. Asking for a
model from a different image under a name already taken is an error rather than
a quiet overwrite, because the intake is what binds every later candidate,
receipt and rig back to the picture a person actually chose.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from .io import read_json, sha256_file, write_json

LEGACY_ROOT_ENVIRONMENT = "RAC_LEGACY_ROOT"
"""Where the Hunyuan checkout, weights and environment live, matching workflow_doctor."""

REQUEST_SCHEMA = "reference-asset-compiler.hy3d-geometry-request.v1"

DEFAULT_PARAMETERS: dict[str, int] = {
    "seed": 42,
    "steps": 30,
    "octree_resolution": 512,
    "chunks": 20000,
}
"""The settings the lakeside village props were generated with, which is the
only reason to prefer them: they are a known-good starting point on this
hardware rather than a claim about what is best."""

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

SLUG = re.compile(r"[^a-z0-9]+")


class GeometryStageError(ValueError):
    """A geometry run cannot be prepared, and nothing half-prepared is left."""


def slugify(value: str) -> str:
    """A workspace name that is safe on every filesystem and stable across runs."""
    slug = SLUG.sub("-", value.strip().lower()).strip("-")
    if not slug:
        raise GeometryStageError("An asset name must contain a letter or a digit")
    return slug[:64]


def resolve_legacy_root(explicit: str | Path | None = None, required: bool = True) -> Path | None:
    """The studio tree holding Hunyuan, named explicitly or through the environment.

    No searching, for the same reason Blender is not searched for: a guessed
    tree is a different set of weights from the one an asset was gated with, and
    nothing in a receipt would show the difference.
    """
    candidate = explicit or os.environ.get(LEGACY_ROOT_ENVIRONMENT)
    if candidate and Path(candidate).is_dir():
        return Path(candidate).resolve()
    if not required:
        return None
    raise GeometryStageError(
        "Geometry needs the Hunyuan studio tree. Pass --legacy-root or set {0}.".format(
            LEGACY_ROOT_ENVIRONMENT))


def geometry_environment(legacy_root: Path | None) -> Path | None:
    """The Python that owns the Hunyuan install, if this machine has one."""
    if legacy_root is None:
        return None
    interpreter = legacy_root / ".venv-hy3d" / "Scripts" / "python.exe"
    return interpreter if interpreter.is_file() else None


def geometry_missing(repo_root: Path | None, legacy_root: Path | None) -> list[str]:
    """What this machine lacks before a geometry run could start.

    A studio asks this before queueing anything. A missing weight tree answered
    now is a refusal with a reason; answered later it is a job that fails an
    hour in, having taken a place in a queue it could never have finished.
    """
    missing = []
    if repo_root is None:
        missing.append("checkout")
    elif not (repo_root / "workflows" / "geometry" / "hunyuan3d").is_dir():
        missing.append("runners")
    if legacy_root is None:
        missing.append("legacy-root")
    elif geometry_environment(legacy_root) is None:
        missing.append("geometry-environment")
    elif not (legacy_root / "upstream" / "Hunyuan3D-2").is_dir():
        missing.append("hunyuan-checkout")
    return missing


def paint_missing(legacy_root: Path | None) -> list[str]:
    """What this machine lacks before a paint run could start.

    The painter is a second install from the geometry one, with its own
    environment, its own upstream checkout and its own weights. A machine can
    easily have one and not the other, so they are answered separately rather
    than as one "AI is available" claim that would be wrong half the time.
    """
    if legacy_root is None:
        return ["legacy-root"]
    missing = []
    if not (legacy_root / ".venv-hy3d21" / "Scripts" / "python.exe").is_file():
        missing.append("paint-environment")
    if not (legacy_root / "scripts" / "run_hy3d21_pbr.py").is_file():
        missing.append("paint-runner")
    if not (legacy_root / "upstream" / "Hunyuan3D-2.1").is_dir():
        missing.append("paint-checkout")
    if not (legacy_root / "models" / "hy3d21" / "Hunyuan3D-2.1").is_dir():
        missing.append("paint-weights")
    return missing


def _validated_parameters(overrides: dict[str, Any] | None) -> dict[str, int]:
    parameters = dict(DEFAULT_PARAMETERS)
    for name, value in (overrides or {}).items():
        if value is None:
            continue
        if name not in DEFAULT_PARAMETERS:
            raise GeometryStageError("Unknown geometry parameter: {0}".format(name))
        parameters[name] = value
    # The launcher's own preflight checks these too. Checking here as well is
    # not duplication for its own sake: it is the difference between a message
    # naming the setting and a rejected request the caller has to decode.
    if not isinstance(parameters["seed"], int) or parameters["seed"] < 0:
        raise GeometryStageError("Geometry seed must be a non-negative integer")
    if not isinstance(parameters["steps"], int) or not 20 <= parameters["steps"] <= 60:
        raise GeometryStageError("Geometry steps must be within 20..60")
    if parameters["octree_resolution"] not in {256, 384, 512}:
        raise GeometryStageError("Geometry octree_resolution must be 256, 384, or 512")
    if not isinstance(parameters["chunks"], int) or not 1000 <= parameters["chunks"] <= 50000:
        raise GeometryStageError("Geometry chunks must be within 1000..50000")
    return parameters


def _intake(workspace: Path, asset_id: str, image: Path, digest: str) -> Path:
    """The workspace's immutable record of which picture this asset came from."""
    intake_path = workspace / "intake.json"
    reference = workspace / "references" / "primary.png"

    if intake_path.is_file():
        existing = read_json(intake_path)
        recorded = (existing.get("source") or {}).get("sha256")
        if existing.get("asset_id") != asset_id:
            raise GeometryStageError(
                "Workspace {0} already belongs to asset {1}".format(
                    workspace, existing.get("asset_id")))
        if recorded != digest:
            raise GeometryStageError(
                "Workspace {0} was taken from a different image (intake records {1}). "
                "Generate under a new name rather than replacing what earlier candidates "
                "were bound to.".format(workspace, recorded))
        return intake_path

    reference.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image, reference)
    if sha256_file(reference) != digest:
        raise GeometryStageError("The reference copy does not match the image it came from")
    write_json(intake_path, {
        "schema_version": 1,
        "asset_id": asset_id,
        "asset_slug": asset_id,
        "asset_kind": "unspecified",
        "articulation": "not_requested",
        "candidate_adapters": ["hunyuan3d_2_1"],
        "source": {
            "primary_view": "front",
            "path": "references/primary.png",
            "sha256": digest,
            "original_filename": image.name,
        },
    })
    return intake_path


def _attempt_directory(workspace: Path, seed: int) -> tuple[Path, Path]:
    """The next unclaimed attempt, because the launcher never overwrites one.

    Attempts are numbered rather than replaced so that a disappointing result
    stays on disk next to the settings that produced it. That is the whole
    record of what was tried.

    The directory alone is not enough to tell whether a number is free. The
    launcher is what creates it, so between preparing a request and running it
    there is nothing on disk under that name -- and preparing twice before
    running either would hand out the same number twice, making the second run
    fail at launch for a reason that happened much earlier. The request file is
    therefore what claims a number, and both have to be free.
    """
    candidates = workspace / "candidates"
    for number in range(1, 1000):
        attempt = candidates / "hy3d-single-seed{0}-attempt{1:03d}".format(seed, number)
        request = workspace / "{0}.geometry.json".format(attempt.name)
        if not attempt.exists() and not request.exists():
            return attempt, request
    raise GeometryStageError(
        "There are already 999 attempts at seed {0} in {1}".format(seed, candidates))


def prepare_single_view_request(
    image: Path,
    repo_root: Path,
    asset_name: str | None = None,
    parameters: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Write the workspace, intake and request for one image, and run nothing.

    Single view rather than multiview deliberately: multiview conditions on
    three derived guidance images and a derivation report binding each of them
    to the source, which is a separate piece of work with its own review. One
    picture in, one candidate out, is the honest shape of what a studio has when
    all it holds is a reference someone approved.
    """
    image = Path(image).resolve()
    if not image.is_file():
        raise GeometryStageError("The reference image does not exist: {0}".format(image))
    if image.suffix.lower() not in IMAGE_SUFFIXES:
        raise GeometryStageError(
            "Geometry conditions on an image; {0} is not one of {1}".format(
                image.suffix or "a file with no extension", ", ".join(IMAGE_SUFFIXES)))

    repo_root = Path(repo_root).resolve()
    work_root = Path(workspace_root).resolve() if workspace_root else repo_root / "work"
    asset_id = slugify(asset_name or image.stem)
    settings = _validated_parameters(parameters)
    digest = sha256_file(image)

    workspace = (work_root / asset_id).resolve()
    try:
        workspace.relative_to(work_root)
    except ValueError as error:
        raise GeometryStageError(
            "Asset name {0} escapes the workspace root".format(asset_id)) from error
    workspace.mkdir(parents=True, exist_ok=True)
    _intake(workspace, asset_id, image, digest)

    reference = workspace / "references" / "primary.png"
    attempt, request_path = _attempt_directory(workspace, settings["seed"])
    write_json(request_path, {
        "schema": REQUEST_SCHEMA,
        "asset_id": asset_id,
        "mode": "single_view",
        "workspace": str(workspace),
        "source_authority": {"path": str(reference), "sha256": digest},
        "inputs": [{"view": "primary", "path": str(reference), "sha256": digest}],
        "parameters": settings,
        "output_directory": str(attempt),
    })
    return {
        "asset_id": asset_id,
        "workspace": workspace,
        "request": request_path,
        "attempt_directory": attempt,
        "candidate": attempt / "candidate.glb",
        "receipt": attempt / "candidate-receipt.json",
        "attempt_report": attempt / "attempt.json",
        "source_sha256": digest,
        "parameters": settings,
    }
