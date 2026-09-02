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
