"""Validation for deterministic Hunyuan geometry requests (multiview or single view)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import read_json, sha256_file

REQUEST_SCHEMA = "reference-asset-compiler.hy3d-geometry-request.v1"
REQUIRED_VIEWS = ("front", "left", "back")
SINGLE_VIEW = ("primary",)
MODES = {"multiview", "single_view"}


def _expand_path(value: Any, legacy_root: Path, repo_root: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Geometry request contains an empty path")
    expanded = value.replace("${RAC_LEGACY_ROOT}", str(legacy_root))
    expanded = expanded.replace("${RAC_REPO_ROOT}", str(repo_root))
    return Path(expanded).resolve()


def _require_hash(path: Path, expected: Any, label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError("Missing {0}: {1}".format(label, path))
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError("{0} hash changed: expected {1}, found {2}".format(
            label, expected, actual))


def validate_geometry_request(
    request_path: Path, legacy_root: Path, repo_root: Path
) -> dict[str, Any]:
    """Resolve and verify a one-attempt multiview generation request without launching it."""
    request_path = request_path.resolve()
    legacy_root = legacy_root.resolve()
    repo_root = repo_root.resolve()
    request = read_json(request_path)
    if request.get("schema") != REQUEST_SCHEMA:
        raise ValueError("Unsupported geometry request schema")
    asset_id = str(request.get("asset_id") or "").strip()
    if not asset_id:
        raise ValueError("Geometry request requires asset_id")

    workspace = _expand_path(request.get("workspace"), legacy_root, repo_root)
    work_root = (repo_root / "work").resolve()
    try:
        workspace.relative_to(work_root)
    except ValueError as error:
        raise ValueError("Geometry request workspace escapes repository work root") from error
    intake_path = workspace / "intake.json"
    intake = read_json(intake_path)
    if intake.get("asset_id") != asset_id:
        raise ValueError("Geometry request asset does not match workspace intake")

    authority = request.get("source_authority")
    if not isinstance(authority, dict):
        raise ValueError("Geometry request requires source_authority")
    authority_path = _expand_path(authority.get("path"), legacy_root, repo_root)
    authority_hash = authority.get("sha256")
    _require_hash(authority_path, authority_hash, "source authority")
    intake_source = intake.get("source") or {}
    intake_copy = workspace / str(intake_source.get("path") or "")
    if intake_source.get("sha256") != authority_hash:
        raise ValueError("Geometry request source does not match immutable workspace intake")
    _require_hash(intake_copy, authority_hash, "workspace source authority")

    mode = str(request.get("mode") or "multiview")
    if mode not in MODES:
        raise ValueError("Geometry request mode must be multiview or single_view")
    expected_views = REQUIRED_VIEWS if mode == "multiview" else SINGLE_VIEW

    derivation = request.get("derivation_report")
    derivation_path = derivation_hash = derivation_payload = None
    if mode == "multiview":
        # Guidance views are derived images; the report binds each one to the
        # immutable source so a stale or edited view cannot condition geometry.
        if not isinstance(derivation, dict):
            raise ValueError("Geometry request requires derivation_report")
        derivation_path = _expand_path(derivation.get("path"), legacy_root, repo_root)
        derivation_hash = derivation.get("sha256")
        _require_hash(derivation_path, derivation_hash, "derivation report")
        derivation_payload = read_json(derivation_path)
        report_source = _expand_path(
            derivation_payload.get("source"), legacy_root, repo_root)
        if derivation_payload.get("source_sha256") != authority_hash:
            raise ValueError("Derivation report source hash does not match source authority")
        if sha256_file(report_source) != authority_hash:
            raise ValueError("Derivation report is not bound to the workspace source authority")
    elif derivation is not None:
        raise ValueError("A single-view request conditions on the source itself; omit derivation_report")

    inputs = request.get("inputs")
    if not isinstance(inputs, list) or len(inputs) != len(expected_views):
        raise ValueError("Geometry request requires exactly {0} input(s)".format(
            ", ".join(expected_views)))
    input_by_view: dict[str, dict[str, Any]] = {}
    resolved_inputs = []
    for item in inputs:
        if not isinstance(item, dict):
            raise ValueError("Geometry request input must be an object")
        view = str(item.get("view") or "").strip()
        if view in input_by_view:
            raise ValueError("Duplicate geometry input view: {0}".format(view))
        input_path = _expand_path(item.get("path"), legacy_root, repo_root)
        input_hash = item.get("sha256")
        _require_hash(input_path, input_hash, "{0} input".format(view))
        input_by_view[view] = item
        resolved_inputs.append({
            "view": view,
            "path": str(input_path),
            "sha256": input_hash,
        })
    if set(input_by_view) != set(expected_views):
        raise ValueError("Geometry request requires exactly {0} input(s)".format(
            ", ".join(expected_views)))

    if mode == "single_view":
        # The one input must be the immutable source authority itself.
        primary = resolved_inputs[0]
        if primary["sha256"] != authority_hash or Path(primary["path"]) != authority_path:
            raise ValueError("Single-view input must be the workspace source authority")
    else:
        report_views = derivation_payload.get("views")
        if not isinstance(report_views, list):
            raise ValueError("Derivation report does not enumerate conditioned views")
        report_by_view = {
            str(item.get("view") or "").strip(): item
            for item in report_views if isinstance(item, dict)
        }
        if set(report_by_view) != set(REQUIRED_VIEWS):
            raise ValueError("Derivation report must enumerate exactly front, left, and back")
        for item in resolved_inputs:
            report_view = report_by_view.get(item["view"])
            if report_view is None:
                raise ValueError("Derivation report omits conditioned view: {0}".format(item["view"]))
            report_output = _expand_path(report_view.get("output"), legacy_root, repo_root)
            if (
                report_output != Path(item["path"])
                or report_view.get("sha256") != item["sha256"]
                or sha256_file(report_output) != item["sha256"]
            ):
                raise ValueError("Derivation report is not bound to view: {0}".format(item["view"]))

    parameters = request.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("Geometry request requires parameters")
    seed = parameters.get("seed")
    steps = parameters.get("steps")
    octree_resolution = parameters.get("octree_resolution")
    chunks = parameters.get("chunks")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("Geometry seed must be a non-negative integer")
    if not isinstance(steps, int) or not 20 <= steps <= 60:
        raise ValueError("Geometry steps must be within 20..60")
    if octree_resolution not in {256, 384, 512}:
        raise ValueError("Geometry octree_resolution must be 256, 384, or 512")
    if not isinstance(chunks, int) or not 1000 <= chunks <= 50000:
        raise ValueError("Geometry chunks must be within 1000..50000")

    output_directory = _expand_path(
        request.get("output_directory"), legacy_root, repo_root)
    candidates_root = (workspace / "candidates").resolve()
    try:
        output_directory.relative_to(candidates_root)
    except ValueError as error:
        raise ValueError("Geometry output escapes workspace candidates directory") from error
    if output_directory.exists():
        raise FileExistsError(
            "Geometry attempt directory already exists; do not retry it: {0}".format(
                output_directory))

    return {
        "schema": "reference-asset-compiler.hy3d-geometry-preflight.v1",
        "asset_id": asset_id,
        "request": str(request_path),
        "request_sha256": sha256_file(request_path),
        "workspace": str(workspace),
        "source_authority": {
            "path": str(authority_path),
            "sha256": authority_hash,
        },
        "mode": mode,
        "derivation_report": (
            {"path": str(derivation_path), "sha256": derivation_hash}
            if derivation_path is not None else None
        ),
        "inputs": resolved_inputs,
        "parameters": {
            "seed": seed,
            "steps": steps,
            "octree_resolution": octree_resolution,
            "chunks": chunks,
        },
        "output_directory": str(output_directory),
        "launch_ready": True,
        "inference_launched": False,
    }
