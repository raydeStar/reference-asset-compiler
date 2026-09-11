from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from reference_asset_compiler.cohort import audit_cohort
from reference_asset_compiler.io import read_json, write_json
from reference_asset_compiler.workspace import create_workspace, promote_stage
from support import promote_generated

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text(encoding="utf-8"))


class CohortAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        self.work.mkdir()
        self.reference = self.root / "source.png"
        self.reference.write_bytes(b"reference")

    def write_manifest(self, members: list[dict]) -> Path:
        path = self.root / "cohort.json"
        path.write_text(json.dumps({
            "schema": "reference-asset-compiler.cohort.v1",
            "cohort_id": "test-cohort",
            "members": members,
        }), encoding="utf-8")
        return path

    def workspace(self, asset_id: str, kind: str = "static_prop", **budgets) -> Path:
        return create_workspace(self.work, self.reference, asset_id, kind,
                                "static" if kind == "static_prop" else "required",
                                REGISTRY, skeleton_profile="ue5_manny", **budgets)

    def member(self, asset_id: str, kind: str = "static_prop", **extra) -> dict:
        return {"asset_id": asset_id, "asset_kind": kind, "workspace": asset_id, **extra}

    def test_missing_workspace_fails_closed(self) -> None:
        manifest = self.write_manifest([self.member("missing-prop")])
        result = audit_cohort(manifest, self.work)
        self.assertFalse(result["production_ready"])
        self.assertEqual(1, result["summary"]["incomplete_assets"])
        self.assertIn("Missing workspace", result["failures"][0])

    def test_real_incomplete_workspace_reports_unresolved_stages(self) -> None:
        job = self.workspace("crate")
        promote_generated(job)
        manifest = self.write_manifest([self.member("crate")])
        result = audit_cohort(manifest, self.work)
        self.assertFalse(result["ok"])
        self.assertFalse(result["production_ready"])
        member = result["members"][0]
        self.assertTrue(member["audit"]["ok"])
        self.assertIn("modeling_approval", member["stage_summary"]["pending"])
        self.assertNotIn("generate_candidates", member["stage_summary"]["pending"])
        self.assertEqual([], member["stage_summary"]["rejected"])
        self.assertTrue(any("unresolved stages" in row for row in result["failures"]))
        self.assertFalse(any("mismatch" in row for row in result["failures"]))

    def test_rejected_stage_requires_replacement_evidence(self) -> None:
        job = self.workspace("hero", "humanoid")
        promote_generated(job)
        promote_stage(job, "modeling_approval", [], "Side view collapsed.", "Ayric", "rejected")
        manifest = self.write_manifest([self.member("hero", "humanoid")])
        result = audit_cohort(manifest, self.work)
        self.assertEqual(1, result["summary"]["rejected_assets"])
        self.assertEqual(["modeling_approval"], result["members"][0]["stage_summary"]["rejected"])
        self.assertTrue(any("requires replacement evidence" in row for row in result["failures"]))

    def test_broken_ledger_is_reported_as_the_asset_failure_not_an_identity_mismatch(self) -> None:
        job = self.workspace("broken")
        (job / "state.json").write_text("{}", encoding="utf-8")
        manifest = self.write_manifest([self.member("broken")])
        result = audit_cohort(manifest, self.work)
        self.assertFalse(result["ok"])
        failures = result["members"][0]["failures"]
        self.assertTrue(any("Cannot audit workspace" in row for row in failures), failures)
        self.assertFalse(any("mismatch" in row for row in failures), failures)

    def test_workspace_identity_must_match_manifest(self) -> None:
        self.workspace("wrong-kind")
        manifest = self.write_manifest([self.member("wrong-kind", "humanoid")])
        result = audit_cohort(manifest, self.work)
        self.assertTrue(any("Workspace kind mismatch" in row for row in result["failures"]))
        job = self.workspace("renamed")
        intake = read_json(job / "intake.json")
        for name in ("intake.json", "routing.json", "state.json"):
            payload = read_json(job / name)
            payload["asset_id"] = "someone-else"
            write_json(job / name, payload)
        self.assertEqual("renamed", intake["asset_id"])
        manifest = self.write_manifest([self.member("renamed")])
        result = audit_cohort(manifest, self.work)
        self.assertTrue(any("Workspace asset mismatch" in row for row in result["failures"]))

    def test_workspace_cannot_relax_release_budget(self) -> None:
        self.workspace("expensive-prop", maximum_vertices=50_000, maximum_triangles=100_000)
        manifest = self.write_manifest([self.member(
            "expensive-prop", maximum_vertices=15_000, maximum_triangles=20_000)])
        result = audit_cohort(manifest, self.work)
        self.assertFalse(result["production_ready"])
        self.assertTrue(any("budget exceeds" in row for row in result["failures"]))

    def test_duplicate_members_are_rejected(self) -> None:
        manifest = self.write_manifest([self.member("duplicate"), self.member("duplicate")])
        with self.assertRaisesRegex(ValueError, "Duplicate cohort asset_id"):
            audit_cohort(manifest, self.work)

    def test_workspace_cannot_escape_declared_root(self) -> None:
        manifest = self.write_manifest([{
            "asset_id": "escape", "asset_kind": "static_prop", "workspace": "../escape",
        }])
        with self.assertRaisesRegex(ValueError, "escapes workspace root"):
            audit_cohort(manifest, self.work)


if __name__ == "__main__":
    unittest.main()
