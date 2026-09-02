"""Immutable publication and Unreal evidence for portable static assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from .io import read_json, sha256_file
from .workspace import AUTOMATION_REVIEWERS, audit_workspace, promote_stage


def _require_clean_workspace(job: Path) -> dict[str, Any]:
    audit = audit_workspace(job)
    if not audit["ok"]:
        raise ValueError("workspace audit failed: {0}".format("; ".join(audit["failures"])))
    return read_json(job / "state.json")


def _require_human_reviewer(value: str, stage: str) -> str:
    reviewer = value.strip()
    if not reviewer or reviewer.lower() in AUTOMATION_REVIEWERS:
        raise ValueError("{0} requires an identified human reviewer".format(stage))
    return reviewer


def _manifest_payload_paths(manifest_path: Path, manifest: dict[str, Any]) -> list[Path]:
    root = manifest_path.parent
    paths = [manifest_path, root / manifest["fbx"]]
    for slots in manifest.get("textures", {}).values():
        for spec in slots.values():
            paths.append(root / spec["file"])
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("published payload is incomplete: {0}".format(missing))
    return paths


def record_static_publish_stages(job: Path, manifest_path: Path) -> dict[str, Any]:
    """Advance collision policy and local static validation after texture approval."""
    job = job.resolve()
    manifest_path = manifest_path.resolve()
    state = _require_clean_workspace(job)
    if state["stages"]["texture_approval"]["status"] != "passed":
        raise ValueError("texture_approval has not passed")
    manifest = read_json(manifest_path)
    if manifest.get("asset_kind") != "static_prop":
        raise ValueError("static publication stages require a static_prop manifest")
    payloads = _manifest_payload_paths(manifest_path, manifest)
    collision = (manifest.get("ue5_import") or {}).get("generate_collision")
    stages = (
        (
            "collision_optional",
            [manifest_path],
            "UE collision policy explicitly declared as {0}; engine import remains a later gate."
            .format("enabled" if collision else "disabled"),
        ),
        (
            "static_validation",
            payloads,
            "Published static payload and every declared texture exist and are hash-bound.",
        ),
    )
    for stage, evidence, note in stages:
        status = state["stages"][stage]["status"]
        if status == "pending":
            state = promote_stage(job, stage, evidence, note, "promote_production.py")
        elif status != "passed":
            raise ValueError("{0} is {1}".format(stage, status))
    return state


def extract_ue5_import_record(
    manifest_path: Path, batch_report_path: Path
) -> dict[str, Any]:
    """Validate and isolate one manifest-bound asset from a mutable UE batch report."""
    manifest_path = manifest_path.resolve()
    batch_report_path = batch_report_path.resolve()
    manifest = read_json(manifest_path)
    report = read_json(batch_report_path)
    asset_id = manifest["asset_id"]
    matches = [entry for entry in report.get("assets", []) if entry.get("asset_id") == asset_id]
    if len(matches) != 1:
        raise ValueError("expected one UE import result for {0}, found {1}".format(
            asset_id, len(matches)))
    entry = matches[0]
    if entry.get("manifest_sha256") != sha256_file(manifest_path):
        raise ValueError("UE result is not bound to the current production manifest")
    failed = [check.get("check") for check in entry.get("checks", []) if not check.get("ok")]
    if not entry.get("ok") or failed:
        raise ValueError("UE imported payload failed checks: {0}".format(failed or "unknown"))
    engine = report.get("engine_version")
    if not engine:
        raise ValueError("UE report does not identify the engine version")
    return {
        "schema": "reference-asset-compiler.ue5-import-evidence.v1",
        "asset_id": asset_id,
        "engine_version": engine,
        "manifest": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "batch_report": str(batch_report_path),
        "batch_report_sha256": sha256_file(batch_report_path),
        "result": entry,
        "ok": True,
    }


def record_ue5_import_stage(
    job: Path, manifest_path: Path, batch_report_path: Path
) -> Path:
    """Persist immutable per-asset UE evidence and promote the import stage."""
    job = job.resolve()
    state = _require_clean_workspace(job)
    prerequisite = ("deformation_validation"
                    if "deformation_validation" in state["stages"]
                    else "static_validation")
    if state["stages"][prerequisite]["status"] != "passed":
        raise ValueError("{0} has not passed".format(prerequisite))
    payload = extract_ue5_import_record(manifest_path, batch_report_path)
    output = job / "validation" / "ue5-import.json"
    encoded = json.dumps(payload, indent=2) + "\n"
    if output.exists() and output.read_text(encoding="utf-8") != encoded:
        raise ValueError("refusing to overwrite different retained UE import evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded, encoding="utf-8")
    status = state["stages"]["ue5_import"]["status"]
    if status == "pending":
        promote_stage(
            job,
            "ue5_import",
            [output, manifest_path.resolve()],
            "UE imported the exact manifest and every native payload check passed.",
            "record_ue5_import.py",
        )
    elif status != "passed":
        raise ValueError("ue5_import is {0}".format(status))
    return output


def _gallery_contains_asset(gallery: dict[str, Any], asset_id: str) -> bool:
    needle = asset_id.lower()
    return any(needle in str(row.get("asset", "")).lower() for row in gallery.get("placed", []))


def _image_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("runtime frame is missing: {0}".format(path))
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        if rgb.width < 640 or rgb.height < 360:
            raise ValueError("runtime frame is too small for review")
        stat = ImageStat.Stat(rgb)
        mean = [round(float(value), 3) for value in stat.mean]
        stddev = [round(float(value), 3) for value in stat.stddev]
        if max(mean) < 4.0 or max(stddev) < 2.0:
            raise ValueError("runtime frame is black or visually empty")
        return {"width": rgb.width, "height": rgb.height, "mean_rgb": mean,
                "stddev_rgb": stddev}


def _write_immutable(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError("refusing to overwrite different retained evidence: {0}".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def record_runtime_review_stage(
    job: Path,
    manifest_path: Path,
    gallery_report_path: Path,
    screenshot_path: Path,
    approved_by: str,
    note: str,
) -> Path:
    """Record an identified human review of the imported asset in its UE level."""
    job = job.resolve()
    state = _require_clean_workspace(job)
    if state["stages"]["ue5_import"]["status"] != "passed":
        raise ValueError("ue5_import has not passed")
    approved_by = _require_human_reviewer(approved_by, "runtime review")
    manifest_path = manifest_path.resolve()
    gallery_report_path = gallery_report_path.resolve()
    screenshot_path = screenshot_path.resolve()
    manifest = read_json(manifest_path)
    gallery = read_json(gallery_report_path)
    if not _gallery_contains_asset(gallery, manifest["asset_id"]):
        raise ValueError("gallery report does not place {0}".format(manifest["asset_id"]))
    payload = {
        "schema": "reference-asset-compiler.ue5-runtime-review.v1",
        "asset_id": manifest["asset_id"],
        "manifest_sha256": sha256_file(manifest_path),
        "gallery_report_sha256": sha256_file(gallery_report_path),
        "screenshot_sha256": sha256_file(screenshot_path),
        "screenshot": _image_stats(screenshot_path),
        "approved_by": approved_by,
        "note": note,
        "status": "approved",
    }
    output = job / "validation" / "ue5-runtime-review.json"
    _write_immutable(output, payload)
    status = state["stages"]["ue5_runtime_review"]["status"]
    if status == "pending":
        promote_stage(
            job,
            "ue5_runtime_review",
            [output, manifest_path, gallery_report_path, screenshot_path],
            note,
            approved_by,
        )
    elif status != "passed":
        raise ValueError("ue5_runtime_review is {0}".format(status))
    return output


def _require_log_markers(path: Path, markers: tuple[str, ...], label: str) -> None:
    if not path.is_file():
        raise ValueError("{0} log is missing: {1}".format(label, path))
    text = path.read_text(encoding="utf-8", errors="replace")
    missing = [marker for marker in markers if marker not in text]
    if missing:
        raise ValueError("{0} log lacks terminal markers: {1}".format(label, missing))


def record_cook_stage(
    job: Path,
    manifest_path: Path,
    gallery_report_path: Path,
    cook_log_path: Path,
    package_log_path: Path,
    runtime_log_path: Path,
    runtime_frame_path: Path,
    package_root: Path,
    approved_by: str,
) -> tuple[Path, dict[str, Any]]:
    """Bind a clean cook, package, packaged run, and reviewed in-game frame."""
    job = job.resolve()
    state = _require_clean_workspace(job)
    prerequisite = ("ue5_motion_review" if "ue5_motion_review" in state["stages"]
                    else "ue5_runtime_review")
    if state["stages"][prerequisite]["status"] != "passed":
        raise ValueError("{0} has not passed".format(prerequisite))
    approved_by = _require_human_reviewer(approved_by, "cooked-runtime proof")
    paths = [Path(path).resolve() for path in (
        manifest_path, gallery_report_path, cook_log_path, package_log_path,
        runtime_log_path, runtime_frame_path,
    )]
    (manifest_path, gallery_report_path, cook_log_path, package_log_path,
     runtime_log_path, runtime_frame_path) = paths
    package_root = package_root.resolve()
    manifest = read_json(manifest_path)
    gallery = read_json(gallery_report_path)
    if not _gallery_contains_asset(gallery, manifest["asset_id"]):
        raise ValueError("cooked gallery does not place {0}".format(manifest["asset_id"]))
    _require_log_markers(cook_log_path, (
        "LogCook: Display: Done!",
        "LogInit: Display: Success - 0 error(s), 0 warning(s)",
    ), "cook")
    _require_log_markers(package_log_path, (
        "BUILD SUCCESSFUL",
        "Success - 0 error(s), 0 warning(s)",
    ), "package")
    _require_log_markers(runtime_log_path, (
        "Load map complete /Game/Compiled/L_RacGallery",
    ), "packaged runtime")
    artifacts = sorted(
        [*package_root.glob("*.exe"), *package_root.rglob("*.pak"),
         *package_root.rglob("*.utoc"), *package_root.rglob("*.ucas")]
    )
    if not any(path.suffix.lower() == ".exe" for path in artifacts):
        raise ValueError("packaged executable is missing")
    if not any(path.suffix.lower() in {".pak", ".utoc", ".ucas"} for path in artifacts):
        raise ValueError("packaged content containers are missing")
    package_log_text = package_log_path.read_text(encoding="utf-8", errors="replace")
    package_locations = {
        str(package_root), str(package_root.parent),
        str(package_root).replace("\\", "/"), str(package_root.parent).replace("\\", "/"),
    }
    if not any(location in package_log_text for location in package_locations):
        raise ValueError("package log is not bound to the supplied package root")
    newest_input = max(manifest_path.stat().st_mtime, gallery_report_path.stat().st_mtime)
    if cook_log_path.stat().st_mtime < newest_input:
        raise ValueError("cook log predates the manifest or gallery")
    if package_log_path.stat().st_mtime < cook_log_path.stat().st_mtime:
        raise ValueError("package log predates the cook")
    if runtime_log_path.stat().st_mtime < package_log_path.stat().st_mtime:
        raise ValueError("packaged runtime log predates the package")
    if runtime_frame_path.stat().st_mtime < package_log_path.stat().st_mtime:
        raise ValueError("in-game frame predates the package")
    payload = {
        "schema": "reference-asset-compiler.cooked-runtime-evidence.v1",
        "asset_id": manifest["asset_id"],
        "manifest_sha256": sha256_file(manifest_path),
        "gallery_report_sha256": sha256_file(gallery_report_path),
        "cook_log_sha256": sha256_file(cook_log_path),
        "package_log_sha256": sha256_file(package_log_path),
        "runtime_log_sha256": sha256_file(runtime_log_path),
        "runtime_frame_sha256": sha256_file(runtime_frame_path),
        "runtime_frame": _image_stats(runtime_frame_path),
        "package_artifacts": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in artifacts
        ],
        "approved_by": approved_by,
        "ok": True,
    }
    output = job / "validation" / "cooked-runtime.json"
    _write_immutable(output, payload)
    status = state["stages"]["cook"]["status"]
    evidence = [output, manifest_path, gallery_report_path, cook_log_path,
                package_log_path, runtime_log_path, runtime_frame_path, *artifacts]
    if status == "pending":
        promote_stage(
            job,
            "cook",
            evidence,
            "Clean cook/package and reviewed frame from the packaged gallery runtime.",
            approved_by,
        )
    elif status != "passed":
        raise ValueError("cook is {0}".format(status))
    audit = audit_workspace(job)
    if not audit["production_ready"]:
        raise ValueError("cook recorded but workspace is not production-ready: {0}".format(audit))
    return output, audit
