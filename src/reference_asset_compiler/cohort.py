"""Cohort-level production-readiness audit."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import read_json, sha256_file
from .workspace import audit_workspace

COHORT_SCHEMA = "reference-asset-compiler.cohort.v1"


def _display_path(path: Path) -> str:
    try:
        displayed = path.relative_to(Path.cwd().resolve())
    except ValueError:
        displayed = path
    return str(displayed).replace("\\", "/")


def audit_cohort(manifest_path: Path, workspace_root: Path) -> dict[str, Any]:
    """Require every named workspace to pass every asset-level production gate."""
    manifest_path = manifest_path.resolve()
    workspace_root = workspace_root.resolve()
    manifest = read_json(manifest_path)
    if manifest.get("schema") != COHORT_SCHEMA:
        raise ValueError("Unsupported cohort manifest schema")
    cohort_id = str(manifest.get("cohort_id") or "").strip()
    if not cohort_id:
        raise ValueError("Cohort manifest requires cohort_id")
    members = manifest.get("members")
    if not isinstance(members, list) or not members:
        raise ValueError("Cohort manifest requires at least one member")

    seen_assets: set[str] = set()
    seen_workspaces: set[str] = set()
    member_results: list[dict[str, Any]] = []
    failures: list[str] = []
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            raise ValueError("Cohort member {0} must be an object".format(index))
        asset_id = str(member.get("asset_id") or "").strip()
        workspace_name = str(member.get("workspace") or "").strip()
        asset_kind = str(member.get("asset_kind") or "").strip()
        maximum_vertices = member.get("maximum_vertices")
        maximum_triangles = member.get("maximum_triangles")
        if not asset_id or not workspace_name or not asset_kind:
            raise ValueError(
                "Cohort member {0} requires asset_id, workspace, and asset_kind".format(index)
            )
        if asset_id in seen_assets:
            raise ValueError("Duplicate cohort asset_id: {0}".format(asset_id))
        if workspace_name in seen_workspaces:
            raise ValueError("Duplicate cohort workspace: {0}".format(workspace_name))
        seen_assets.add(asset_id)
        seen_workspaces.add(workspace_name)

        workspace = (workspace_root / workspace_name).resolve()
        try:
            workspace.relative_to(workspace_root)
        except ValueError as error:
            raise ValueError(
                "Cohort workspace escapes workspace root: {0}".format(workspace_name)
            ) from error
        result: dict[str, Any] = {
            "asset_id": asset_id,
            "asset_kind": asset_kind,
            "workspace": workspace_name,
            "production_ready": False,
            "failures": [],
        }
        if maximum_vertices is not None or maximum_triangles is not None:
            if (not isinstance(maximum_vertices, int) or maximum_vertices <= 0
                    or not isinstance(maximum_triangles, int) or maximum_triangles <= 0):
                raise ValueError(
                    "Cohort member {0} has invalid runtime budgets".format(asset_id))
            result["budgets"] = {
                "maximum_vertices": maximum_vertices,
                "maximum_triangles": maximum_triangles,
            }
        state_path = workspace / "state.json"
        if not state_path.is_file():
            message = "Missing workspace for {0}: {1}".format(
                asset_id, _display_path(workspace)
            )
            result["failures"].append(message)
            failures.append(message)
            member_results.append(result)
            continue
        try:
            asset_audit = audit_workspace(workspace)
        except (FileNotFoundError, KeyError, ValueError) as error:
            message = "Invalid workspace for {0}: {1}".format(asset_id, error)
            result["failures"].append(message)
            failures.append(message)
            member_results.append(result)
            continue
        result["audit"] = asset_audit
        if maximum_vertices is not None:
            try:
                intake_budgets = read_json(workspace / "intake.json").get("budgets") or {}
            except (FileNotFoundError, ValueError) as error:
                message = "Workspace budgets are unreadable for {0}: {1}".format(
                    asset_id, error)
                result["failures"].append(message)
                failures.append(message)
            else:
                actual_vertices = intake_budgets.get("maximum_vertices")
                actual_triangles = intake_budgets.get("maximum_triangles")
                if (not isinstance(actual_vertices, int)
                        or actual_vertices > maximum_vertices
                        or not isinstance(actual_triangles, int)
                        or actual_triangles > maximum_triangles):
                    message = (
                        "Workspace runtime budget exceeds cohort contract for {0}: "
                        "vertices {1}/{2}, triangles {3}/{4}"
                    ).format(
                        asset_id, actual_vertices, maximum_vertices,
                        actual_triangles, maximum_triangles)
                    result["failures"].append(message)
                    failures.append(message)
        if asset_audit.get("asset_id") != asset_id:
            message = "Workspace asset mismatch: expected {0}, found {1}".format(
                asset_id, asset_audit.get("asset_id")
            )
            result["failures"].append(message)
            failures.append(message)
        if asset_audit.get("asset_kind") != asset_kind:
            message = "Workspace kind mismatch for {0}: expected {1}, found {2}".format(
                asset_id, asset_kind, asset_audit.get("asset_kind")
            )
            result["failures"].append(message)
            failures.append(message)
        if not asset_audit.get("ok"):
            for failure in asset_audit.get("failures", []):
                message = "{0}: {1}".format(asset_id, failure)
                result["failures"].append(message)
                failures.append(message)
        if not asset_audit.get("production_ready"):
            stages = asset_audit.get("stages", {})
            stage_summary = {
                status: [stage for stage, value in stages.items() if value == status]
                for status in ("rejected", "blocked", "in_progress", "pending")
            }
            result["stage_summary"] = stage_summary
            unresolved = [stage for stage, status in stages.items() if status != "passed"]
            if stage_summary["rejected"]:
                message = (
                    "{0} requires replacement evidence; rejected stages: {1}; "
                    "all unresolved stages: {2}"
                ).format(asset_id, stage_summary["rejected"], unresolved)
            elif stage_summary["blocked"]:
                message = (
                    "{0} is blocked at stages: {1}; all unresolved stages: {2}"
                ).format(asset_id, stage_summary["blocked"], unresolved)
            elif stage_summary["in_progress"]:
                message = (
                    "{0} has active stages: {1}; all unresolved stages: {2}"
                ).format(asset_id, stage_summary["in_progress"], unresolved)
            else:
                message = "{0} is incomplete; unresolved stages: {1}".format(
                    asset_id, unresolved
                )
            result["failures"].append(message)
            failures.append(message)
        result["production_ready"] = (
            not result["failures"] and asset_audit.get("production_ready") is True
        )
        member_results.append(result)

    ready_count = sum(1 for member in member_results if member["production_ready"])
    rejected_count = sum(
        bool(member.get("stage_summary", {}).get("rejected"))
        for member in member_results
    )
    blocked_count = sum(
        bool(member.get("stage_summary", {}).get("blocked"))
        for member in member_results
    )
    return {
        "schema": "reference-asset-compiler.cohort-audit.v1",
        "cohort_id": cohort_id,
        "manifest_sha256": sha256_file(manifest_path),
        "workspace_root": _display_path(workspace_root),
        "ok": not failures,
        "production_ready": not failures and ready_count == len(member_results),
        "summary": {
            "required_assets": len(member_results),
            "production_ready_assets": ready_count,
            "incomplete_assets": len(member_results) - ready_count,
            "rejected_assets": rejected_count,
            "blocked_assets": blocked_count,
        },
        "failures": failures,
        "members": member_results,
    }
