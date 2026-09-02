from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.cohort import audit_cohort


class CohortAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        self.work.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(self, members: list[dict]) -> Path:
        path = self.root / "cohort.json"
        path.write_text(json.dumps({
            "schema": "reference-asset-compiler.cohort.v1",
            "cohort_id": "test-cohort",
            "members": members,
        }), encoding="utf-8")
        return path

    def test_missing_workspace_fails_closed(self) -> None:
        manifest = self.write_manifest([{
            "asset_id": "missing-prop",
            "asset_kind": "static_prop",
            "workspace": "missing-prop",
        }])
        result = audit_cohort(manifest, self.work)
        self.assertFalse(result["production_ready"])
        self.assertEqual(1, result["summary"]["incomplete_assets"])
        self.assertIn("Missing workspace", result["failures"][0])

    def test_incomplete_member_blocks_cohort(self) -> None:
        workspace = self.work / "unfinished"
        workspace.mkdir()
        (workspace / "state.json").write_text("{}", encoding="utf-8")
        manifest = self.write_manifest([{
            "asset_id": "unfinished",
            "asset_kind": "static_prop",
            "workspace": "unfinished",
        }])
        with patch("reference_asset_compiler.cohort.audit_workspace", return_value={
            "asset_id": "unfinished",
            "asset_kind": "static_prop",
            "ok": True,
            "production_ready": False,
            "failures": [],
            "stages": {"intake": "passed", "cook": "pending"},
        }):
            result = audit_cohort(manifest, self.work)
        self.assertFalse(result["production_ready"])
        self.assertIn("unresolved stages: ['cook']", result["failures"][0])
        self.assertEqual([], result["members"][0]["stage_summary"]["rejected"])

    def test_rejected_stage_requires_replacement_evidence(self) -> None:
        workspace = self.work / "rejected-character"
        workspace.mkdir()
        (workspace / "state.json").write_text("{}", encoding="utf-8")
        manifest = self.write_manifest([{
            "asset_id": "rejected-character",
            "asset_kind": "humanoid",
            "workspace": "rejected-character",
        }])
        with patch("reference_asset_compiler.cohort.audit_workspace", return_value={
            "asset_id": "rejected-character",
            "asset_kind": "humanoid",
            "ok": True,
            "production_ready": False,
            "failures": [],
            "stages": {
                "generate_candidates": "passed",
                "modeling_approval": "rejected",
                "semantic_cleanup": "pending",
            },
        }):
            result = audit_cohort(manifest, self.work)
        self.assertFalse(result["production_ready"])
        self.assertEqual(1, result["summary"]["rejected_assets"])
        self.assertEqual(
            ["modeling_approval"],
            result["members"][0]["stage_summary"]["rejected"],
        )
        self.assertIn("requires replacement evidence", result["failures"][0])

    def test_every_member_must_be_ready(self) -> None:
        members = []
        for asset_id in ("hero", "prop"):
            workspace = self.work / asset_id
            workspace.mkdir()
            (workspace / "state.json").write_text("{}", encoding="utf-8")
            members.append({
                "asset_id": asset_id,
                "asset_kind": "humanoid" if asset_id == "hero" else "static_prop",
                "workspace": asset_id,
            })
        manifest = self.write_manifest(members)

        def ready_audit(workspace: Path) -> dict:
            return {
                "asset_id": workspace.name,
                "asset_kind": "humanoid" if workspace.name == "hero" else "static_prop",
                "ok": True,
                "production_ready": True,
                "failures": [],
                "stages": {"intake": "passed", "cook": "passed"},
            }

        with patch("reference_asset_compiler.cohort.audit_workspace", side_effect=ready_audit):
            result = audit_cohort(manifest, self.work)
        self.assertTrue(result["production_ready"])
        self.assertEqual(2, result["summary"]["production_ready_assets"])

    def test_duplicate_members_are_rejected(self) -> None:
        member = {
            "asset_id": "duplicate",
            "asset_kind": "static_prop",
            "workspace": "duplicate",
        }
        manifest = self.write_manifest([member, member])
        with self.assertRaisesRegex(ValueError, "Duplicate cohort asset_id"):
            audit_cohort(manifest, self.work)

    def test_workspace_cannot_escape_declared_root(self) -> None:
        manifest = self.write_manifest([{
            "asset_id": "escape",
            "asset_kind": "static_prop",
            "workspace": "../escape",
        }])
        with self.assertRaisesRegex(ValueError, "escapes workspace root"):
            audit_cohort(manifest, self.work)

    def test_workspace_kind_must_match_manifest(self) -> None:
        workspace = self.work / "wrong-kind"
        workspace.mkdir()
        (workspace / "state.json").write_text("{}", encoding="utf-8")
        manifest = self.write_manifest([{
            "asset_id": "wrong-kind",
            "asset_kind": "static_prop",
            "workspace": "wrong-kind",
        }])
        with patch("reference_asset_compiler.cohort.audit_workspace", return_value={
            "asset_id": "wrong-kind",
            "asset_kind": "humanoid",
            "ok": True,
            "production_ready": True,
            "failures": [],
            "stages": {"cook": "passed"},
        }):
            result = audit_cohort(manifest, self.work)
        self.assertFalse(result["production_ready"])
        self.assertIn("Workspace kind mismatch", result["failures"][0])

    def test_workspace_cannot_relax_release_budget(self) -> None:
        workspace = self.work / "expensive-prop"
        workspace.mkdir()
        (workspace / "state.json").write_text("{}", encoding="utf-8")
        (workspace / "intake.json").write_text(json.dumps({
            "budgets": {"maximum_vertices": 50_000, "maximum_triangles": 100_000},
        }), encoding="utf-8")
        manifest = self.write_manifest([{
            "asset_id": "expensive-prop",
            "asset_kind": "static_prop",
            "workspace": "expensive-prop",
            "maximum_vertices": 15_000,
            "maximum_triangles": 20_000,
        }])
        with patch("reference_asset_compiler.cohort.audit_workspace", return_value={
            "asset_id": "expensive-prop",
            "asset_kind": "static_prop",
            "ok": True,
            "production_ready": True,
            "failures": [],
            "stages": {"cook": "passed"},
        }):
            result = audit_cohort(manifest, self.work)
        self.assertFalse(result["production_ready"])
        self.assertTrue(any("budget exceeds" in row for row in result["failures"]))


if __name__ == "__main__":
    unittest.main()
