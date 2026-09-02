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

from reference_asset_compiler.articulated_evidence import (  # noqa: E402
    REQUIRED_POSES,
    record_deformation_stage,
    record_rig_and_skin_stage,
    record_ue5_motion_review_stage,
)
from reference_asset_compiler.io import sha256_file  # noqa: E402
from reference_asset_compiler.runtime_evidence import (  # noqa: E402
    record_cook_stage,
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


class ArticulatedEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "source.png"
        source.write_bytes(b"source")
        self.job = create_workspace(
            self.root / "work", source, "Hero", "humanoid", "required", REGISTRY,
            skeleton_profile="ue5_manny",
        )
        candidate, _ = promote_generated(self.job)
        token = self.job / "logs" / "stage.json"
        token.write_text("{}", encoding="utf-8")
        views: list[Path] = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = self.job / "modeling" / name
            path.write_bytes(name.encode())
            views.append(path)
        promote_stage(
            self.job, "modeling_approval", modeling_evidence(self.job, candidate, views),
            "Approved.", "Ayric")
        cleaned = promote_cleanup(self.job, candidate)
        promote_retopology(self.job, cleaned)
        promote_stage(self.job, "unwrap_and_bake", [token], "Passed.", "system")
        self.approved = self.job / "textures" / "hero_production.fbx"
        texture_evidence = []
        for name in ("hero_production.fbx", "retopo.json", "gate-tex.json", "base.png",
                     "beauty-front.png", "beauty-three-quarter.png",
                     "beauty-side.png", "beauty-back.png"):
            path = self.job / "textures" / name
            path.write_bytes(name.encode())
            texture_evidence.append(path)
        promote_stage(self.job, "texture_approval", texture_evidence, "Approved.", "Ayric")
        self.rigged = self.root / "hero-rigged.fbx"
        self.rigged.write_bytes(b"rigged")
        self.profile = self.root / "ue5-manny.json"
        self.profile.write_text(json.dumps({"profile_id": "ue5_manny"}))
        self.gate = self.root / "gate-rig.json"
        self.gate.write_text(json.dumps({
            "asset": str(self.rigged.resolve()), "profile": "ue5_manny", "ok": True,
            "failures": [], "warnings": [], "bone_count": 86, "total_tris": 20000,
        }))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_frame(self, path: Path) -> Path:
        image = Image.new("RGB", (800, 450), (32, 64, 96))
        image.paste((192, 128, 64), (400, 0, 800, 450))
        image.save(path)
        return path

    def advance_through_deformation(self) -> None:
        record_rig_and_skin_stage(
            self.job, self.approved, self.rigged, self.profile, self.gate)
        render_dir = self.root / "deform"
        render_dir.mkdir()
        poses = {}
        for pose in REQUIRED_POSES:
            names = ["deform-{0}-front.png".format(pose),
                     "deform-{0}-side.png".format(pose)]
            for name in names:
                self.make_frame(render_dir / name)
            poses[pose] = {"vertices_moved": 100, "side_bias": 0.0, "renders": names}
        report = self.root / "deform.json"
        report.write_text(json.dumps({
            "asset": str(self.rigged.resolve()), "poses": poses,
            "failures": [], "warnings": [], "ok": True,
        }))
        record_deformation_stage(self.job, self.rigged, report, render_dir)

    def test_rig_input_must_be_exact_texture_approval(self) -> None:
        impostor = self.root / "impostor.fbx"
        impostor.write_bytes(b"impostor")
        with self.assertRaisesRegex(ValueError, "exact texture-approved"):
            record_rig_and_skin_stage(
                self.job, impostor, self.rigged, self.profile, self.gate)

    def test_articulated_route_reaches_verified_cooked_runtime(self) -> None:
        self.advance_through_deformation()
        published = self.root / "published"
        published.mkdir()
        fbx = published / "hero-production.fbx"
        fbx.write_bytes(b"fbx")
        manifest = published / "hero-production.ue5import.json"
        manifest.write_text(json.dumps({
            "asset_id": "hero-production", "kind": "humanoid", "fbx": fbx.name,
            "skeleton_profile": "ue5_manny",
        }))
        batch = self.root / "ue5-import.json"
        batch.write_text(json.dumps({
            "engine_version": "5.8.2-test",
            "assets": [{
                "asset_id": "hero-production", "manifest_sha256": sha256_file(manifest),
                "checks": [{"check": "mesh_exists", "ok": True}], "ok": True,
            }],
        }))
        record_ue5_import_stage(self.job, manifest, batch)
        motion = self.root / "motion.json"
        runs = []
        for animation in ("MM_Idle", "MF_Unarmed_Jog_Fwd"):
            runs.append({
                "asset": "/Game/Compiled/HeroProduction/hero-production",
                "animation": animation,
                "checks": [{"check": "skeleton_moves", "ok": True}], "ok": True,
            })
        motion.write_text(json.dumps({"engine_version": "5.8.2-test", "runs": runs}))
        motion_frames = [self.make_frame(self.root / "idle.png"),
                         self.make_frame(self.root / "run.png")]
        record_ue5_motion_review_stage(
            self.job, manifest, motion, motion_frames, "Ayric", "Motion reviewed.")

        gallery = self.root / "gallery.json"
        gallery.write_text(json.dumps({
            "level": "/Game/Compiled/L_RacGallery",
            "placed": [{"asset": "/Game/Compiled/HeroProduction/hero-production"}],
        }))
        cook = self.root / "cook.log"
        package = self.root / "package.log"
        runtime = self.root / "runtime.log"
        package_root = self.root / "package"
        package_root.mkdir()
        cook.write_text("LogCook: Display: Done!\nLogInit: Display: Success - 0 error(s), 0 warning(s)")
        package.write_text("Success - 0 error(s), 0 warning(s)\nBUILD SUCCESSFUL\n{0}".format(
            package_root.resolve()))
        runtime.write_text("Load map complete /Game/Compiled/L_RacGallery")
        (package_root / "Game.exe").write_bytes(b"exe")
        (package_root / "Game.pak").write_bytes(b"pak")
        _, audit = record_cook_stage(
            self.job, manifest, gallery, cook, package, runtime,
            self.make_frame(self.root / "packaged.png"), package_root, "Ayric")
        self.assertTrue(audit["production_ready"])


if __name__ == "__main__":
    unittest.main()
