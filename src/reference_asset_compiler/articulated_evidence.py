"""Immutable rig, deformation, and UE motion evidence for articulated assets."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io import read_json, sha256_file
from .runtime_evidence import _image_stats, _require_human_reviewer, _write_immutable
from .workspace import audit_workspace, promote_stage

REQUIRED_POSES = {
    "arms_forward", "left_arm_only", "elbows_bent", "knees_bent", "spine_twist",
}


def _state(job: Path) -> dict[str, Any]:
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    return read_json(job / "state.json")


def _stage_hashes(state: dict[str, Any], stage: str) -> set[str]:
    return {row["sha256"] for row in state["stages"][stage].get("evidence", [])}


def _same_report_asset(report: dict[str, Any], asset: Path) -> bool:
    declared = report.get("asset")
    if not declared:
        return False
    try:
        return Path(str(declared)).resolve() == asset.resolve()
    except OSError:
        return False


def record_rig_and_skin_stage(
    job: Path,
    approved_mesh_path: Path,
    rigged_fbx_path: Path,
    skeleton_profile_path: Path,
    gate_report_path: Path,
) -> Path:
    """Bind a rigged FBX to the exact texture-approved mesh and skeleton profile."""
    job = job.resolve()
    state = _state(job)
    if state["stages"]["texture_approval"]["status"] != "passed":
        raise ValueError("texture_approval has not passed")
    paths = [Path(path).resolve() for path in (
        approved_mesh_path, rigged_fbx_path, skeleton_profile_path, gate_report_path,
    )]
    approved_mesh_path, rigged_fbx_path, skeleton_profile_path, gate_report_path = paths
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("rig evidence is incomplete: {0}".format(missing))
    approved_hash = sha256_file(approved_mesh_path)
    if approved_hash not in _stage_hashes(state, "texture_approval"):
        raise ValueError("rig input is not the exact texture-approved production mesh")
    profile = read_json(skeleton_profile_path)
    gate = read_json(gate_report_path)
    if (gate.get("ok") is not True or gate.get("failures")
            or gate.get("profile") != profile.get("profile_id")
            or not _same_report_asset(gate, rigged_fbx_path)):
        raise ValueError("rigged FBX did not pass its declared skeleton profile")
    payload = {
        "schema": "reference-asset-compiler.rig-and-skin-evidence.v1",
        "approved_mesh_sha256": approved_hash,
        "rigged_fbx_sha256": sha256_file(rigged_fbx_path),
        "skeleton_profile": profile["profile_id"],
        "skeleton_profile_sha256": sha256_file(skeleton_profile_path),
        "gate_report_sha256": sha256_file(gate_report_path),
        "gate": {
            "ok": True,
            "profile": gate["profile"],
            "bone_count": gate.get("bone_count"),
            "total_tris": gate.get("total_tris"),
            "failures": [],
            "warnings": gate.get("warnings", []),
        },
        "ok": True,
    }
    output = job / "validation" / "rig-and-skin.json"
    _write_immutable(output, payload)
    if state["stages"]["rig_and_skin"]["status"] == "pending":
        promote_stage(
            job, "rig_and_skin",
            [output, approved_mesh_path, rigged_fbx_path, skeleton_profile_path,
             gate_report_path],
            "Exact approved mesh passed the declared skeleton and skinning contract.",
            "record_rig_and_skin.py",
        )
    elif state["stages"]["rig_and_skin"]["status"] != "passed":
        raise ValueError("rig_and_skin is {0}".format(
            state["stages"]["rig_and_skin"]["status"]))
    return output


def record_deformation_stage(
    job: Path, rigged_fbx_path: Path, report_path: Path, render_directory: Path
) -> Path:
    """Require all five numeric deformation poses and their front/side renders."""
    job = job.resolve()
    state = _state(job)
    if state["stages"]["rig_and_skin"]["status"] != "passed":
        raise ValueError("rig_and_skin has not passed")
    rigged_fbx_path = rigged_fbx_path.resolve()
    report_path = report_path.resolve()
    render_directory = render_directory.resolve()
    report = read_json(report_path)
    rig_receipts = [job / row["path"] for row in state["stages"]["rig_and_skin"]["evidence"]
                    if row["path"].endswith("rig-and-skin.json")]
    if len(rig_receipts) != 1:
        raise ValueError("rig_and_skin receipt is missing")
    rig_receipt = read_json(rig_receipts[0])
    if sha256_file(rigged_fbx_path) != rig_receipt.get("rigged_fbx_sha256"):
        raise ValueError("deformation suite is not bound to the approved rigged FBX")
    poses = report.get("poses")
    if (report.get("ok") is not True or report.get("failures")
            or not _same_report_asset(report, rigged_fbx_path)
            or not isinstance(poses, dict) or set(poses) != REQUIRED_POSES):
        raise ValueError("deformation report did not pass the complete required pose suite")
    retained: dict[str, Any] = {}
    render_paths: list[Path] = []
    for name in sorted(REQUIRED_POSES):
        pose = poses[name]
        render_names = pose.get("renders") if isinstance(pose, dict) else None
        if (pose.get("skipped") is True or pose.get("vertices_moved", 0) <= 0
                or not isinstance(render_names, list) or len(render_names) != 2):
            raise ValueError("deformation pose is incomplete: {0}".format(name))
        expected = {"deform-{0}-front.png".format(name),
                    "deform-{0}-side.png".format(name)}
        if set(render_names) != expected:
            raise ValueError("deformation pose lacks fixed front/side views: {0}".format(name))
        rows = []
        for render_name in sorted(render_names):
            path = render_directory / render_name
            if not path.is_file():
                raise ValueError("deformation render is missing: {0}".format(path))
            render_paths.append(path)
            rows.append({"name": render_name, "sha256": sha256_file(path)})
        retained[name] = {"vertices_moved": pose["vertices_moved"],
                          "side_bias": pose.get("side_bias"), "renders": rows}
    payload = {
        "schema": "reference-asset-compiler.deformation-evidence.v1",
        "rigged_fbx_sha256": sha256_file(rigged_fbx_path),
        "deformation_report_sha256": sha256_file(report_path),
        "poses": retained,
        "warnings": report.get("warnings", []),
        "ok": True,
    }
    output = job / "validation" / "deformation.json"
    _write_immutable(output, payload)
    if state["stages"]["deformation_validation"]["status"] == "pending":
        promote_stage(
            job, "deformation_validation",
            [output, rigged_fbx_path, report_path, *render_paths],
            "Five required poses moved skin correctly and retained fixed front/side evidence.",
            "record_deformation.py",
        )
    elif state["stages"]["deformation_validation"]["status"] != "passed":
        raise ValueError("deformation_validation is {0}".format(
            state["stages"]["deformation_validation"]["status"]))
    return output


def _asset_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def record_ue5_motion_review_stage(
    job: Path,
    manifest_path: Path,
    motion_report_path: Path,
    frame_paths: list[Path],
    approved_by: str,
    note: str,
) -> Path:
    """Bind two passing UE animation runs to human-reviewed in-engine frames."""
    job = job.resolve()
    state = _state(job)
    if state["stages"]["ue5_import"]["status"] != "passed":
        raise ValueError("ue5_import has not passed")
    manifest_path = manifest_path.resolve()
    motion_report_path = motion_report_path.resolve()
    manifest = read_json(manifest_path)
    report = read_json(motion_report_path)
    token = _asset_token(manifest["asset_id"])
    runs = [run for run in report.get("runs", [])
            if token in _asset_token(str(run.get("asset", "")))]
    animations = {run.get("animation") for run in runs if run.get("ok") is True}
    if (len(animations) < 2 or any(run.get("ok") is not True for run in runs)
            or any(not run.get("checks") for run in runs)
            or any(any(check.get("ok") is not True for check in run.get("checks", []))
                   for run in runs)):
        raise ValueError("UE motion report lacks two clean animation runs for the asset")
    approved_by = _require_human_reviewer(approved_by, "UE motion review")
    if not note.strip():
        raise ValueError("UE motion review requires a review note")
    frames = []
    resolved_frames = []
    for frame_path in frame_paths:
        path = frame_path.resolve()
        frames.append({"path": str(path), "sha256": sha256_file(path),
                       "stats": _image_stats(path)})
        resolved_frames.append(path)
    if len(frames) < 2:
        raise ValueError("UE motion review requires at least two in-engine frames")
    payload = {
        "schema": "reference-asset-compiler.ue5-motion-review.v1",
        "asset_id": manifest["asset_id"],
        "manifest_sha256": sha256_file(manifest_path),
        "motion_report_sha256": sha256_file(motion_report_path),
        "engine_version": report.get("engine_version"),
        "accepted_runs": len(animations),
        "frames": frames,
        "approved_by": approved_by,
        "note": note,
        "status": "approved",
    }
    output = job / "validation" / "ue5-motion-review.json"
    _write_immutable(output, payload)
    if state["stages"]["ue5_motion_review"]["status"] == "pending":
        promote_stage(
            job, "ue5_motion_review",
            [output, manifest_path, motion_report_path, *resolved_frames],
            note, approved_by,
        )
    elif state["stages"]["ue5_motion_review"]["status"] != "passed":
        raise ValueError("ue5_motion_review is {0}".format(
            state["stages"]["ue5_motion_review"]["status"]))
    return output
