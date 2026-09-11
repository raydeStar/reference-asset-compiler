from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from reference_asset_compiler.approvals import (
    TEXTURE_VIEW_NAMES,
    record_modeling_derivative,
    texture_evidence_paths,
)
from reference_asset_compiler.cleanup import record_cleanup_receipt
from reference_asset_compiler.io import read_json, sha256_file
from reference_asset_compiler.retopology import ARTICULATED_KINDS, record_retopology_receipt
from reference_asset_compiler.workspace import promote_stage

UV_TRANSPORT_SCHEMA = "reference-asset-compiler.texture-uv-transport.v1"
TEXTURE_PAYLOAD_SCHEMA = "reference-asset-compiler.generated-texture-payload.v1"


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
    articulated = read_json(job / "intake.json")["asset_kind"] in ARTICULATED_KINDS
    payload = record_retopology_receipt(
        job, cleaned, output, report, views, approved_by,
        "Topology and fixed views approved.", topology_views,
        deformation_topology_reviewed=articulated)
    receipt = Path(payload["receipt"])
    promote_stage(
        job, "production_retopology",
        [cleaned, output, report, receipt, *views, *topology_views],
        "Topology and fixed views approved.", approved_by)
    return output


def write_uv_transport(job: Path, retopology_output: Path) -> tuple[Path, Path]:
    """The UV authority derivative and the receipt binding it to the retopology mesh."""
    uv_dir = job / "texture" / "operator-uv-attempt001"
    uv_dir.mkdir(parents=True, exist_ok=True)
    uv_blend = uv_dir / "uv-authority.blend"
    uv_blend.write_bytes(b"uv-authority-derivative")
    transport = uv_dir / "texture-transport.obj"
    transport.write_bytes(b"triangulated-transport")
    report = uv_dir / "uv-transport-report.json"
    report.write_text(json.dumps({
        "schema": UV_TRANSPORT_SCHEMA,
        "status": "passed",
        "source": {"path": str(retopology_output), "sha256": sha256_file(retopology_output)},
        "uv_authority": {"path": str(uv_blend), "sha256": sha256_file(uv_blend)},
        "transport": {"path": str(transport), "sha256": sha256_file(transport)},
        "failures": [],
    }), encoding="utf-8")
    return uv_blend, report


def write_texture_payload(
    job: Path, uv_authority: Path, name: str = "prod-v2", gate_ok: bool = True,
    authority_sha256: str | None = None,
) -> tuple[Path, dict]:
    """Mirror package_character_texture.py: retopo.json, gate-tex.json, baked maps."""
    intake = read_json(job / "intake.json")
    prod = job / name
    prod.mkdir(parents=True, exist_ok=True)
    asset = intake["asset_slug"]
    baked = {channel: "T_{0}_{1}.png".format(asset, channel)
             for channel in ("BaseColor", "Roughness", "Metallic", "AO")}
    for channel, file in baked.items():
        (prod / file).write_bytes(("baked-" + channel).encode())
    retopo = {
        "schema": TEXTURE_PAYLOAD_SCHEMA,
        "asset_id": intake["asset_id"],
        "asset_kind": intake["asset_kind"],
        "source_uv_authority": str(uv_authority),
        "source_uv_authority_sha256": authority_sha256 or sha256_file(uv_authority),
        "output_fbx": "{0}_production.fbx".format(asset),
        "baked": baked,
        "texture_gate": {"ok": gate_ok},
        "ok": gate_ok,
    }
    (prod / "retopo.json").write_text(json.dumps(retopo, indent=2), encoding="utf-8")
    (prod / "gate-tex.json").write_text(json.dumps({
        "material": "M_Test", "ok": gate_ok,
        "failures": [] if gate_ok else ["baked lighting correlation 0.91 exceeds 0.35"],
        "warnings": [],
    }), encoding="utf-8")
    from reference_asset_compiler.texture_payload import bind_texture_payload
    output = prod / retopo["output_fbx"]
    output.write_bytes(b"production-fbx")
    retopo = bind_texture_payload(retopo, uv_authority, output, prod / "gate-tex.json")
    if authority_sha256 is not None:
        retopo["source_uv_authority_sha256"] = authority_sha256
    (prod / "retopo.json").write_text(json.dumps(retopo, indent=2), encoding="utf-8")
    return prod, retopo


def promote_unwrap_and_bake(
    job: Path, retopology_output: Path, name: str = "prod-v2",
) -> tuple[Path, dict]:
    """Advance unwrap_and_bake the way crank_from_image.py records it."""
    uv_blend, report = write_uv_transport(job, retopology_output)
    prod, retopo = write_texture_payload(job, uv_blend, name)
    evidence = [uv_blend, report, prod / "retopo.json", prod / "gate-tex.json",
                *(prod / file for file in retopo["baked"].values())]
    promote_stage(
        job, "unwrap_and_bake", evidence,
        "UV transport and topology-locked PBR maps passed mechanical gates.",
        "crank_from_image.py")
    return prod, retopo


def texture_payload_evidence(prod: Path, retopo: dict) -> list[Path]:
    """Add the production FBX and lit fixed views, then list what a reviewer approves."""
    (prod / retopo["output_fbx"]).write_bytes(b"production-fbx")
    (prod / "turn").mkdir(exist_ok=True)
    for name in TEXTURE_VIEW_NAMES:
        (prod / "turn" / name).write_bytes(name.encode())
    return texture_evidence_paths(prod, retopo)


def promote_texture_approval(
    job: Path, retopology_output: Path, approved_by: str = "Ayric",
) -> tuple[Path, dict, list[Path]]:
    """Advance through unwrap_and_bake and a human texture approval."""
    prod, retopo = promote_unwrap_and_bake(job, retopology_output)
    evidence = texture_payload_evidence(prod, retopo)
    promote_stage(job, "texture_approval", evidence, "Approved PBR response.", approved_by)
    return prod, retopo, evidence
