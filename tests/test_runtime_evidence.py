from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from reference_asset_compiler.io import sha256_file  # noqa: E402
from reference_asset_compiler.runtime_evidence import (  # noqa: E402
    extract_ue5_import_record,
    record_cook_stage,
    record_runtime_review_stage,
    record_static_publish_stages,
    record_ue5_import_stage,
    record_native_import_revision,
)
from reference_asset_compiler.workspace import create_workspace, promote_stage  # noqa: E402
from support import (  # noqa: E402
    modeling_evidence,
    promote_cleanup,
    promote_generated,
    promote_retopology,
)

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text())


class RuntimeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "source.png"
        source.write_bytes(b"source")
        self.job = create_workspace(
            self.root / "work", source, "Test Prop", "static_prop", "static", REGISTRY
        )
        candidate, _ = promote_generated(self.job)
        evidence = self.job / "logs" / "stage.json"
        evidence.write_text("{}")
        modeling_views = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = self.job / "modeling" / name
            path.write_bytes(name.encode())
            modeling_views.append(path)
        modeling = modeling_evidence(self.job, candidate, modeling_views)
        promote_stage(self.job, "modeling_approval", modeling, "Approved.", "Ayric")
        cleaned = promote_cleanup(self.job, candidate)
        promote_retopology(self.job, cleaned)
        promote_stage(self.job, "unwrap_and_bake", [evidence], "Passed.", "system")
        texture_dir = self.job / "textures"
        texture_evidence = []
        for name in ("prop_production.fbx", "retopo.json", "gate-tex.json", "base.png",
                     "beauty-front.png", "beauty-three-quarter.png",
                     "beauty-side.png", "beauty-back.png"):
            path = texture_dir / name
            path.write_bytes(name.encode())
            texture_evidence.append(path)
        promote_stage(self.job, "texture_approval", texture_evidence, "Approved.", "Ayric")

        self.published = self.root / "out" / "test-prop-production"
        (self.published / "textures").mkdir(parents=True)
        self.fbx = self.published / "test-prop-production.fbx"
        self.texture = self.published / "textures" / "base.png"
        self.fbx.write_bytes(b"fbx")
        self.texture.write_bytes(b"texture")
        self.manifest = self.published / "test-prop-production.ue5import.json"
        self.manifest.write_text(json.dumps({
            "asset_id": "test-prop-production",
            "asset_kind": "static_prop",
            "fbx": self.fbx.name,
            "textures": {"M_Test": {"BaseColor": {"file": "textures/base.png"}}},
            "ue5_import": {"generate_collision": True},
        }))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def batch_report(self, manifest_hash: str | None = None, ok: bool = True) -> Path:
        report = self.root / "ue5-verify.json"
        report.write_text(json.dumps({
            "engine_version": "5.8.2-test",
            "assets": [{
                "asset_id": "test-prop-production",
                "mesh": "/Game/Source/Board",
                "manifest_sha256": manifest_hash or sha256_file(self.manifest),
                "checks": [{"check": "mesh_exists", "ok": ok}],
                "ok": ok,
            }],
        }))
        return report

    def test_static_publish_advances_two_mechanical_stages(self) -> None:
        state = record_static_publish_stages(self.job, self.manifest)
        self.assertEqual("passed", state["stages"]["collision_optional"]["status"])
        self.assertEqual("passed", state["stages"]["static_validation"]["status"])

    def test_import_record_is_manifest_bound_and_immutable(self) -> None:
        record_static_publish_stages(self.job, self.manifest)
        output = record_ue5_import_stage(self.job, self.manifest, self.batch_report())
        payload = json.loads(output.read_text())
        self.assertTrue(payload["ok"])
        self.assertEqual(sha256_file(self.manifest), payload["manifest_sha256"])

    def test_manifest_hash_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not bound"):
            extract_ue5_import_record(self.manifest, self.batch_report("0" * 64))

    def native_report(self, vertices=14534):
        self.advance_through_import()
        artifacts = []
        for name, mesh in (("source", "/Game/Source/Board"), ("candidate", "/Game/Reduced/Board")):
            path = self.root / (name + ".uasset")
            path.write_bytes(name.encode())
            artifacts.append({"path": str(path), "sha256": sha256_file(path), "mesh": mesh})
        transform = self.root / "reduction.json"
        transform.write_text(json.dumps({
            "schema": "reference-asset-compiler.native-lod-reduction.v1",
            "source_mesh": "/Game/Source/Board", "candidate_mesh": "/Game/Reduced/Board",
            "triangle_fractions": [.85], "original_asset_preserved": True}))
        derivative = {
            "source_mesh": "/Game/Source/Board", "candidate_mesh": "/Game/Reduced/Board",
            "source_manifest_sha256": sha256_file(self.manifest),
            "operation": "native_lod_reduction", "triangle_fractions": [.85],
            "material_interfaces_identical": True, "material_interfaces": [["M"], ["M"]],
            "native_files": artifacts,
            "artifacts": [{"path": str(transform), "sha256": sha256_file(transform)}]}
        report = self.root / "native-report.json"
        report.write_text(json.dumps({"engine_version": "5.8.2-test", "native_derivative": derivative,
            "assets": [{"asset_id": "test-prop-production", "mesh": "/Game/Reduced/Board",
                "manifest_sha256": sha256_file(self.manifest), "lod_count": 1,
                "native_lods": [{"lod": 0, "vertices": vertices, "triangles": 15300}],
                "checks": [{"check": key, "ok": True} for key in (
                    "import_scale", "materials_assigned", "materials_textured", "lods",
                    "native_runtime_budget", "texture_settings", "derivative_material_identity")],
                "ok": True}]}))
        return report

    def test_native_revision_preserves_original_and_downstream_hold(self):
        report = self.native_report()
        old = self.job / "validation/ue5-import.json"
        old_hash = sha256_file(old)
        promote_stage(self.job, "ue5_runtime_review", [report], "Original over budget.", "pipeline", "blocked")
        output = record_native_import_revision(self.job, self.manifest, report, "native-v2")
        self.assertEqual(old_hash, sha256_file(old))
        self.assertTrue(output.is_file())
        self.assertTrue((self.job / "validation/ledger-before-native-v2.json").is_file())
        state = json.loads((self.job / "state.json").read_text())
        self.assertEqual("blocked", state["stages"]["ue5_runtime_review"]["status"])
        from reference_asset_compiler.workspace import audit_workspace
        self.assertTrue(audit_workspace(self.job)["ok"])
        (self.root / "candidate.uasset").write_bytes(b"changed")
        self.assertFalse(audit_workspace(self.job)["ok"])

    def test_native_revision_checks_counts_even_when_report_claims_pass(self):
        report = self.native_report(vertices=15973)
        with self.assertRaisesRegex(ValueError, "runtime budgets"):
            record_native_import_revision(self.job, self.manifest, report, "native-v2")
        self.assertFalse((self.job / "validation/ue5-import-native-v2.json").exists())

    def test_native_revision_refuses_unbound_mesh(self):
        report = self.native_report()
        (self.root / "candidate.uasset").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "missing or changed"):
            record_native_import_revision(self.job, self.manifest, report, "native-v2")

    def test_native_revision_refuses_wrong_transform_destination(self):
        report = self.native_report()
        transform = self.root / "reduction.json"
        payload = json.loads(transform.read_text())
        payload["candidate_mesh"] = "/Game/Unrelated"
        transform.write_text(json.dumps(payload))
        batch = json.loads(report.read_text())
        batch["native_derivative"]["artifacts"][0]["sha256"] = sha256_file(transform)
        report.write_text(json.dumps(batch))
        with self.assertRaisesRegex(ValueError, "different mesh"):
            record_native_import_revision(self.job, self.manifest, report, "native-v2")

    def test_native_revision_refuses_passed_downstream(self):
        report = self.native_report()
        record_runtime_review_stage(self.job, self.manifest, self.gallery_report(),
                                    self.make_frame("reviewed.png"), "Ayric", "Reviewed.")
        with self.assertRaisesRegex(ValueError, "downstream"):
            record_native_import_revision(self.job, self.manifest, report, "native-v2")

    def matched_native_review(self):
        report = self.native_report()
        record_native_import_revision(self.job, self.manifest, report, "native-v2")
        frames = []
        for view in range(2):
            for kind, mesh in (("original", "/Game/Source/Board"), ("reduced", "/Game/Reduced/Board")):
                path = self.make_frame("view-{0}-{1}.png".format(view, kind))
                frames.append({"path": str(path.resolve()), "sha256": sha256_file(path),
                    "mesh": mesh, "forced_lod_model": 1, "camera_position": [view, 1, 2],
                    "camera_pitch_yaw": [0, 0], "actor_position": [0, 0, 0]})
        gallery = self.root / "matched.json"
        gallery.write_text(json.dumps({
            "schema": "reference-asset-compiler.ue-native-matched-review.v1",
            "error": None, "forced_lod_model": 1, "level": "/Game/Fixture",
            "assets": {"original": {"path": "/Game/Source/Board"}, "reduced": {
                "path": "/Game/Reduced/Board", "lod0_vertices": 14534}}, "frames": frames}))
        return gallery, Path(frames[1]["path"])

    def test_delegated_native_runtime_review_binds_all_matched_frames(self):
        gallery, frame = self.matched_native_review()
        auth = self.root / "authorization.json"
        intake = json.loads((self.job / "intake.json").read_text())
        auth.write_text(json.dumps({"schema": "reference-asset-compiler.review-delegation.v1",
            "authorized_by": "Ayric", "reviewer": "codex", "user_instruction": "Judge it yourself",
            "source_sha256": intake["source"]["sha256"], "stages": ["ue5_runtime_review"],
            "mechanical_gates_waived": False}))
        output = record_runtime_review_stage(self.job, self.manifest, gallery, frame,
                                            "codex", "Inspected both pairs.", authorization=auth)
        self.assertFalse(json.loads(output.read_text())["human_visual_review"])
        from reference_asset_compiler.workspace import audit_workspace
        self.assertTrue(audit_workspace(self.job)["ok"])
        frame.write_bytes(b"changed")
        self.assertFalse(audit_workspace(self.job)["ok"])

    def test_native_runtime_review_refuses_unmatched_camera_pair(self):
        gallery, frame = self.matched_native_review()
        payload = json.loads(gallery.read_text())
        payload["frames"][1]["camera_position"] = [99, 0, 0]
        gallery.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "camera pair"):
            record_runtime_review_stage(self.job, self.manifest, gallery, frame, "Ayric", "Reviewed.")
        self.assertFalse((self.job / "validation/ue5-runtime-review.json").exists())

    def test_failed_native_check_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "failed checks"):
            extract_ue5_import_record(self.manifest, self.batch_report(ok=False))

    def advance_through_import(self) -> None:
        record_static_publish_stages(self.job, self.manifest)
        record_ue5_import_stage(self.job, self.manifest, self.batch_report())

    def make_frame(self, name: str) -> Path:
        path = self.root / name
        image = Image.new("RGB", (800, 450), (48, 96, 144))
        image.paste((180, 120, 60), (400, 0, 800, 450))
        image.save(path)
        return path

    def gallery_report(self, placed: bool = True) -> Path:
        path = self.root / "gallery.json"
        asset = "/Game/Compiled/TestPropProduction/test-prop-production"
        path.write_text(json.dumps({"level": "/Game/Compiled/L_RacGallery",
                                    "placed": [{"asset": asset}] if placed else []}))
        return path

    def test_runtime_review_requires_asset_placement(self) -> None:
        self.advance_through_import()
        with self.assertRaisesRegex(ValueError, "does not place"):
            record_runtime_review_stage(
                self.job, self.manifest, self.gallery_report(False),
                self.make_frame("editor.png"), "Ayric", "Reviewed.")

    def static_multiview_fixture(self):
        record_static_publish_stages(self.job, self.manifest)
        batch = self.batch_report()
        data = json.loads(batch.read_text())
        lods = [{"lod": 0, "vertices": 900, "triangles": 1500, "sections": 1}]
        data["assets"][0]["native_lods"] = lods
        batch.write_text(json.dumps(data))
        imported = record_ue5_import_stage(self.job, self.manifest, batch)
        rows = []
        for name, camera in zip(("front", "three-quarter", "side", "back"),
                                ((0, -10, 2), (7, -7, 2), (10, 0, 2), (0, 10, 2))):
            frame = self.make_frame(name + ".png")
            rows.append({"name": name, "path": str(frame), "sha256": sha256_file(frame),
                         "mesh": "/Game/Source/Board", "camera_position": camera,
                         "camera_target": [0, 0, 2], "forced_lod_model": 1})
        gallery = self.root / "static-multiview.json"
        gallery.write_text(json.dumps({
            "schema": "reference-asset-compiler.ue-static-multiview-review.v1",
            "error": None, "level_saved": True,
            "manifest_sha256": sha256_file(self.manifest),
            "import_receipt_sha256": sha256_file(imported),
            "placed": [{"asset": "/Game/Source/Board"}], "native_lods": lods,
            "frames": rows,
        }))
        return gallery, Path(rows[0]["path"])

    def test_static_multiview_retains_all_frames_and_audits_changes(self):
        from reference_asset_compiler.workspace import audit_workspace
        gallery, front = self.static_multiview_fixture()
        output = record_runtime_review_stage(self.job, self.manifest, gallery, front,
                                             "Ayric", "Reviewed all four static views.")
        self.assertIn("static_multiview_import_sha256", json.loads(output.read_text()))
        self.assertTrue(audit_workspace(self.job)["ok"])
        (self.root / "back.png").write_bytes(b"changed after approval")
        self.assertFalse(audit_workspace(self.job)["ok"])

    def test_static_multiview_refuses_missing_or_unrelated_evidence(self):
        gallery, front = self.static_multiview_fixture()
        original = json.loads(gallery.read_text())
        cases = [
            ("missing side", lambda d: d["frames"].pop(2)),
            ("wrong mesh", lambda d: d["frames"][1].update(mesh="/Game/Wrong")),
            ("invented LOD", lambda d: d["frames"][1].update(forced_lod_model=7)),
            ("wrong import", lambda d: d.update(import_receipt_sha256="0" * 64)),
            ("failed capture", lambda d: d.update(error="timeout")),
            ("duplicate path", lambda d: d["frames"][1].update(path=d["frames"][0]["path"])),
            ("duplicate camera", lambda d: d["frames"][1].update(camera_position=d["frames"][0]["camera_position"])),
            ("changed counts", lambda d: d["native_lods"][0].update(vertices=901)),
        ]
        for name, mutate in cases:
            with self.subTest(name=name):
                data = json.loads(json.dumps(original))
                mutate(data)
                gallery.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    record_runtime_review_stage(self.job, self.manifest, gallery, front,
                                                "Ayric", "Invalid capture must not advance.")
                self.assertFalse((self.job / "validation/ue5-runtime-review.json").exists())

    def test_static_multiview_rejects_unbound_primary_frame(self):
        gallery, _ = self.static_multiview_fixture()
        with self.assertRaisesRegex(ValueError, "not a bound"):
            record_runtime_review_stage(self.job, self.manifest, gallery,
                self.make_frame("unrelated.png"), "Ayric", "Must be actual bound frame.")

    def test_automation_reviewer_is_rejected_before_receipt_write(self) -> None:
        self.advance_through_import()
        with self.assertRaisesRegex(ValueError, "human reviewer"):
            record_runtime_review_stage(
                self.job, self.manifest, self.gallery_report(),
                self.make_frame("editor.png"), "codex", "Reviewed.")
        self.assertFalse((self.job / "validation" / "ue5-runtime-review.json").exists())

    def test_clean_packaged_runtime_completes_workspace(self) -> None:
        self.advance_through_import()
        gallery = self.gallery_report()
        record_runtime_review_stage(
            self.job, self.manifest, gallery, self.make_frame("editor.png"),
            "Ayric", "Reviewed imported runtime.")
        cook = self.root / "cook.log"
        package = self.root / "package.log"
        runtime = self.root / "runtime.log"
        package_root = self.root / "package"
        package_root.mkdir()
        cook.write_text("LogCook: Display: Done!\nLogInit: Display: Success - 0 error(s), 0 warning(s)")
        package.write_text("Success - 0 error(s), 0 warning(s)\nBUILD SUCCESSFUL\n{0}".format(
            package_root.resolve()))
        runtime.write_text("Load map complete /Game/Compiled/L_RacGallery")
        frame = self.make_frame("packaged.png")
        (package_root / "Game.exe").write_bytes(b"exe")
        (package_root / "Game.pak").write_bytes(b"pak")
        output, audit = record_cook_stage(
            self.job, self.manifest, gallery, cook, package, runtime, frame,
            package_root, "Ayric")
        self.assertTrue(output.is_file())
        self.assertTrue(audit["production_ready"])

    def test_cook_without_success_marker_is_rejected(self) -> None:
        self.advance_through_import()
        gallery = self.gallery_report()
        record_runtime_review_stage(
            self.job, self.manifest, gallery, self.make_frame("editor.png"),
            "Ayric", "Reviewed imported runtime.")
        cook = self.root / "cook.log"
        package = self.root / "package.log"
        runtime = self.root / "runtime.log"
        package_root = self.root / "package"
        package_root.mkdir()
        cook.write_text("LogCook: Display: Done!")
        package.write_text("Success - 0 error(s), 0 warning(s)\nBUILD SUCCESSFUL\n{0}".format(
            package_root.resolve()))
        runtime.write_text("Load map complete /Game/Compiled/L_RacGallery")
        (package_root / "Game.exe").write_bytes(b"exe")
        (package_root / "Game.pak").write_bytes(b"pak")
        with self.assertRaisesRegex(ValueError, "lacks terminal markers"):
            record_cook_stage(
                self.job, self.manifest, gallery, cook, package, runtime,
                self.make_frame("packaged.png"), package_root, "Ayric")


if __name__ == "__main__":
    unittest.main()
