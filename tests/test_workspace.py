from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from reference_asset_compiler.io import read_json, sha256_file
from reference_asset_compiler.workspace import (
    audit_workspace,
    create_workspace,
    promote_stage,
    validate_passed_stage_contract,
)
from support import promote_generated  # noqa: E402

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text(encoding="utf-8"))


class WorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.reference = self.root / "source.png"
        self.reference.write_bytes(b"deterministic-reference-image")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_static_job(self) -> Path:
        return create_workspace(
            self.root / "work",
            self.reference,
            "Weathered Sword",
            "static_prop",
            "static",
            REGISTRY,
        )

    def test_new_workspace_copies_and_hashes_reference(self) -> None:
        job = self.create_static_job()
        intake = read_json(job / "intake.json")
        copied = job / intake["source"]["path"]
        self.assertEqual(self.reference.read_bytes(), copied.read_bytes())
        audit = audit_workspace(job)
        self.assertTrue(audit["ok"])
        self.assertFalse(audit["production_ready"])

    def test_source_tampering_fails_audit(self) -> None:
        job = self.create_static_job()
        intake = read_json(job / "intake.json")
        (job / intake["source"]["path"]).write_bytes(b"changed")
        audit = audit_workspace(job)
        self.assertFalse(audit["ok"])
        self.assertIn("Immutable source hash changed", audit["failures"])

    def test_stage_cannot_skip_unfinished_predecessor(self) -> None:
        job = self.create_static_job()
        evidence = job / "validation" / "front.png"
        evidence.write_bytes(b"review")
        with self.assertRaises(ValueError):
            promote_stage(
                job,
                "modeling_approval",
                [evidence],
                "Looks correct",
                "reviewer",
            )

    def test_evidence_hash_drift_fails_audit(self) -> None:
        job = self.create_static_job()
        generated, _ = promote_generated(job)
        generated.write_bytes(b"changed")
        audit = audit_workspace(job)
        self.assertFalse(audit["ok"])
        self.assertTrue(any("Evidence hash changed" in failure for failure in audit["failures"]))

    def test_passed_stage_requires_evidence(self) -> None:
        job = self.create_static_job()
        with self.assertRaisesRegex(ValueError, "without evidence"):
            promote_stage(job, "generate_candidates", [], "No proof.", "reviewer")

    def test_generic_modeling_promotion_cannot_use_token_evidence(self) -> None:
        job = self.create_static_job()
        _, generated = promote_generated(job)
        with self.assertRaisesRegex(ValueError, "mesh and four neutral views"):
            promote_stage(job, "modeling_approval", [generated], "Looks fine.", "reviewer")

    def test_modeling_mesh_cannot_substitute_for_ai_derivative_lineage(self) -> None:
        job = self.create_static_job()
        candidate, _ = promote_generated(job)
        views = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = job / "modeling" / name
            path.write_bytes(name.encode())
            views.append(path)
        with self.assertRaisesRegex(ValueError, "lineage from the AI candidate"):
            promote_stage(
                job, "modeling_approval", [candidate, *views],
                "Approved.", "Ayric")

    def test_human_gate_rejects_automation_identity(self) -> None:
        job = self.create_static_job()
        promote_generated(job)
        mesh = job / "modeling" / "candidate.fbx"
        mesh.write_bytes(b"mesh")
        views = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = job / "modeling" / name
            path.write_bytes(name.encode())
            views.append(path)
        with self.assertRaisesRegex(ValueError, "human reviewer"):
            promote_stage(job, "modeling_approval", [mesh, *views], "Approved.", "codex")

    def test_generation_rejects_token_evidence_without_ai_lineage(self) -> None:
        job = self.create_static_job()
        generated = job / "logs" / "candidate.json"
        generated.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "image-conditioned AI lineage"):
            promote_stage(job, "generate_candidates", [generated], "Candidate retained.", "system")

    def test_multiview_ai_lineage_binds_every_derived_input(self) -> None:
        job = self.create_static_job()
        intake = read_json(job / "intake.json")
        routing = read_json(job / "routing.json")
        candidate = job / "candidates" / "candidate.glb"
        candidate.write_bytes(b"multiview-ai-mesh")
        views = []
        for name in ("front.png", "side.png", "back.png"):
            path = job / "references" / name
            path.write_bytes(name.encode())
            views.append(path)
        split = job / "references" / "turnaround-split.json"
        split.write_text(json.dumps({
            "schema": "reference-studio.character-turnaround-split.v1",
            "source": str(self.reference),
            "source_sha256": intake["source"]["sha256"],
            "views": [
                {
                    "view": path.stem,
                    "output": str(path),
                    "sha256": sha256_file(path),
                }
                for path in views
            ],
        }), encoding="utf-8")
        report = job / "candidates" / "candidate.json"
        report.write_text(json.dumps({
            "schema": "reference-asset-compiler.geometry-candidate.v1",
            "asset_id": "Weathered Sword",
            "adapter": routing["geometry_candidates"][0],
            "ok": True,
            "candidate_sha256": sha256_file(candidate),
            "image_sha256": intake["source"]["sha256"],
            "source_image_sha256": intake["source"]["sha256"],
            "image_inputs": [
                {"view": path.stem, "sha256": sha256_file(path)} for path in views
            ],
            "image_derivation_report_sha256": sha256_file(split),
        }), encoding="utf-8")
        state = promote_stage(
            job, "generate_candidates", [candidate, report, split, *views],
            "Hash-bound multiview AI candidate retained.", "compile_from_image.py")
        self.assertEqual("passed", state["stages"]["generate_candidates"]["status"])

    def test_multiview_ai_lineage_rejects_unrelated_split_report(self) -> None:
        job = self.create_static_job()
        intake = read_json(job / "intake.json")
        routing = read_json(job / "routing.json")
        candidate = job / "candidates" / "candidate.glb"
        candidate.write_bytes(b"multiview-ai-mesh")
        views = []
        for name in ("front.png", "side.png", "back.png"):
            path = job / "references" / name
            path.write_bytes(name.encode())
            views.append(path)
        split = job / "references" / "turnaround-split.json"
        split.write_text("{}", encoding="utf-8")
        report = job / "candidates" / "candidate.json"
        report.write_text(json.dumps({
            "schema": "reference-asset-compiler.geometry-candidate.v1",
            "asset_id": "Weathered Sword",
            "adapter": routing["geometry_candidates"][0],
            "ok": True,
            "candidate_sha256": sha256_file(candidate),
            "source_image_sha256": intake["source"]["sha256"],
            "image_inputs": [
                {"view": path.stem, "sha256": sha256_file(path)} for path in views
            ],
            "image_derivation_report_sha256": sha256_file(split),
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "derivation report"):
            promote_stage(
                job, "generate_candidates", [candidate, report, split, *views],
                "This report is unrelated.", "compile_from_image.py")

    def test_hollow_ue_receipt_is_not_proof(self) -> None:
        manifest = self.root / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        receipt = self.root / "ue5-import.json"
        receipt.write_text(json.dumps({
            "schema": "reference-asset-compiler.ue5-import-evidence.v1",
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not bound|successful native checks"):
            validate_passed_stage_contract(
                "ue5_import", [receipt, manifest], "Imported.", "record_ue5_import.py"
            )

    def test_hollow_runtime_review_receipt_is_not_proof(self) -> None:
        receipt = self.root / "ue5-runtime-review.json"
        receipt.write_text(json.dumps({
            "schema": "reference-asset-compiler.ue5-runtime-review.v1",
            "status": "approved",
            "approved_by": "Ayric",
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not bound|human-reviewed frame"):
            validate_passed_stage_contract(
                "ue5_runtime_review", [receipt], "Reviewed.", "Ayric"
            )

    def test_hollow_cook_receipt_is_not_proof(self) -> None:
        receipt = self.root / "cooked-runtime.json"
        receipt.write_text(json.dumps({
            "schema": "reference-asset-compiler.cooked-runtime-evidence.v1",
            "ok": True,
            "approved_by": "Ayric",
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not bound|packaged-runtime proof"):
            validate_passed_stage_contract("cook", [receipt], "Cooked.", "Ayric")

    def test_articulated_receipt_names_alone_are_not_proof(self) -> None:
        cases = (
            ("rig_and_skin", "reference-asset-compiler.rig-and-skin-evidence.v1",
             "profile-bound|not bound"),
            ("deformation_validation", "reference-asset-compiler.deformation-evidence.v1",
             "pose-suite|not bound"),
            ("ue5_motion_review", "reference-asset-compiler.ue5-motion-review.v1",
             "native motion|not bound"),
        )
        for stage, schema, message in cases:
            with self.subTest(stage=stage):
                receipt = self.root / (stage + ".json")
                receipt.write_text(json.dumps({"schema": schema}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    validate_passed_stage_contract(stage, [receipt], "Passed.", "Ayric")

    def test_cook_rejects_automation_identity(self) -> None:
        receipt = self.root / "cooked-runtime.json"
        receipt.write_text(json.dumps({
            "schema": "reference-asset-compiler.cooked-runtime-evidence.v1",
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "human reviewer"):
            validate_passed_stage_contract("cook", [receipt], "Cooked.", "codex")


if __name__ == "__main__":
    unittest.main()
