"""The humanoid rig stage a studio calls by name.

`rac run-stage rig` wraps the portable landmark route (run_rig_candidate.ps1)
against the ue5_manny_browser profile, exports a browser GLB with its skin, and
hands back the pose suite as evidence. It is a candidate route: the receipt
never claims production grade, and a person reviews the poses.

Most of this runs without Blender: the registry, the attempt directory and the
refusals are where the mistakes are. Two checks run real Blender when
RAC_BLENDER is set: a plain cube must be refused with a readable reason, and a
humanoid named by RAC_RIG_HUMANOID must come back rigged with its evidence.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from reference_asset_compiler.stages import (
    STAGES,
    StageError,
    describe_stages,
    prepare_rig,
    run_stage,
)

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get("RAC_BLENDER")
HUMANOID = os.environ.get("RAC_RIG_HUMANOID")


class RigStageRegistryTests(unittest.TestCase):
    def test_the_stage_is_registered_against_its_own_launcher(self):
        stage = STAGES["rig"]
        self.assertEqual(stage["runner"], "powershell")
        self.assertEqual(stage["script"], "scripts/run_rig_stage.ps1")
        self.assertTrue((ROOT / stage["script"]).is_file())
        self.assertIn("blender", stage["needs"])
        self.assertEqual(stage["produces"], "reference-asset-compiler.rig-candidate.v1")

    def test_a_studio_is_told_it_cannot_rig_without_blender(self):
        rig = {entry["stage"]: entry for entry in describe_stages(ROOT, blender=None)["stages"]}["rig"]
        # A GLB, like every other model stage, so a studio chaining steps can
        # name the file before it exists.
        self.assertEqual(rig["output_suffix"], ".glb")
        if not BLENDER:
            self.assertFalse(rig["available"])
            self.assertIn("blender", rig["missing"])


class PrepareRigTests(unittest.TestCase):
    def test_each_run_claims_a_fresh_attempt_beside_the_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "hero.glb"
            source.write_bytes(b"glTF")
            output = Path(folder) / "out" / "hero-rigged.glb"
            first = prepare_rig(source, output, "blender.exe")
            attempt = Path(first["payload"]["attempt_directory"])
            self.assertEqual(attempt.name, "hero-rigged-rig-attempt001")
            self.assertEqual(attempt.parent, output.parent.resolve())
            self.assertEqual(first["produced"]["output"], attempt / "rigged.glb")
            self.assertEqual(first["produced"]["report"], attempt / "rig-stage-report.json")
            self.assertEqual(first["arguments"][:4], ["-InputMesh", str(source.resolve()), "-OutputDirectory", str(attempt)])
            self.assertEqual(first["arguments"][4:], ["-Blender", "blender.exe"])

            # An earlier attempt is the record of what was tried; the next one
            # goes beside it rather than over it.
            attempt.mkdir(parents=True)
            second = prepare_rig(source, output, None)
            self.assertEqual(Path(second["payload"]["attempt_directory"]).name, "hero-rigged-rig-attempt002")
            self.assertNotIn("-Blender", second["arguments"])

    def test_a_file_that_is_not_a_mesh_is_refused_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("crate.obj", "hero.blend", "hero"):
                with self.subTest(name=name):
                    with self.assertRaises(StageError) as refusal:
                        prepare_rig(Path(folder) / name, Path(folder) / "out.glb")
                    self.assertIn("GLB, glTF or FBX", str(refusal.exception))


@unittest.skipUnless(BLENDER, "Set RAC_BLENDER for real Blender checks")
class RigStageBlenderTests(unittest.TestCase):
    def test_a_cube_is_refused_with_a_reason_a_person_can_read(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("RAC_SHORT_TEMP")) as folder:
            cube = Path(folder) / "cube.glb"
            subprocess.run([
                BLENDER, "-b", "--factory-startup", "--python-expr",
                "import bpy; bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(); "
                "bpy.ops.mesh.primitive_cube_add(size=1.8); "
                "bpy.ops.export_scene.gltf(filepath=r'{0}')".format(cube),
            ], check=True, capture_output=True, stdin=subprocess.DEVNULL)
            result = run_stage("rig", cube, Path(folder) / "out" / "cube-rigged.glb",
                               Path(folder) / "out" / "cube-rigged.json", repo_root=ROOT, blender=BLENDER)
            self.assertFalse(result["ok"])
            # The reason travels out; "exited with code 1" is not a reason.
            self.assertIn("could not be rigged", result["error"])
            self.assertFalse((Path(folder) / "out" / "cube-rigged.glb").exists())

    @unittest.skipUnless(HUMANOID, "Set RAC_RIG_HUMANOID to a prepared humanoid GLB")
    def test_a_humanoid_comes_back_rigged_with_its_pose_suite(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("RAC_SHORT_TEMP")) as folder:
            output = Path(folder) / "out" / "hero-rigged.glb"
            result = run_stage("rig", Path(HUMANOID), output, Path(folder) / "out" / "hero-rigged.json",
                               repo_root=ROOT, blender=BLENDER)
            self.assertTrue(result["ok"], result.get("error"))
            receipt = result["receipt"]
            self.assertEqual(receipt["schema"], "reference-asset-compiler.rig-candidate.v1")
            self.assertEqual(receipt["skeleton_profile"], "ue5_manny_browser")
            self.assertTrue(receipt["gate"]["passed"])
            self.assertTrue(receipt["deformation"]["passed"])
            self.assertTrue(receipt["geometry_unchanged"])
            self.assertEqual(receipt["weight_coverage"], 1)
            self.assertLessEqual(receipt["maximum_influences"], 4)
            # A candidate, never an approval.
            self.assertFalse(receipt["production_grade"])
            self.assertTrue(receipt["requires_deformation_review"])
            self.assertEqual(receipt["landmarks"]["status"], "derived_pending_overlay_review")
            self.assertTrue(output.is_file())

            manifest = json.loads(Path(receipt["evidence_manifest"]).read_text(encoding="utf-8-sig"))
            poses = {view["pass"] for view in manifest["views"] if view["pass"] != "landmarks"}
            self.assertEqual(poses, {"arms_forward", "left_arm_only", "elbows_bent", "knees_bent", "spine_twist"})
            for view in manifest["views"]:
                self.assertTrue((Path(receipt["evidence_directory"]) / view["file"]).is_file())
                self.assertEqual(len(view["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
