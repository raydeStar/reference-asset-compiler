"""promote_stage must not overwrite, advance over tampered evidence, or race itself."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from reference_asset_compiler import cli
from reference_asset_compiler.contracts import AUTOMATION_REVIEWERS
from reference_asset_compiler.io import read_json, sha256_file
from reference_asset_compiler.workspace import (
    STATE_LOCK_NAME,
    _state_lock,
    audit_workspace,
    create_workspace,
    promote_stage,
    validate_passed_stage_contract,
)
from reference_asset_compiler import approvals, delegated_review, workspace
from support import (
    modeling_evidence,
    promote_cleanup,
    promote_generated,
    promote_retopology,
    promote_texture_approval,
    promote_unwrap_and_bake,
    texture_payload_evidence,
    write_texture_payload,
    write_uv_transport,
)

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text(encoding="utf-8"))


class PromotionGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.reference = self.root / "source.png"
        self.reference.write_bytes(b"deterministic-reference-image")
        self.job = create_workspace(
            self.root / "work", self.reference, "Test Prop", "static_prop", "static", REGISTRY)

    def test_passed_stage_cannot_be_overwritten_without_replace(self) -> None:
        candidate, report = promote_generated(self.job)
        before = read_json(self.job / "state.json")["stages"]["generate_candidates"]
        with self.assertRaisesRegex(ValueError, "already passed"):
            promote_stage(self.job, "generate_candidates", [candidate, report],
                          "Second opinion.", "compile_from_image.py")
        with self.assertRaisesRegex(ValueError, "already passed"):
            promote_stage(self.job, "generate_candidates", [], "Retract.",
                          "compile_from_image.py", "rejected")
        self.assertEqual(before, read_json(self.job / "state.json")["stages"]["generate_candidates"])
        self.assertEqual([], list((self.job / "validation").glob("ledger-before-*")))

    def test_replace_snapshots_the_prior_record_first(self) -> None:
        candidate, report = promote_generated(self.job)
        before = read_json(self.job / "state.json")["stages"]["generate_candidates"]
        state = promote_stage(self.job, "generate_candidates", [candidate, report],
                              "Re-recorded with the same lineage.", "compile_from_image.py",
                              replace=True)
        snapshots = list((self.job / "validation").glob("ledger-before-generate_candidates-*.json"))
        self.assertEqual(1, len(snapshots))
        snapshot = read_json(snapshots[0])
        self.assertEqual(before, snapshot["record"])
        self.assertEqual("generate_candidates", snapshot["stage"])
        self.assertEqual("Re-recorded with the same lineage.",
                         state["stages"]["generate_candidates"]["note"])

    def test_cli_exposes_replace(self) -> None:
        candidate, report = promote_generated(self.job)
        argv = ["promote", str(self.job), "generate_candidates",
                "--evidence", str(candidate), "--evidence", str(report),
                "--note", "Again.", "--approved-by", "compile_from_image.py"]
        self.assertEqual(2, cli.main(argv))
        self.assertEqual(0, cli.main([*argv, "--replace"]))

    def test_tampered_earlier_evidence_blocks_any_promotion(self) -> None:
        candidate, _ = promote_generated(self.job)
        candidate.write_bytes(b"swapped after approval")
        with self.assertRaisesRegex(ValueError, "Evidence hash changed"):
            promote_stage(self.job, "modeling_approval", [], "Working on it.", "Ayric",
                          "in_progress")
        self.assertEqual("pending",
                         read_json(self.job / "state.json")["stages"]["modeling_approval"]["status"])

    def test_state_lock_file_is_created_and_released(self) -> None:
        promote_generated(self.job)
        lock = self.job / STATE_LOCK_NAME
        self.assertTrue(lock.is_file())
        with _state_lock(self.job):
            pass
        with _state_lock(self.job):
            pass
        self.assertTrue(audit_workspace(self.job)["ok"])

    def test_failed_plan_leaves_no_workspace_and_retry_succeeds(self) -> None:
        root = self.root / "fresh"
        with self.assertRaisesRegex(ValueError, "Unknown model adapters"):
            create_workspace(root, self.reference, "Bad Adapter", "static_prop", "static",
                             REGISTRY, candidate_adapters=["not-registered"])
        self.assertFalse(root.exists())
        job = create_workspace(root, self.reference, "Bad Adapter", "static_prop", "static",
                               REGISTRY)
        self.assertTrue((job / "state.json").is_file())
        self.assertTrue(audit_workspace(job)["ok"])

    def test_missing_candidate_hash_cannot_match_a_missing_lineage_hash(self) -> None:
        mesh = self.root / "mesh.glb"
        mesh.write_bytes(b"mesh")
        lineage = self.root / "lineage.json"
        lineage.write_text(json.dumps({
            "schema": "reference-asset-compiler.modeling-derivative-lineage.v1",
            "ok": True,
            "modeling_candidate_sha256": sha256_file(mesh),
            "operations": ["direct_ai_candidate"],
            "derivation_artifacts": [],
        }), encoding="utf-8")
        views = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = self.root / name
            path.write_bytes(name.encode())
            views.append(path)
        with self.assertRaisesRegex(ValueError, "does not begin at the ledger AI candidate"):
            validate_passed_stage_contract(
                "modeling_approval", [mesh, lineage, *views], "Approved.", "Ayric",
                generated_candidate_sha256=None)

    def test_reviewer_allow_list_is_defined_once(self) -> None:
        self.assertIs(AUTOMATION_REVIEWERS, workspace.AUTOMATION_REVIEWERS)
        self.assertIs(AUTOMATION_REVIEWERS, approvals.AUTOMATION_REVIEWERS)
        self.assertTrue(delegated_review.DELEGATED_REVIEWERS <= AUTOMATION_REVIEWERS)


class TextureAndStaticGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        reference = self.root / "source.png"
        reference.write_bytes(b"source")
        self.job = create_workspace(
            self.root / "work", reference, "Test Prop", "static_prop", "static", REGISTRY)
        candidate, _ = promote_generated(self.job)
        views = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = self.job / "modeling" / name
            path.write_bytes(name.encode())
            views.append(path)
        promote_stage(self.job, "modeling_approval", modeling_evidence(self.job, candidate, views),
                      "Approved.", "Ayric")
        cleaned = promote_cleanup(self.job, candidate)
        self.retopology = promote_retopology(self.job, cleaned)

    def test_unwrap_and_bake_requires_retopo_json_and_a_map(self) -> None:
        uv_blend, report = write_uv_transport(self.job, self.retopology)
        prod, retopo = write_texture_payload(self.job, uv_blend)
        maps = [prod / file for file in retopo["baked"].values()]
        with self.assertRaisesRegex(ValueError, "at least one baked PNG"):
            promote_stage(self.job, "unwrap_and_bake", [uv_blend, report, prod / "retopo.json"],
                          "Mechanical pass.", "crank_from_image.py")
        with self.assertRaisesRegex(ValueError, "exactly one retopo.json"):
            promote_stage(self.job, "unwrap_and_bake", [uv_blend, report, *maps],
                          "Mechanical pass.", "crank_from_image.py")
        state = promote_stage(self.job, "unwrap_and_bake",
                              [uv_blend, report, prod / "retopo.json", *maps],
                              "Mechanical pass.", "crank_from_image.py")
        self.assertEqual("passed", state["stages"]["unwrap_and_bake"]["status"])

    def test_replacing_an_upstream_pass_cannot_invalidate_downstream_approvals(self):
        before = (self.job / "state.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "invalidate downstream"):
            promote_stage(self.job, "semantic_cleanup", [], "Retracted.", "Ayric",
                          status="rejected", replace=True)
        self.assertEqual(before, (self.job / "state.json").read_bytes())
        self.assertEqual([], list((self.job / "validation").glob("ledger-before-*")))

    def test_unwrap_and_bake_rejects_a_payload_without_a_uv_authority_hash(self) -> None:
        uv_blend, report = write_uv_transport(self.job, self.retopology)
        prod, retopo = write_texture_payload(self.job, uv_blend)
        payload = json.loads((prod / "retopo.json").read_text(encoding="utf-8"))
        del payload["source_uv_authority_sha256"]
        (prod / "retopo.json").write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source_uv_authority_sha256"):
            promote_stage(self.job, "unwrap_and_bake",
                          [uv_blend, report, prod / "retopo.json",
                           *(prod / file for file in retopo["baked"].values())],
                          "Mechanical pass.", "build_production.py")

    def test_texture_approval_rejects_a_failed_texture_gate(self) -> None:
        _, baked = promote_unwrap_and_bake(self.job, self.retopology)
        prod, retopo = write_texture_payload(
            self.job, Path(baked["source_uv_authority"]), name="prod-v3", gate_ok=False)
        with self.assertRaisesRegex(ValueError, "gate-tex.json does not record ok"):
            promote_stage(self.job, "texture_approval", texture_payload_evidence(prod, retopo),
                          "Looks fine to me.", "Ayric")

    def test_retained_unwrap_evidence_cannot_be_edited_under_a_later_approval(self) -> None:
        prod, retopo = promote_unwrap_and_bake(self.job, self.retopology)
        (prod / "gate-tex.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Evidence hash changed for unwrap_and_bake"):
            promote_stage(self.job, "texture_approval", texture_payload_evidence(prod, retopo),
                          "Approved.", "Ayric")

    def test_texture_approval_rejects_a_payload_from_another_mesh(self) -> None:
        promote_unwrap_and_bake(self.job, self.retopology)
        stranger = self.root / "stranger.blend"
        stranger.write_bytes(b"a mesh nobody approved")
        prod, retopo = write_texture_payload(self.job, stranger, name="prod-v3")
        with self.assertRaisesRegex(ValueError, "does not derive from the approved"):
            promote_stage(self.job, "texture_approval", texture_payload_evidence(prod, retopo),
                          "Approved.", "Ayric")

    def test_texture_approval_accepts_the_uv_transport_chain(self) -> None:
        prod, retopo, evidence = promote_texture_approval(self.job, self.retopology)
        record = read_json(self.job / "state.json")["stages"]["texture_approval"]
        self.assertEqual("passed", record["status"])
        self.assertEqual({sha256_file(path) for path in evidence},
                         {row["sha256"] for row in record["evidence"]})
        self.assertTrue(audit_workspace(self.job)["ok"])

    def test_texture_approval_rejects_an_unrelated_export_with_the_expected_name(self) -> None:
        promote_unwrap_and_bake(self.job, self.retopology)
        prod, retopo = write_texture_payload(self.job, self.retopology, name="prod-other")
        evidence = texture_payload_evidence(prod, retopo)
        (prod / retopo["output_fbx"]).write_bytes(b"an entirely different mesh")
        with self.assertRaisesRegex(ValueError, "does not bind the retained file"):
            promote_stage(self.job, "texture_approval", evidence, "Approved.", "Ayric")

    def test_texture_approval_rejects_a_substituted_passing_gate(self) -> None:
        promote_unwrap_and_bake(self.job, self.retopology)
        prod, retopo = write_texture_payload(self.job, self.retopology, name="prod-other")
        evidence = texture_payload_evidence(prod, retopo)
        (prod / "gate-tex.json").write_text('{"ok": true}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not bind the retained file"):
            promote_stage(self.job, "texture_approval", evidence, "Approved.", "Ayric")

    def test_unwrap_rejects_a_replaced_baked_map(self) -> None:
        prod, retopo = write_texture_payload(self.job, self.retopology)
        maps = [prod / name for name in retopo["baked"].values()]
        maps[0].write_bytes(b"maps from a different paint attempt")
        with self.assertRaisesRegex(ValueError, "does not bind the retained file"):
            promote_stage(self.job, "unwrap_and_bake", [prod / "retopo.json", *maps],
                          "Mechanical pass.", "build_production.py")

    def test_delegated_texture_review_is_accepted_by_ledger_and_approval_check_alike(self) -> None:
        prod, retopo = promote_unwrap_and_bake(self.job, self.retopology)
        evidence = texture_payload_evidence(prod, retopo)
        source_hash = read_json(self.job / "intake.json")["source"]["sha256"]
        authorization = self.job / "review-delegation.json"
        authorization.write_text(json.dumps({
            "schema": delegated_review.AUTH_SCHEMA, "authorized_by": "Ayric", "reviewer": "codex",
            "source_sha256": source_hash, "stages": ["texture_approval"],
            "mechanical_gates_waived": False,
            "user_instruction": "Judge the lit views yourself and record what you saw.",
        }), encoding="utf-8")
        paths = delegated_review.record_delegated_review(
            prod / "delegated-review.json", authorization, "codex", source_hash,
            "texture_approval", evidence, "All four lit views match the reference palette.")
        promote_stage(self.job, "texture_approval", paths, "Delegated review recorded.", "codex")
        record = approvals.validate_texture_approval(self.job, prod, retopo)
        self.assertEqual("codex", record["approved_by"])
        self.assertTrue(audit_workspace(self.job)["ok"])

    def static_manifest(self, **changes) -> tuple[Path, list[Path]]:
        published = self.root / "out" / "test-prop-production"
        (published / "textures").mkdir(parents=True, exist_ok=True)
        fbx = published / "test-prop-production.fbx"
        fbx.write_bytes(b"fbx")
        texture = published / "textures" / "base.png"
        texture.write_bytes(b"texture")
        manifest = published / "test-prop-production.ue5import.json"
        payload = {
            "asset_id": "test-prop-production", "asset_kind": "static_prop",
            "fbx": fbx.name, "fbx_sha256": sha256_file(fbx).upper(),
            "textures": {"M_Test": {"BaseColor": {"file": "textures/base.png"}}},
            "ue5_import": {"generate_collision": False},
        }
        payload.update(changes)
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        return manifest, [manifest, fbx, texture]

    def test_static_stages_require_the_declared_manifest_contract(self) -> None:
        manifest, payloads = self.static_manifest()
        validate_passed_stage_contract("collision_optional", [manifest], "Declared.",
                                       "promote_production.py")
        validate_passed_stage_contract("static_validation", payloads, "Published.",
                                       "promote_production.py")
        with self.assertRaisesRegex(ValueError, "not retained as hash-bound"):
            validate_passed_stage_contract("static_validation", payloads[:2], "Published.",
                                           "promote_production.py")
        manifest, payloads = self.static_manifest(ue5_import={})
        with self.assertRaisesRegex(ValueError, "generate_collision"):
            validate_passed_stage_contract("collision_optional", [manifest], "Declared.",
                                           "promote_production.py")
        manifest, payloads = self.static_manifest(fbx_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "fbx_sha256 disagrees"):
            validate_passed_stage_contract("static_validation", payloads, "Published.",
                                           "promote_production.py")
        with self.assertRaisesRegex(ValueError, "ue5import.json"):
            validate_passed_stage_contract("collision_optional", payloads[1:], "Declared.",
                                           "promote_production.py")


if __name__ == "__main__":
    unittest.main()
