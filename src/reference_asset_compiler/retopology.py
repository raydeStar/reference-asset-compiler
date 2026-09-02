"""Hash-bound approval receipts for production retopology derivatives."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from .io import read_json, sha256_file
from .workspace import AUTOMATION_REVIEWERS, audit_workspace

REPORT_SCHEMA = "reference-asset-compiler.production-retopology-candidate.v1"
RECEIPT_SCHEMA = "reference-asset-compiler.production-retopology.v1"
FIXED_VIEWS = {
    "matcap-front.png",
    "matcap-three-quarter.png",
    "matcap-side.png",
    "matcap-back.png",
}
TOPOLOGY_VIEWS = {
    "wireframe-front.png",
    "wireframe-three-quarter.png",
    "wireframe-side.png",
    "wireframe-back.png",
}
ARTICULATED_KINDS = {"humanoid", "mascot", "creature", "mechanical_articulated"}


def _stage_receipt(job: Path, stage: str, schema: str) -> dict[str, Any]:
    state = read_json(job / "state.json")
    record = state["stages"][stage]
    if record.get("status") != "passed":
        raise ValueError("{0} has not passed".format(stage))
    for row in record.get("evidence", []):
        path = Path(row["path"])
        path = path if path.is_absolute() else job / path
        if path.suffix.lower() == ".json" and path.is_file():
            payload = read_json(path)
            if payload.get("schema") == schema:
                return payload
    raise ValueError("{0} receipt is missing".format(stage))


def _validate_views(views: list[Path]) -> list[dict[str, Any]]:
    indexed = {path.name.lower(): path.resolve() for path in views}
    missing = sorted(FIXED_VIEWS - set(indexed))
    if missing or len(views) != len(FIXED_VIEWS) or len(indexed) != len(FIXED_VIEWS):
        raise ValueError("production retopology requires exactly four matcap views; missing {0}".format(
            missing))
    rows = []
    for name in sorted(FIXED_VIEWS):
        path = indexed[name]
        if not path.is_file():
            raise FileNotFoundError("retopology fixed view is missing: {0}".format(path))
        with Image.open(path) as image:
            width, height = image.size
        if width < 640 or height < 640:
            raise ValueError("retopology fixed view is too small for review: {0}".format(path))
        rows.append({"view": name, "path": str(path), "sha256": sha256_file(path)})
    if len({row["sha256"] for row in rows}) != len(FIXED_VIEWS):
        raise ValueError("production retopology fixed views must be four distinct renders")
    return rows


def _validate_topology_views(views: list[Path]) -> list[dict[str, Any]]:
    indexed = {path.name.lower(): path.resolve() for path in views}
    missing = sorted(TOPOLOGY_VIEWS - set(indexed))
    if missing or len(views) != len(TOPOLOGY_VIEWS) or len(indexed) != len(TOPOLOGY_VIEWS):
        raise ValueError(
            "articulated production retopology requires exactly four wireframe views; "
            "missing {0}".format(missing)
        )
    rows = []
    for name in sorted(TOPOLOGY_VIEWS):
        path = indexed[name]
        if not path.is_file():
            raise FileNotFoundError("retopology wireframe view is missing: {0}".format(path))
        with Image.open(path) as image:
            width, height = image.size
        if width < 640 or height < 640:
            raise ValueError("retopology wireframe view is too small for review: {0}".format(path))
        rows.append({"view": name, "path": str(path), "sha256": sha256_file(path)})
    if len({row["sha256"] for row in rows}) != len(TOPOLOGY_VIEWS):
        raise ValueError("production retopology wireframe views must be four distinct renders")
    return rows


def record_retopology_receipt(
    job: Path,
    input_mesh: Path,
    output_mesh: Path,
    report_path: Path,
    views: list[Path],
    approved_by: str,
    note: str,
    topology_views: list[Path] | None = None,
    output: Path | None = None,
) -> dict[str, Any]:
    """Approve an under-budget, deformation-aware derivative of semantic cleanup."""
    job = job.resolve()
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    reviewer = approved_by.strip()
    if not reviewer or reviewer.lower() in AUTOMATION_REVIEWERS:
        raise ValueError("production_retopology requires an identified human reviewer")
    if not note.strip():
        raise ValueError("production_retopology requires a review note")

    cleanup = _stage_receipt(
        job, "semantic_cleanup", "reference-asset-compiler.semantic-cleanup.v1")
    input_mesh = input_mesh.resolve()
    output_mesh = output_mesh.resolve()
    report_path = report_path.resolve()
    for path in (input_mesh, output_mesh, report_path):
        if not path.is_file():
            raise FileNotFoundError("retopology evidence is missing: {0}".format(path))
    input_hash = sha256_file(input_mesh)
    output_hash = sha256_file(output_mesh)
    if input_hash != cleanup.get("output_mesh_sha256"):
        raise ValueError("production retopology does not begin at semantic cleanup output")

    report = read_json(report_path)
    report_output = report.get("output") or {}
    report_source = report.get("source") or {}
    manifest = read_json(job / "intake.json")
    budgets = manifest["budgets"]
    vertices = report_output.get("vertices")
    triangles = report_output.get("triangles")
    quad_fraction = report_output.get("quad_fraction")
    if (report.get("schema") != REPORT_SCHEMA or report.get("status") != "mechanical_pass"
            or report.get("failures") not in ([], None)
            or report_source.get("sha256") != input_hash
            or report_output.get("sha256") != output_hash):
        raise ValueError("retopology report is not a passing derivative of its input and output")
    if (not isinstance(vertices, int) or vertices <= 0
            or vertices > budgets["maximum_vertices"]
            or not isinstance(triangles, int) or triangles <= 0
            or triangles > budgets["maximum_triangles"]):
        raise ValueError("retopology output exceeds the workspace runtime budget")
    if report_output.get("boundary_edges") != 0 or report_output.get("nonmanifold_edges") != 0:
        raise ValueError("retopology output is not a closed two-manifold surface")
    if (manifest["asset_kind"] in ARTICULATED_KINDS
            and (not isinstance(quad_fraction, (int, float)) or quad_fraction < 0.8)):
        raise ValueError("articulated production retopology requires at least 80% quads")

    view_rows = _validate_views(views)
    topology_view_rows = (
        _validate_topology_views(topology_views or [])
        if manifest["asset_kind"] in ARTICULATED_KINDS
        else []
    )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "asset_id": manifest["asset_id"],
        "asset_kind": manifest["asset_kind"],
        "input_mesh_sha256": input_hash,
        "output_mesh_sha256": output_hash,
        "report_sha256": sha256_file(report_path),
        "vertices": vertices,
        "triangles": triangles,
        "quad_fraction": quad_fraction,
        "fixed_views": view_rows,
        "topology_views": topology_view_rows,
        "deformation_topology_reviewed": manifest["asset_kind"] in ARTICULATED_KINDS,
        "approved_by": reviewer,
        "note": note.strip(),
        "status": "approved",
        "production_grade": False,
    }
    receipt_path = (output or (job / "retopology" / "production-retopology-receipt.json")).resolve()
    encoded = json.dumps(receipt, indent=2) + "\n"
    if receipt_path.exists() and receipt_path.read_text(encoding="utf-8") != encoded:
        raise ValueError("refusing to overwrite different production retopology evidence")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(encoded, encoding="utf-8")
    return {**receipt, "receipt": str(receipt_path)}
