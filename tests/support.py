from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from reference_asset_compiler.approvals import record_modeling_derivative
from reference_asset_compiler.cleanup import record_cleanup_receipt
from reference_asset_compiler.io import read_json, sha256_file
from reference_asset_compiler.retopology import record_retopology_receipt
from reference_asset_compiler.workspace import promote_stage


def promote_generated(job: Path, payload: bytes = b"ai-generated-candidate") -> tuple[Path, Path]:
    """Create the smallest valid image-conditioned generation fixture."""
    candidate = job / "candidates" / "candidate.glb"
    report = job / "candidates" / "candidate.json"
    candidate.write_bytes(payload)
    intake = read_json(job / "intake.json")
    routing = read_json(job / "routing.json")
    report.write_text(json.dumps({
        "schema": "reference-asset-compiler.geometry-candidate.v1",
        "asset_id": intake["asset_id"],
        "adapter": routing["geometry_candidates"][0],
        "ok": True,
        "candidate_sha256": sha256_file(candidate),
        "image_sha256": intake["source"]["sha256"],
        "status": "candidate -- not approved, not an asset",
    }), encoding="utf-8")
    promote_stage(
        job, "generate_candidates", [candidate, report],
        "Hash-bound image-conditioned AI candidate retained.", "compile_from_image.py")
    return candidate, report


def modeling_evidence(job: Path, candidate: Path, views: list[Path]) -> list[Path]:
    lineage, artifacts = record_modeling_derivative(
        job, candidate, candidate, ["direct_ai_candidate"])
    return [candidate, lineage, *artifacts, *views]


def promote_cleanup(job: Path, candidate: Path) -> Path:
    """Advance the conservative cleanup contract with a compact test fixture."""
    output = job / "cleanup" / "cleaned.glb"
    report = job / "cleanup" / "topology.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"conservatively-cleaned-mesh")
    report.write_text(json.dumps({
        "schema": "reference-asset-compiler.semantic-cleanup-topology.v1",
        "source_sha256": sha256_file(candidate),
        "output_sha256": sha256_file(output),
        "operations": ["remove_degenerate_faces", "recalculate_normals"],
        "before": {
            "faces": 1000, "invalid_vertices": 0,
            "degenerate_faces": 1, "loose_vertices": 0,
        },
        "after": {
            "faces": 999, "invalid_vertices": 0,
            "degenerate_faces": 0, "loose_vertices": 0,
        },
        "roundtrip": {
            "faces": 999, "invalid_vertices": 0,
            "degenerate_faces": 0, "loose_vertices": 0,
        },
        "bbox_max_drift_m": 0.0,
        "ok": True,
    }), encoding="utf-8")
    payload = record_cleanup_receipt(job, candidate, output, report)
    receipt = Path(payload["receipt"])
    promote_stage(
        job, "semantic_cleanup", [candidate, output, report, receipt],
        "Conservative cleanup passed.", "semantic_cleanup.py")
    return output


def promote_retopology(job: Path, cleaned: Path, approved_by: str = "Ayric") -> Path:
    """Advance the production-retopology contract with a valid compact fixture."""
    directory = job / "retopology"
    output = directory / "runtime.blend"
    report = directory / "report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"production-retopology")
    report.write_text(json.dumps({
        "schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass",
        "source": {"sha256": sha256_file(cleaned)},
        "output": {
            "sha256": sha256_file(output), "vertices": 10000, "triangles": 19000,
            "quad_fraction": 0.9, "boundary_edges": 0, "nonmanifold_edges": 0,
        },
        "failures": [],
    }), encoding="utf-8")
    views = []
    for index, name in enumerate(("matcap-front.png", "matcap-three-quarter.png",
                                  "matcap-side.png", "matcap-back.png"), start=1):
        path = directory / "fixed-views" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (640, 640), (index * 40, index * 30, index * 20)).save(path)
        views.append(path)
    topology_views = []
    for index, name in enumerate(("wireframe-front.png", "wireframe-three-quarter.png",
                                  "wireframe-side.png", "wireframe-back.png"), start=1):
        path = directory / "topology-views" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (640, 640), (index * 20, index * 30, index * 50)).save(path)
        topology_views.append(path)
    payload = record_retopology_receipt(
        job, cleaned, output, report, views, approved_by,
        "Topology and fixed views approved.", topology_views)
    receipt = Path(payload["receipt"])
    promote_stage(
        job, "production_retopology",
        [cleaned, output, report, receipt, *views, *topology_views],
        "Topology and fixed views approved.", approved_by)
    return output
