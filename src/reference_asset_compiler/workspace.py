"""Create and audit an evidence-gated asset workspace."""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .contracts import AUTOMATION_REVIEWERS, STAGE_STATUSES
from .evidence import (
    IMPORT_SCHEMA,
    evidence_display_path,
    find_receipt,
    is_sha256,
    load_json_receipts,
    record_evidence_paths,
    record_receipt_value,
    verify_record_evidence,
)
from .io import read_json, sha256_file, slugify, write_json, write_retained_json
from .planner import articulation_required, plan, required_stages
from .delegated_review import validate_delegated_review
from .native_revision import validate_native_revision, validate_matched_native_frames

MODELING_VIEWS = {
    "matcap-front.png",
    "matcap-three-quarter.png",
    "matcap-side.png",
    "matcap-back.png",
}
TEXTURE_VIEWS = {
    "beauty-front.png",
    "beauty-three-quarter.png",
    "beauty-side.png",
    "beauty-back.png",
}
HUMAN_STAGES = {"modeling_approval", "production_retopology", "texture_approval", "ue5_runtime_review",
                "ue5_motion_review", "cook"}
ARTICULATED_KINDS = {"humanoid", "mascot", "creature", "mechanical_articulated"}
GENERATION_SCHEMA = "reference-asset-compiler.geometry-candidate.v1"
MODELING_LINEAGE_SCHEMA = "reference-asset-compiler.modeling-derivative-lineage.v1"
CLEANUP_SCHEMA = "reference-asset-compiler.semantic-cleanup.v1"
RETOPOLOGY_SCHEMA = "reference-asset-compiler.production-retopology.v1"
UV_TRANSPORT_SCHEMA = "reference-asset-compiler.texture-uv-transport.v1"
LEDGER_SNAPSHOT_SCHEMA = "reference-asset-compiler.ledger-snapshot.v1"
STATE_LOCK_NAME = ".state.lock"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


# Kept as module names for callers and tests that imported the private helpers.
_receipt = find_receipt
_record_evidence_paths = record_evidence_paths
_record_receipt_value = record_receipt_value
_is_sha256 = is_sha256


def _evidence_hashes(paths: list[Path], receipt_path: Path) -> set[str]:
    return {sha256_file(path) for path in paths if path != receipt_path and path.is_file()}


def _require_bound_hashes(
    payload: dict[str, Any], keys: tuple[str, ...], hashes: set[str], stage: str
) -> None:
    missing = [key for key in keys
               if not _is_sha256(payload.get(key)) or payload[key] not in hashes]
    if missing:
        raise ValueError("{0} receipt is not bound to supplied evidence: {1}".format(
            stage, missing))


def _evidence_path_for_hash(
    paths: list[Path], receipt_path: Path, expected_sha256: str
) -> Path | None:
    for path in paths:
        if path != receipt_path and path.is_file() and sha256_file(path) == expected_sha256:
            return path
    return None


def _resolved_report_path(report_path: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else report_path.parent / path


def _validate_multiview_derivation_report(
    evidence: list[Path], receipt_path: Path, payload: dict[str, Any], source_sha256: str
) -> None:
    """Prove that the supplied split report names the source and every AI input view."""
    derivation_hash = payload["image_derivation_report_sha256"]
    report_path = _evidence_path_for_hash(evidence, receipt_path, derivation_hash)
    if report_path is None or report_path.suffix.lower() != ".json":
        raise ValueError("generate_candidates has no readable multiview derivation report")
    try:
        report = read_json(report_path)
    except (OSError, ValueError) as error:
        raise ValueError("generate_candidates has no readable multiview derivation report") from error

    report_source = _resolved_report_path(report_path, report.get("source"))
    embedded_source_hash = report.get("source_sha256")
    source_is_bound = embedded_source_hash == source_sha256
    if report_source is not None and report_source.is_file():
        source_is_bound = source_is_bound or sha256_file(report_source) == source_sha256
    if not source_is_bound:
        raise ValueError("multiview derivation report is not bound to the immutable source image")

    report_views = report.get("views")
    if not isinstance(report_views, list):
        raise ValueError("multiview derivation report does not enumerate conditioned views")
    indexed_views = {
        str(item.get("view", "")).strip(): item
        for item in report_views
        if isinstance(item, dict) and str(item.get("view", "")).strip()
    }
    for claimed in payload["image_inputs"]:
        report_view = indexed_views.get(claimed["view"])
        if report_view is None:
            raise ValueError("multiview derivation report omits conditioned view: {0}".format(
                claimed["view"]))
        output_path = _resolved_report_path(report_path, report_view.get("output"))
        embedded_view_hash = report_view.get("sha256")
        view_is_bound = embedded_view_hash == claimed["sha256"]
        if output_path is not None and output_path.is_file():
            view_is_bound = view_is_bound or sha256_file(output_path) == claimed["sha256"]
        if not view_is_bound:
            raise ValueError("multiview derivation report is not bound to view: {0}".format(
                claimed["view"]))


def _valid_frame_stats(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    mean = payload.get("mean_rgb")
    stddev = payload.get("stddev_rgb")
    return (
        isinstance(payload.get("width"), int) and payload["width"] >= 640
        and isinstance(payload.get("height"), int) and payload["height"] >= 360
        and isinstance(mean, list) and len(mean) == 3 and max(mean, default=0) >= 4.0
        and isinstance(stddev, list) and len(stddev) == 3 and max(stddev, default=0) >= 2.0
    )


def _validate_ue5_import_receipt(evidence: list[Path], maximum_vertices=None,
                                maximum_triangles=None) -> None:
    found = _receipt(evidence, IMPORT_SCHEMA)
    if found is None:
        raise ValueError("ue5_import requires a manifest-bound per-asset UE receipt")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(payload, ("manifest_sha256",), hashes, "ue5_import")
    result = payload.get("result")
    checks = result.get("checks") if isinstance(result, dict) else None
    if (payload.get("ok") is not True or not str(payload.get("asset_id", "")).strip()
            or not str(payload.get("engine_version", "")).strip()
            or not isinstance(result, dict) or result.get("ok") is not True
            or result.get("asset_id") != payload.get("asset_id")
            or result.get("manifest_sha256") != payload.get("manifest_sha256")
            or not isinstance(checks, list) or not checks
            or any(not isinstance(check, dict) or check.get("ok") is not True
                   for check in checks)):
        raise ValueError("ue5_import receipt does not prove successful native checks")
    if "native_revision" in payload:
        validate_native_revision(payload, evidence, maximum_vertices, maximum_triangles)


def _validate_generation_receipt(
    evidence: list[Path], source_sha256: str | None,
    allowed_geometry_adapters: set[str] | None,
) -> None:
    found = _receipt(evidence, "reference-asset-compiler.geometry-candidate.v1")
    if found is None:
        raise ValueError("generate_candidates requires an image-conditioned AI lineage report")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    candidate_hash = payload.get("candidate_sha256")
    image_hash = payload.get("image_sha256")
    adapter = payload.get("adapter")
    if (payload.get("ok") is not True or not _is_sha256(candidate_hash)
            or candidate_hash not in hashes):
        raise ValueError("generate_candidates report is not bound to the supplied AI mesh")
    if not _is_sha256(source_sha256):
        raise ValueError("generate_candidates has no immutable source-image hash")
    inputs = payload.get("image_inputs")
    derivation_hash = payload.get("image_derivation_report_sha256")
    multiview_claimed = inputs is not None or derivation_hash is not None
    if image_hash != source_sha256 or multiview_claimed:
        if (payload.get("source_image_sha256") != source_sha256
                or not _is_sha256(derivation_hash) or derivation_hash not in hashes
                or not isinstance(inputs, list) or len(inputs) < 2):
            raise ValueError("generate_candidates report is not bound to the immutable source image")
        for item in inputs:
            if (not isinstance(item, dict) or not str(item.get("view", "")).strip()
                    or not _is_sha256(item.get("sha256")) or item["sha256"] not in hashes):
                raise ValueError("generate_candidates has an unbound multiview image input")
        _validate_multiview_derivation_report(
            evidence, receipt_path, payload, source_sha256)
    if not allowed_geometry_adapters or adapter not in allowed_geometry_adapters:
        raise ValueError("generate_candidates adapter is not registered for this asset route")


def _validate_modeling_lineage(
    evidence: list[Path], generated_candidate_sha256: str | None,
) -> None:
    found = _receipt(evidence, "reference-asset-compiler.modeling-derivative-lineage.v1")
    if found is None:
        raise ValueError("modeling_approval requires lineage from the AI candidate to the reviewed mesh")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    source_hash = payload.get("source_ai_candidate_sha256")
    candidate_hash = payload.get("modeling_candidate_sha256")
    allowed_operations = {"direct_ai_candidate", "normalize_scale_origin", "voxel_remesh",
                          "collapse_qem"}
    operations = payload.get("operations")
    artifacts = payload.get("derivation_artifacts")
    if (payload.get("ok") is not True or not _is_sha256(generated_candidate_sha256)
            or source_hash != generated_candidate_sha256):
        raise ValueError("modeling lineage does not begin at the ledger AI candidate")
    if not _is_sha256(candidate_hash) or candidate_hash not in hashes:
        raise ValueError("modeling lineage is not bound to the reviewed mesh")
    if (not isinstance(operations, list) or not operations
            or any(operation not in allowed_operations for operation in operations)):
        raise ValueError("modeling lineage contains an unregistered derivation operation")
    if not isinstance(artifacts, list):
        raise ValueError("modeling lineage lacks its derivation artifacts")
    for artifact in artifacts:
        if (not isinstance(artifact, dict) or not str(artifact.get("role", "")).strip()
                or not _is_sha256(artifact.get("sha256"))
                or artifact["sha256"] not in hashes):
            raise ValueError("modeling lineage contains an unbound derivation artifact")


def _validate_runtime_review_receipt(evidence: list[Path], reviewer: str) -> None:
    from .static_review import SCHEMA as STATIC_REVIEW_SCHEMA, validate_static_frames
    found = _receipt(evidence, "reference-asset-compiler.ue5-runtime-review.v1")
    if found is None:
        raise ValueError("ue5_runtime_review requires its reviewed-frame receipt")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(
        payload,
        ("manifest_sha256", "gallery_report_sha256", "screenshot_sha256"),
        hashes,
        "ue5_runtime_review",
    )
    if (payload.get("status") != "approved" or payload.get("approved_by") != reviewer
            or not str(payload.get("asset_id", "")).strip()
            or not str(payload.get("note", "")).strip()
            or not _valid_frame_stats(payload.get("screenshot"))):
        raise ValueError("ue5_runtime_review receipt lacks a valid human-reviewed frame")
    gallery_path = _evidence_path_for_hash(evidence, receipt_path, payload["gallery_report_sha256"])
    if (read_json(gallery_path).get("schema") == STATIC_REVIEW_SCHEMA
            and "static_multiview_import_sha256" not in payload):
        raise ValueError("Static multiview runtime receipt is missing its import binding")
    if "native_import_sha256" in payload:
        _require_bound_hashes(payload, ("native_import_sha256",), hashes, "native runtime review")
        imported_path = _evidence_path_for_hash(evidence, receipt_path, payload["native_import_sha256"])
        gallery_path = _evidence_path_for_hash(evidence, receipt_path, payload["gallery_report_sha256"])
        imported, gallery = read_json(imported_path), read_json(gallery_path)
        if (imported.get("schema") != IMPORT_SCHEMA
                or imported.get("manifest_sha256") != payload.get("manifest_sha256")
                or imported.get("ok") is not True):
            raise ValueError("Native runtime review is not bound to its successful manifest import")
        frames = validate_matched_native_frames(
            gallery, imported["result"]["mesh"], imported["result"]["native_lods"][0]["vertices"])
        if any(sha256_file(path) not in hashes for path in frames):
            raise ValueError("Native runtime review lacks its complete frame evidence")
        if payload["screenshot_sha256"] not in {row["sha256"] for row in gallery["frames"]
                                               if row["mesh"] == imported["result"]["mesh"]}:
            raise ValueError("Native runtime primary frame shows a different mesh")
    if "static_multiview_import_sha256" in payload:
        key = "static_multiview_import_sha256"
        _require_bound_hashes(payload, (key,), hashes, "static multiview runtime review")
        imported_path = _evidence_path_for_hash(evidence, receipt_path, payload[key])
        gallery_path = _evidence_path_for_hash(evidence, receipt_path, payload["gallery_report_sha256"])
        imported, gallery = read_json(imported_path), read_json(gallery_path)
        if imported.get("manifest_sha256") != payload["manifest_sha256"]:
            raise ValueError("Static multiview manifest differs from runtime receipt")
        frames = validate_static_frames(gallery, imported, imported_path)
        frame_hashes = {sha256_file(path) for path in frames}
        if not frame_hashes <= hashes or payload["screenshot_sha256"] not in frame_hashes:
            raise ValueError("Static multiview runtime review lacks its complete frame evidence")


def _validate_cook_receipt(evidence: list[Path], reviewer: str) -> None:
    found = _receipt(evidence, "reference-asset-compiler.cooked-runtime-evidence.v1")
    if found is None:
        raise ValueError("cook requires clean packaged-runtime evidence")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(
        payload,
        ("manifest_sha256", "gallery_report_sha256", "cook_log_sha256",
         "package_log_sha256", "runtime_log_sha256", "runtime_frame_sha256"),
        hashes,
        "cook",
    )
    artifacts = payload.get("package_artifacts")
    if (payload.get("ok") is not True or payload.get("approved_by") != reviewer
            or not str(payload.get("asset_id", "")).strip()
            or not _valid_frame_stats(payload.get("runtime_frame"))
            or not isinstance(artifacts, list) or not artifacts):
        raise ValueError("cook receipt lacks valid packaged-runtime proof")
    suffixes: set[str] = set()
    for artifact in artifacts:
        if (not isinstance(artifact, dict) or not _is_sha256(artifact.get("sha256"))
                or artifact["sha256"] not in hashes
                or not isinstance(artifact.get("bytes"), int) or artifact["bytes"] <= 0):
            raise ValueError("cook receipt contains an unbound package artifact")
        suffixes.add(Path(str(artifact.get("path", ""))).suffix.lower())
    if ".exe" not in suffixes or not suffixes.intersection({".pak", ".utoc", ".ucas"}):
        raise ValueError("cook receipt requires an executable and packaged content containers")


def _validate_rig_receipt(evidence: list[Path]) -> None:
    found = _receipt(evidence, "reference-asset-compiler.rig-and-skin-evidence.v1")
    if found is None:
        raise ValueError("rig_and_skin requires a profile-bound rig and skin receipt")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(
        payload,
        ("approved_mesh_sha256", "rigged_fbx_sha256", "skeleton_profile_sha256",
         "gate_report_sha256"),
        hashes,
        "rig_and_skin",
    )
    gate = payload.get("gate")
    if (payload.get("ok") is not True or not str(payload.get("skeleton_profile", "")).strip()
            or not isinstance(gate, dict) or gate.get("ok") is not True
            or gate.get("profile") != payload.get("skeleton_profile")
            or gate.get("failures") not in ([], None)):
        raise ValueError("rig_and_skin receipt lacks a successful skeleton and skin gate")


def _validate_deformation_receipt(evidence: list[Path]) -> None:
    found = _receipt(evidence, "reference-asset-compiler.deformation-evidence.v1")
    if found is None:
        raise ValueError("deformation_validation requires a pose-suite receipt")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(
        payload, ("rigged_fbx_sha256", "deformation_report_sha256"), hashes,
        "deformation_validation")
    poses = payload.get("poses")
    required = {"arms_forward", "left_arm_only", "elbows_bent", "knees_bent",
                "spine_twist"}
    if (payload.get("ok") is not True or not isinstance(poses, dict)
            or set(poses) != required):
        raise ValueError("deformation receipt must exercise the complete required pose suite")
    for pose, result in poses.items():
        renders = result.get("renders") if isinstance(result, dict) else None
        if (result.get("skipped") is True or result.get("vertices_moved", 0) <= 0
                or not isinstance(renders, list) or len(renders) != 2
                or any(not _is_sha256(row.get("sha256")) or row["sha256"] not in hashes
                       for row in renders if isinstance(row, dict))
                or any(not isinstance(row, dict) for row in renders)):
            raise ValueError("deformation pose is incomplete or unbound: {0}".format(pose))


def _validate_semantic_cleanup_receipt(
    evidence: list[Path], modeling_candidate_sha256: str | None
) -> None:
    found = _receipt(evidence, "reference-asset-compiler.semantic-cleanup.v1")
    if found is None:
        raise ValueError("semantic_cleanup requires a hash-bound cleanup receipt")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(
        payload,
        ("input_mesh_sha256", "output_mesh_sha256", "topology_report_sha256"),
        hashes,
        "semantic_cleanup",
    )
    if (not _is_sha256(modeling_candidate_sha256)
            or payload.get("input_mesh_sha256") != modeling_candidate_sha256):
        raise ValueError("semantic_cleanup does not begin at the approved modeling mesh")
    report_path = _evidence_path_for_hash(
        evidence, receipt_path, payload.get("topology_report_sha256"))
    if report_path is None or report_path.suffix.lower() != ".json":
        raise ValueError("semantic_cleanup has no readable topology report")
    try:
        report = read_json(report_path)
    except (OSError, ValueError) as error:
        raise ValueError("semantic_cleanup has no readable topology report") from error
    before = report.get("before")
    after = report.get("after")
    roundtrip = report.get("roundtrip")
    operations = report.get("operations")
    allowed_operations = {
        "weld_coincident_vertices",
        "remove_degenerate_faces",
        "remove_loose_vertices",
        "recalculate_normals",
    }
    if (payload.get("ok") is not True
            or report.get("schema") != "reference-asset-compiler.semantic-cleanup-topology.v1"
            or report.get("ok") is not True
            or not isinstance(before, dict) or not isinstance(after, dict)
            or not isinstance(roundtrip, dict) or roundtrip != after
            or not isinstance(operations, list) or not operations
            or not set(operations).issubset(allowed_operations)):
        raise ValueError("semantic_cleanup receipt lacks a successful conservative cleanup")
    if (roundtrip.get("invalid_vertices") != 0
            or roundtrip.get("degenerate_faces") != 0
            or roundtrip.get("loose_vertices") != 0):
        raise ValueError("semantic_cleanup retains invalid, degenerate, or loose geometry")
    before_faces = before.get("faces")
    after_faces = after.get("faces")
    bbox_drift = report.get("bbox_max_drift_m")
    if (not isinstance(before_faces, int) or before_faces <= 0
            or not isinstance(after_faces, int)
            or after_faces < int(before_faces * 0.995)
            or after_faces > before_faces
            or not isinstance(bbox_drift, (int, float)) or bbox_drift > 0.000001):
        raise ValueError("semantic_cleanup changed the approved surface beyond its contract")


def _validate_retopology_receipt(
    evidence: list[Path], cleanup_output_sha256: str | None, reviewer: str,
    maximum_vertices: int | None, maximum_triangles: int | None, asset_kind: str | None,
) -> None:
    found = _receipt(evidence, "reference-asset-compiler.production-retopology.v1")
    if found is None:
        raise ValueError("production_retopology requires a hash-bound human approval receipt")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(
        payload, ("input_mesh_sha256", "output_mesh_sha256", "report_sha256"),
        hashes, "production_retopology")
    if (not _is_sha256(cleanup_output_sha256)
            or payload.get("input_mesh_sha256") != cleanup_output_sha256):
        raise ValueError("production_retopology does not begin at semantic cleanup output")
    report_path = _evidence_path_for_hash(evidence, receipt_path, payload["report_sha256"])
    if report_path is None or report_path.suffix.lower() != ".json":
        raise ValueError("production_retopology has no readable mechanical report")
    try:
        report = read_json(report_path)
    except (OSError, ValueError) as error:
        raise ValueError("production_retopology has no readable mechanical report") from error
    report_source = report.get("source") or {}
    report_output = report.get("output") or {}
    if (report.get("schema") != "reference-asset-compiler.production-retopology-candidate.v1"
            or report.get("status") != "mechanical_pass" or report.get("failures") not in ([], None)
            or report_source.get("sha256") != cleanup_output_sha256
            or report_output.get("sha256") != payload.get("output_mesh_sha256")
            or report_output.get("vertices") != payload.get("vertices")
            or report_output.get("triangles") != payload.get("triangles")
            or report_output.get("quad_fraction") != payload.get("quad_fraction")
            or report_output.get("boundary_edges") != 0
            or report_output.get("nonmanifold_edges") != 0):
        raise ValueError("production_retopology receipt contradicts its mechanical report")
    views = payload.get("fixed_views")
    expected_views = MODELING_VIEWS
    if (payload.get("status") != "approved" or payload.get("approved_by") != reviewer
            or not str(payload.get("note", "")).strip() or not isinstance(views, list)
            or {row.get("view") for row in views if isinstance(row, dict)} != expected_views):
        raise ValueError("production_retopology lacks its identified fixed-view approval")
    for row in views:
        if (not isinstance(row, dict) or not _is_sha256(row.get("sha256"))
                or row["sha256"] not in hashes):
            raise ValueError("production_retopology contains an unbound fixed view")
    if len({row["sha256"] for row in views}) != len(MODELING_VIEWS):
        raise ValueError("production_retopology fixed views are not distinct renders")
    topology_views = payload.get("topology_views")
    expected_topology_views = {
        "wireframe-front.png", "wireframe-three-quarter.png",
        "wireframe-side.png", "wireframe-back.png",
    }
    if asset_kind in ARTICULATED_KINDS:
        if (not isinstance(topology_views, list)
                or {row.get("view") for row in topology_views if isinstance(row, dict)}
                != expected_topology_views):
            raise ValueError("articulated production retopology lacks bound wireframe views")
        for row in topology_views:
            if (not isinstance(row, dict) or not _is_sha256(row.get("sha256"))
                    or row["sha256"] not in hashes):
                raise ValueError("production_retopology contains an unbound wireframe view")
        if len({row["sha256"] for row in topology_views}) != len(expected_topology_views):
            raise ValueError("production_retopology wireframe views are not distinct renders")
    vertices = payload.get("vertices")
    triangles = payload.get("triangles")
    if (not isinstance(vertices, int) or vertices <= 0 or maximum_vertices is None
            or vertices > maximum_vertices or not isinstance(triangles, int)
            or triangles <= 0 or maximum_triangles is None or triangles > maximum_triangles):
        raise ValueError("production_retopology exceeds the workspace runtime budget")
    if (asset_kind in ARTICULATED_KINDS
            and (payload.get("deformation_topology_reviewed") is not True
                 or not isinstance(payload.get("quad_fraction"), (int, float))
                 or payload["quad_fraction"] < 0.8)):
        raise ValueError("articulated production retopology lacks deformation-aware topology")


def _validate_motion_review_receipt(evidence: list[Path], reviewer: str) -> None:
    found = _receipt(evidence, "reference-asset-compiler.ue5-motion-review.v1")
    if found is None:
        raise ValueError("ue5_motion_review requires native motion checks and reviewed frames")
    receipt_path, payload = found
    hashes = _evidence_hashes(evidence, receipt_path)
    _require_bound_hashes(
        payload, ("manifest_sha256", "motion_report_sha256"), hashes,
        "ue5_motion_review")
    frames = payload.get("frames")
    if (payload.get("status") != "approved" or payload.get("approved_by") != reviewer
            or payload.get("accepted_runs", 0) < 2 or not isinstance(frames, list)
            or len(frames) < 2):
        raise ValueError("ue5_motion_review lacks two passing animations and reviewed frames")
    for frame in frames:
        if (not isinstance(frame, dict) or not _is_sha256(frame.get("sha256"))
                or frame["sha256"] not in hashes or not _valid_frame_stats(frame.get("stats"))):
            raise ValueError("ue5_motion_review contains an invalid or unbound frame")


def _named_report(evidence: list[Path], name: str, stage: str) -> dict[str, Any]:
    matches = [path for path in evidence if path.name.lower() == name]
    if len(matches) != 1:
        raise ValueError("{0} requires exactly one {1}; found {2}".format(
            stage, name, len(matches)))
    try:
        payload = read_json(matches[0])
    except (OSError, ValueError) as error:
        raise ValueError("{0} has an unreadable {1}".format(stage, name)) from error
    if not isinstance(payload, dict):
        raise ValueError("{0} requires {1} to be a JSON object".format(stage, name))
    return payload


def _lineage_links(receipts: list[tuple[Path, dict[str, Any]]]) -> dict[str, set[str]]:
    """output hash -> source hashes, from retained derivation receipts."""
    links: dict[str, set[str]] = {}

    def link(output: Any, source: Any) -> None:
        if is_sha256(output) and is_sha256(source):
            links.setdefault(output, set()).add(source)

    for _, payload in receipts:
        if payload.get("schema") == UV_TRANSPORT_SCHEMA and payload.get("status") == "passed":
            source = (payload.get("source") or {}).get("sha256")
            for key in ("uv_authority", "transport"):
                link((payload.get(key) or {}).get("sha256"), source)
        link(payload.get("output_sha256"), payload.get("source_sha256"))
    return links


def _require_uv_authority_lineage(
    payload: dict[str, Any], retopology_output_sha256: str | None,
    lineage_evidence: list[Path], stage: str,
) -> None:
    """retopo.json must name the approved retopology mesh, directly or via retained UV receipts."""
    authority = payload.get("source_uv_authority_sha256")
    if not is_sha256(authority):
        raise ValueError(
            "{0} retopo.json lacks a hash-bound source_uv_authority_sha256; the texture "
            "payload cannot be tied to the approved production retopology".format(stage))
    if not is_sha256(retopology_output_sha256):
        raise ValueError("{0} cannot bind retopo.json: production_retopology has no "
                         "hash-bound output mesh".format(stage))
    links = _lineage_links(load_json_receipts(lineage_evidence))
    frontier, seen = {authority}, set()
    while frontier:
        if retopology_output_sha256 in frontier:
            return
        seen |= frontier
        frontier = {source for output in frontier for source in links.get(output, ())} - seen
    raise ValueError(
        "{0} retopo.json source_uv_authority_sha256 {1} does not derive from the approved "
        "production retopology output {2}".format(
            stage, authority[:12], retopology_output_sha256[:12]))


def _validate_unwrap_and_bake(
    evidence: list[Path], retopology_output_sha256: str | None,
) -> None:
    if not any(path.suffix.lower() == ".png" for path in evidence):
        raise ValueError("unwrap_and_bake requires at least one baked PNG map")
    payload = _named_report(evidence, "retopo.json", "unwrap_and_bake")
    _require_uv_authority_lineage(payload, retopology_output_sha256, evidence, "unwrap_and_bake")
    _validate_texture_payload_files(payload, evidence, require_output=False)


def _validate_texture_payload_files(
    payload: dict[str, Any], evidence: list[Path], *, require_output: bool,
) -> None:
    report = next(path for path in evidence if path.name.lower() == "retopo.json")
    retained = {path.resolve() for path in evidence}
    baked = payload.get("baked")
    hashes = payload.get("baked_sha256")
    if not isinstance(baked, dict) or not baked or not isinstance(hashes, dict):
        raise ValueError("texture payload requires baked maps with baked_sha256 hashes")
    bindings = [(filename, hashes.get(channel)) for channel, filename in baked.items()]
    if require_output:
        bindings += [(payload.get("output_fbx"), payload.get("output_fbx_sha256")),
                     ("gate-tex.json", payload.get("gate_texture_sha256"))]
    for filename, expected in bindings:
        if not isinstance(filename, str) or not filename or not is_sha256(expected):
            raise ValueError("texture payload lacks a file or SHA-256 binding: {0}".format(filename))
        path = (report.parent / filename).resolve()
        if path not in retained or not path.is_file() or sha256_file(path) != expected:
            raise ValueError("texture payload does not bind the retained file: {0}".format(filename))


def _validate_texture_approval(
    evidence: list[Path], retopology_output_sha256: str | None,
    lineage_evidence: list[Path],
) -> None:
    names = {path.name.lower() for path in evidence}
    missing = sorted(TEXTURE_VIEWS - names)
    production = [path for path in evidence if path.name.lower().endswith("_production.fbx")]
    baked = [path for path in evidence
             if path.suffix.lower() == ".png" and path.name.lower() not in TEXTURE_VIEWS]
    required_reports = {"retopo.json", "gate-tex.json"}
    if missing or len(production) != 1 or not baked or not required_reports.issubset(names):
        raise ValueError("texture_approval requires production FBX, baked maps, reports, "
                         "and four lit views; missing views {0}".format(missing))
    gate = _named_report(evidence, "gate-tex.json", "texture_approval")
    if gate.get("ok") is not True:
        raise ValueError("texture_approval gate-tex.json does not record ok: true; "
                         "failures: {0}".format(gate.get("failures")))
    payload = _named_report(evidence, "retopo.json", "texture_approval")
    _require_uv_authority_lineage(
        payload, retopology_output_sha256, [*evidence, *lineage_evidence], "texture_approval")
    if payload.get("output_fbx") != production[0].name:
        raise ValueError("texture_approval production FBX differs from the texture payload")
    _validate_texture_payload_files(payload, evidence, require_output=True)


def _static_manifest(evidence: list[Path], stage: str) -> tuple[Path, dict[str, Any]]:
    matches = [path for path in evidence if path.name.lower().endswith(".ue5import.json")]
    if len(matches) != 1:
        raise ValueError("{0} requires exactly one published *.ue5import.json manifest; "
                         "found {1}".format(stage, len(matches)))
    try:
        manifest = read_json(matches[0])
    except (OSError, ValueError) as error:
        raise ValueError("{0} manifest is unreadable".format(stage)) from error
    if (not isinstance(manifest, dict) or manifest.get("asset_kind") != "static_prop"
            or not str(manifest.get("asset_id", "")).strip()
            or not isinstance(manifest.get("fbx"), str) or not manifest["fbx"]):
        raise ValueError("{0} requires a static_prop manifest naming its asset and FBX".format(
            stage))
    return matches[0], manifest


def _validate_collision_receipt(evidence: list[Path]) -> None:
    _, manifest = _static_manifest(evidence, "collision_optional")
    settings = manifest.get("ue5_import")
    if not isinstance(settings, dict) or not isinstance(settings.get("generate_collision"), bool):
        raise ValueError("collision_optional requires the manifest to declare "
                         "ue5_import.generate_collision explicitly")


def _validate_static_validation(evidence: list[Path]) -> None:
    manifest_path, manifest = _static_manifest(evidence, "static_validation")
    hashes = _evidence_hashes(evidence, manifest_path)
    root = manifest_path.parent
    payloads = {"fbx": root / manifest["fbx"]}
    textures = manifest.get("textures")
    if not isinstance(textures, dict):
        raise ValueError("static_validation requires the manifest to declare its textures")
    for material, slots in textures.items():
        if not isinstance(slots, dict):
            raise ValueError("static_validation manifest has a malformed material: {0}".format(
                material))
        for channel, spec in slots.items():
            file = spec.get("file") if isinstance(spec, dict) else None
            if not isinstance(file, str) or not file:
                raise ValueError("static_validation manifest texture lacks a file: {0}/{1}".format(
                    material, channel))
            payloads["{0}/{1}".format(material, channel)] = root / file
    for label, path in payloads.items():
        if not path.is_file() or sha256_file(path) not in hashes:
            raise ValueError("static_validation payload is not retained as hash-bound "
                             "evidence: {0}".format(label))
    declared = manifest.get("fbx_sha256")
    if declared is not None and str(declared).lower() != sha256_file(payloads["fbx"]):
        raise ValueError("static_validation manifest fbx_sha256 disagrees with the retained FBX")


def validate_passed_stage_contract(
    stage: str,
    evidence: list[Path],
    note: str | None,
    approved_by: str | None,
    source_sha256: str | None = None,
    allowed_geometry_adapters: set[str] | None = None,
    generated_candidate_sha256: str | None = None,
    modeling_candidate_sha256: str | None = None,
    cleanup_output_sha256: str | None = None,
    maximum_vertices: int | None = None,
    maximum_triangles: int | None = None,
    asset_kind: str | None = None,
    retopology_output_sha256: str | None = None,
    lineage_evidence: list[Path] | None = None,
) -> None:
    """Reject ledger passes that do not contain the proof their stage claims."""
    if stage in {"intake", "route"}:
        return
    if not evidence:
        raise ValueError("Cannot pass {0} without evidence".format(stage))
    if not str(note or "").strip():
        raise ValueError("Cannot pass {0} without a review note".format(stage))
    reviewer = str(approved_by or "").strip()
    if not reviewer:
        raise ValueError("Cannot pass {0} without approved_by".format(stage))
    if stage in HUMAN_STAGES and reviewer.lower() in AUTOMATION_REVIEWERS:
        try:
            validate_delegated_review(evidence, reviewer, source_sha256, stage)
        except ValueError as error:
            raise ValueError("{0} requires an identified human reviewer or explicit "
                             "hash-bound user delegation: {1}".format(stage, error)) from error

    names = {path.name.lower() for path in evidence}
    if stage == "generate_candidates":
        _validate_generation_receipt(evidence, source_sha256, allowed_geometry_adapters)
    elif stage == "modeling_approval":
        missing = sorted(MODELING_VIEWS - names)
        meshes = [path for path in evidence if path.suffix.lower() in {".fbx", ".glb"}]
        if missing or not meshes:
            raise ValueError("modeling_approval requires a mesh and four neutral views; "
                             "missing {0}".format(missing))
        _validate_modeling_lineage(evidence, generated_candidate_sha256)
    elif stage == "semantic_cleanup":
        _validate_semantic_cleanup_receipt(evidence, modeling_candidate_sha256)
    elif stage == "production_retopology":
        _validate_retopology_receipt(
            evidence, cleanup_output_sha256, reviewer,
            maximum_vertices, maximum_triangles, asset_kind)
    elif stage == "unwrap_and_bake":
        _validate_unwrap_and_bake(evidence, retopology_output_sha256)
    elif stage == "texture_approval":
        _validate_texture_approval(evidence, retopology_output_sha256, lineage_evidence or [])
    elif stage == "collision_optional":
        _validate_collision_receipt(evidence)
    elif stage == "static_validation":
        _validate_static_validation(evidence)
    elif stage == "rig_and_skin":
        _validate_rig_receipt(evidence)
    elif stage == "deformation_validation":
        _validate_deformation_receipt(evidence)
    elif stage == "ue5_import":
        _validate_ue5_import_receipt(evidence, maximum_vertices, maximum_triangles)
    elif stage == "ue5_runtime_review":
        _validate_runtime_review_receipt(evidence, reviewer)
    elif stage == "ue5_motion_review":
        _validate_motion_review_receipt(evidence, reviewer)
    elif stage == "cook":
        _validate_cook_receipt(evidence, reviewer)


def create_workspace(
    root: Path,
    reference: Path,
    asset_id: str,
    asset_kind: str,
    articulation: str,
    registry: dict[str, Any],
    candidate_adapters: list[str] | None = None,
    rig_backbone: str | None = None,
    skeleton_profile: str | None = None,
    maximum_vertices: int = 15_000,
    maximum_triangles: int = 20_000,
) -> Path:
    """Validate everything first; the filesystem is touched only once the plan is sound."""
    reference = reference.resolve()
    if not reference.is_file():
        raise FileNotFoundError(f"Reference image does not exist: {reference}")
    if maximum_vertices <= 0 or maximum_triangles <= 0:
        raise ValueError("Runtime vertex and triangle budgets must be positive")
    slug = slugify(asset_id)
    job = root.resolve() / slug
    if job.exists() and any(job.iterdir()):
        raise FileExistsError(f"Asset workspace already exists and is not empty: {job}")
    source_path = "references/primary{0}".format(reference.suffix.lower())
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "asset_id": asset_id,
        "asset_slug": slug,
        "asset_kind": asset_kind,
        "articulation": articulation,
        "candidate_adapters": candidate_adapters,
        "rig_backbone": rig_backbone,
        "skeleton_profile": skeleton_profile,
        "source": {
            "primary_view": "front",
            "path": source_path,
            "sha256": sha256_file(reference),
            "original_filename": reference.name,
        },
        "budgets": {
            "maximum_vertices": maximum_vertices,
            "maximum_triangles": maximum_triangles,
        },
    }
    manifest = {key: value for key, value in manifest.items() if value is not None}
    routing = plan(manifest, registry)
    state = {
        "schema": "reference-asset-compiler.state.v1",
        "asset_id": asset_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "stages": {
            stage: {
                "status": "passed" if stage in {"intake", "route"} else "pending",
                "evidence": [],
                "note": "Immutable reference copied and hashed."
                if stage == "intake"
                else "Routing decision generated."
                if stage == "route"
                else None,
            }
            for stage in routing["stages"]
        },
    }

    copied_reference = job / source_path
    copied_reference.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(reference, copied_reference)
    if sha256_file(copied_reference) != manifest["source"]["sha256"]:
        raise ValueError("Reference image changed while it was being copied")
    write_json(job / "intake.json", manifest)
    write_json(job / "routing.json", routing)
    write_json(job / "state.json", state)
    for directory in (
        "candidates",
        "authority",
        "modeling",
        "textures",
        "rig",
        "exports",
        "validation",
        "rejected",
        "logs",
    ):
        (job / directory).mkdir(exist_ok=True)
    return job


def _load_workspace_contract(job: Path) -> tuple[dict, dict, dict, list[str]]:
    """Validate ledger shape before either auditing or recording a transition."""
    manifest, routing, state = (read_json(job / name) for name in
                                ("intake.json", "routing.json", "state.json"))
    for name, payload in (("intake", manifest), ("routing", routing), ("state", state)):
        if not isinstance(payload, dict):
            raise ValueError(f"{name}.json must contain an object")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise ValueError("Unsupported intake schema_version")
    for name, payload in (("routing", routing), ("state", state)):
        if payload.get("schema") != f"reference-asset-compiler.{name}.v1":
            raise ValueError(f"Unsupported {name} schema")
    asset_id = manifest.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id.strip():
        raise ValueError("Intake requires an asset_id")
    if any(payload.get("asset_id") != asset_id for payload in (routing, state)):
        raise ValueError("Intake, routing and state asset_id must agree")
    stages = required_stages(manifest)
    if routing.get("stages") != stages:
        raise ValueError("Routing stages disagree with the required intake pipeline")
    if (routing.get("asset_kind") != manifest["asset_kind"]
            or routing.get("articulation_mode") != manifest.get("articulation", "auto")
            or routing.get("articulated") is not articulation_required(
                manifest["asset_kind"], manifest.get("articulation", "auto"))):
        raise ValueError("Routing disagrees with the intake kind/articulation")
    source = manifest.get("source")
    if (not isinstance(source, dict) or not isinstance(source.get("path"), str)
            or not source["path"] or not _is_sha256(source.get("sha256"))):
        raise ValueError("Intake requires a source path and SHA-256")
    budgets = manifest.get("budgets")
    if not isinstance(budgets, dict) or any(
        type(budgets.get(key)) is not int or budgets[key] <= 0
        for key in ("maximum_vertices", "maximum_triangles")
    ):
        raise ValueError("Intake requires positive integer runtime budgets")
    candidates = routing.get("geometry_candidates")
    if not isinstance(candidates, list) or not candidates or any(
        not isinstance(item, str) or not item for item in candidates
    ):
        raise ValueError("Routing requires geometry candidate identifiers")
    records = state.get("stages")
    if not isinstance(records, dict):
        raise ValueError("State stages must be an object")
    missing, unexpected = sorted(set(stages) - records.keys()), sorted(records.keys() - set(stages))
    if missing or unexpected:
        raise ValueError(f"State stage set is invalid; missing={missing}; unexpected={unexpected}")
    for stage in stages:
        record = records[stage]
        if (not isinstance(record, dict) or not isinstance(record.get("status"), str)
                or record["status"] not in STAGE_STATUSES):
            raise ValueError(f"Invalid stage record/status for {stage}")
        evidence = record.get("evidence")
        if not isinstance(evidence, list):
            raise ValueError(f"Evidence for {stage} must be a list")
        for row in evidence:
            if (not isinstance(row, dict) or not isinstance(row.get("path"), str)
                    or not row["path"] or not _is_sha256(row.get("sha256"))
                    or type(row.get("bytes")) is not int or row["bytes"] < 0):
                raise ValueError(f"Invalid evidence record for {stage}")
    return manifest, routing, state, stages


def _verify_ledger_integrity(
    job: Path, manifest: dict[str, Any], state: dict[str, Any], stage_names: list[str]
) -> list[str]:
    """Source, evidence hash/size, and pass-order checks shared by audit and promotion."""
    failures: list[str] = []
    source = job / manifest["source"]["path"]
    if not source.is_file():
        failures.append(f"Missing immutable source: {source}")
    elif sha256_file(source) != manifest["source"]["sha256"]:
        failures.append("Immutable source hash changed")
    seen_unpassed = False
    for stage in stage_names:
        record = state["stages"][stage]
        status = record["status"]
        if status not in STAGE_STATUSES:
            failures.append(f"Invalid status for {stage}: {status}")
        if status != "passed":
            seen_unpassed = True
        elif seen_unpassed:
            failures.append(f"Stage {stage} passed before an earlier stage")
        failures.extend(verify_record_evidence(job, stage, record))
    return failures


def _stage_context(job: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Hashes and retained derivation receipts that later gates must chain to."""
    records = state["stages"]
    unwrap = records.get("unwrap_and_bake", {})
    return {
        "generated_candidate_sha256": record_receipt_value(
            job, records.get("generate_candidates", {}), GENERATION_SCHEMA, "candidate_sha256"),
        "modeling_candidate_sha256": record_receipt_value(
            job, records.get("modeling_approval", {}), MODELING_LINEAGE_SCHEMA,
            "modeling_candidate_sha256"),
        "cleanup_output_sha256": record_receipt_value(
            job, records.get("semantic_cleanup", {}), CLEANUP_SCHEMA, "output_mesh_sha256"),
        "retopology_output_sha256": record_receipt_value(
            job, records.get("production_retopology", {}), RETOPOLOGY_SCHEMA,
            "output_mesh_sha256"),
        "lineage_evidence": (record_evidence_paths(job, unwrap)
                             if unwrap.get("status") == "passed" else []),
    }


def _validate_stage(
    stage: str, evidence: list[Path], note: Any, approved_by: Any,
    manifest: dict[str, Any], routing: dict[str, Any], context: dict[str, Any],
) -> None:
    validate_passed_stage_contract(
        stage,
        evidence,
        note,
        approved_by,
        manifest.get("source", {}).get("sha256"),
        set(routing.get("geometry_candidates", [])),
        maximum_vertices=manifest.get("budgets", {}).get("maximum_vertices"),
        maximum_triangles=manifest.get("budgets", {}).get("maximum_triangles"),
        asset_kind=manifest.get("asset_kind"),
        **context,
    )


@contextmanager
def _state_lock(job: Path) -> Iterator[None]:
    """Serialize state.json read-modify-write across processes on one host."""
    lock_path = job / STATE_LOCK_NAME
    handle = open(lock_path, "a+b")
    try:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _snapshot_replaced_stage(job: Path, stage: str, state: dict[str, Any]) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = job / "validation" / "ledger-before-{0}-{1}.json".format(stage, stamp)
    if snapshot.exists():
        raise ValueError("Ledger snapshot already exists: {0}".format(snapshot))
    write_retained_json(snapshot, {
        "schema": LEDGER_SNAPSHOT_SCHEMA,
        "asset_id": state.get("asset_id"),
        "stage": stage,
        "snapshot_at": utc_now(),
        "record": state["stages"][stage],
        "state": state,
    })
    return snapshot


def promote_stage(
    job: Path,
    stage: str,
    evidence: list[Path],
    note: str,
    approved_by: str,
    status: str = "passed",
    replace: bool = False,
) -> dict[str, Any]:
    job = job.resolve()
    with _state_lock(job):
        return _promote_stage_locked(job, stage, evidence, note, approved_by, status, replace)


def _promote_stage_locked(
    job: Path, stage: str, evidence: list[Path], note: str, approved_by: str,
    status: str, replace: bool,
) -> dict[str, Any]:
    state_path = job / "state.json"
    manifest, routing, state, stage_names = _load_workspace_contract(job)
    if stage not in state["stages"]:
        raise ValueError(f"Unknown stage for this asset: {stage}")
    if status not in STAGE_STATUSES:
        raise ValueError(f"Unsupported stage status: {status}")
    integrity = _verify_ledger_integrity(job, manifest, state, stage_names)
    if integrity:
        raise ValueError("Cannot record {0}; existing ledger evidence failed verification: "
                         "{1}".format(stage, "; ".join(integrity)))
    current = state["stages"][stage]
    if current["status"] == "passed" and not replace:
        raise ValueError(
            f"{stage} is already passed; pass replace=True (rac promote --replace) to "
            "supersede it, which retains a ledger snapshot first")
    index = stage_names.index(stage)
    if status == "passed":
        unfinished = [
            name for name in stage_names[:index] if state["stages"][name]["status"] != "passed"
        ]
        if unfinished:
            raise ValueError(f"Cannot pass {stage}; earlier stages are not passed: {unfinished}")
    resolved_evidence = []
    evidence_rows = []
    for path in evidence:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Evidence file does not exist: {resolved}")
        resolved_evidence.append(resolved)
        evidence_rows.append(
            {
                "path": evidence_display_path(job, resolved),
                "sha256": sha256_file(resolved),
                "bytes": resolved.stat().st_size,
            }
        )
    if status == "passed":
        _validate_stage(stage, resolved_evidence, note, approved_by, manifest, routing,
                        _stage_context(job, state))
    replacement = {
        "status": status,
        "evidence": evidence_rows,
        "note": note,
        "approved_by": approved_by,
        "recorded_at": utc_now(),
    }
    if current["status"] == "passed":
        # Validate the proposed chain before retaining a replacement. A new
        # upstream mesh cannot inherit yesterday's downstream approvals.
        proposed = {**state, "stages": {**state["stages"], stage: replacement}}
        failures = _verify_ledger_integrity(job, manifest, proposed, stage_names)
        if failures:
            raise ValueError("Replacement would invalidate downstream stages: " + "; ".join(failures))
        context = _stage_context(job, proposed)
        for later in stage_names[index + 1:]:
            record = proposed["stages"][later]
            if record["status"] == "passed":
                _validate_stage(later, record_evidence_paths(job, record), record.get("note"),
                                record.get("approved_by"), manifest, routing, context)
        _snapshot_replaced_stage(job, stage, state)
    state["stages"][stage] = replacement
    state["updated_at"] = utc_now()
    write_json(state_path, state)
    return state


def audit_workspace(job: Path) -> dict[str, Any]:
    """Malformed or missing evidence is a failed audit, never a readiness claim."""
    try:
        return _audit_workspace(job)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return {
            "schema": "reference-asset-compiler.audit.v1",
            "asset_id": job.name,
            "asset_kind": None,
            "ok": False,
            "all_stages_passed": False,
            "production_ready": False,
            "failures": [f"Cannot audit workspace: {error}"],
            "stages": {},
        }


def _audit_workspace(job: Path) -> dict[str, Any]:
    job = job.resolve()
    manifest, routing, state, stage_names = _load_workspace_contract(job)
    failures = _verify_ledger_integrity(job, manifest, state, stage_names)
    try:
        context = _stage_context(job, state)
    except ValueError as error:
        failures.append(str(error))
        context = None
    for stage in stage_names:
        record = state["stages"][stage]
        if record["status"] != "passed" or context is None:
            continue
        try:
            _validate_stage(stage, record_evidence_paths(job, record), record.get("note"),
                            record.get("approved_by"), manifest, routing, context)
        except ValueError as error:
            failures.append(str(error))

    all_passed = all(record["status"] == "passed" for record in state["stages"].values())
    return {
        "schema": "reference-asset-compiler.audit.v1",
        "asset_id": manifest["asset_id"],
        "asset_kind": manifest["asset_kind"],
        "ok": not failures,
        "all_stages_passed": all_passed,
        "production_ready": not failures and all_passed,
        "failures": failures,
        "stages": {name: record["status"] for name, record in state["stages"].items()},
    }
