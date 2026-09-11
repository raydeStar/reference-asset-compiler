"""Evidence helpers for conservative post-approval mesh cleanup."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .evidence import record_receipt, resolve_evidence_path, verified_evidence_hashes
from .io import read_json, sha256_file, write_retained_json
from .workspace import audit_workspace

CLEANUP_REPORT_SCHEMA = "reference-asset-compiler.semantic-cleanup-topology.v1"
CLEANUP_RECEIPT_SCHEMA = "reference-asset-compiler.semantic-cleanup.v1"
LINEAGE_SCHEMA = "reference-asset-compiler.modeling-derivative-lineage.v1"


def _resolve_evidence(job: Path, row: dict[str, Any]) -> Path:
    return resolve_evidence_path(job, row.get("path"))


def validate_cleanup_input(job: Path, input_mesh: Path) -> dict[str, Any]:
    """Require the exact human-approved modeling derivative as cleanup input."""
    job = job.resolve()
    input_mesh = input_mesh.resolve()
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    state = read_json(job / "state.json")
    modeling = state["stages"]["modeling_approval"]
    if modeling.get("status") != "passed":
        raise ValueError("modeling_approval has not passed")
    input_hash = sha256_file(input_mesh)
    evidence_hashes = verified_evidence_hashes(job, modeling)
    found = record_receipt(job, modeling, LINEAGE_SCHEMA)
    lineage = found[1] if found else None
    if lineage is None or lineage.get("modeling_candidate_sha256") != input_hash:
        raise ValueError("cleanup input is not the lineage-approved modeling mesh")
    if input_hash not in evidence_hashes:
        raise ValueError("cleanup input is not retained in modeling approval evidence")
    return {
        "schema": "reference-asset-compiler.semantic-cleanup-preflight.v1",
        "asset_id": state["asset_id"],
        "workspace": str(job),
        "input_mesh": str(input_mesh),
        "input_mesh_sha256": input_hash,
        "launch_ready": True,
        "cleanup_launched": False,
    }


def record_cleanup_receipt(
    job: Path,
    input_mesh: Path,
    output_mesh: Path,
    topology_report: Path,
    output: Path | None = None,
) -> dict[str, Any]:
    """Validate a conservative Blender cleanup and freeze its ledger receipt."""
    preflight = validate_cleanup_input(job, input_mesh)
    job = job.resolve()
    output_mesh = output_mesh.resolve()
    topology_report = topology_report.resolve()
    for path in (output_mesh, topology_report):
        if not path.is_file():
            raise FileNotFoundError("cleanup output is missing: {0}".format(path))
    report = read_json(topology_report)
    output_hash = sha256_file(output_mesh)
    if (report.get("schema") != CLEANUP_REPORT_SCHEMA or report.get("ok") is not True
            or report.get("source_sha256") != preflight["input_mesh_sha256"]
            or report.get("output_sha256") != output_hash):
        raise ValueError("cleanup topology report is not bound to its input and output")
    after = report.get("after") or {}
    roundtrip = report.get("roundtrip") or {}
    if roundtrip != after:
        raise ValueError("cleanup output does not preserve topology through serialization")
    if (roundtrip.get("invalid_vertices") != 0
            or roundtrip.get("degenerate_faces") != 0
            or roundtrip.get("loose_vertices") != 0):
        raise ValueError("cleanup output retains invalid, degenerate, or loose geometry")
    receipt = {
        "schema": CLEANUP_RECEIPT_SCHEMA,
        "asset_id": preflight["asset_id"],
        "input_mesh": preflight["input_mesh"],
        "input_mesh_sha256": preflight["input_mesh_sha256"],
        "output_mesh": str(output_mesh),
        "output_mesh_sha256": output_hash,
        "topology_report": str(topology_report),
        "topology_report_sha256": sha256_file(topology_report),
        "operations": report.get("operations"),
        "ok": True,
        "status": "conservative cleanup derivative -- modeling authority remains immutable",
    }
    receipt_path = (output or (job / "cleanup" / "semantic-cleanup-receipt.json")).resolve()
    try:
        write_retained_json(receipt_path, receipt)
    except ValueError as error:
        raise ValueError("refusing to overwrite different semantic cleanup evidence") from error
    return {**receipt, "receipt": str(receipt_path)}
