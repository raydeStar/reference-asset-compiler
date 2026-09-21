"""Unwrapping a generated mesh and painting it from its reference.

A generated mesh has no UVs: nothing in generation makes them and nothing in
reduction keeps them. The painter needs them, and says so in the least helpful
way available -- an AttributeError deep inside a mesh library -- so the unwrap
runs first and refuses in its own terms.

The painter is also the one stage here that takes a second input, the picture
it paints from, and the one whose exit code is not its verdict: it can fault
during teardown after writing everything and passing its own geometry and UV
gate. None of this runs a GPU; what is exercised is the paperwork and the
refusals.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from reference_asset_compiler import stages
from reference_asset_compiler.geometry_stage import paint_missing
from reference_asset_compiler.stages import (
    StageError,
    describe_stages,
    prepare_texture,
    prepare_uv_unwrap,
    run_stage,
)


def paint_stack(root: Path) -> Path:
    """The four separate things a paint install is made of."""
    interpreter = root / ".venv-hy3d21" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"python")
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "run_hy3d21_pbr.py").write_text("paint", encoding="utf-8")
    (root / "upstream" / "Hunyuan3D-2.1").mkdir(parents=True)
    (root / "models" / "hy3d21" / "Hunyuan3D-2.1").mkdir(parents=True)
    return root


class PaintCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = Path(tempfile.mkdtemp())
        self.legacy = paint_stack(self.temporary / "studio")

    def test_a_complete_paint_install_is_missing_nothing(self):
        self.assertEqual(paint_missing(self.legacy), [])

    def test_no_studio_tree_at_all(self):
        self.assertEqual(paint_missing(None), ["legacy-root"])

    def test_each_missing_piece_is_named_on_its_own(self):
        for removed, expected in (
            (".venv-hy3d21", "paint-environment"),
            ("scripts/run_hy3d21_pbr.py", "paint-runner"),
            ("upstream/Hunyuan3D-2.1", "paint-checkout"),
            ("models/hy3d21/Hunyuan3D-2.1", "paint-weights"),
        ):
            with self.subTest(removed=removed):
                legacy = paint_stack(Path(tempfile.mkdtemp()) / "studio")
                target = legacy / removed
                shutil.rmtree(target) if target.is_dir() else target.unlink()
                # A machine that can generate geometry often cannot paint it;
                # answering "AI is available" would be wrong half the time.
                self.assertEqual(paint_missing(legacy), [expected])


class UnwrapPreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.source = self.root / "runtime.glb"
        self.source.write_bytes(b"glTF")
        self.output = self.root / "unwrapped.obj"

    def test_the_unwrapper_reads_the_source_and_writes_its_own_attempt(self):
        prepared = prepare_uv_unwrap(self.source, self.output, {})

        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("-InputMesh") + 1], str(self.source.resolve()))
        attempt = Path(prepared["payload"]["attempt_directory"])
        self.assertEqual(arguments[arguments.index("-OutputDirectory") + 1], str(attempt))
        self.assertEqual(prepared["produced"]["output"], attempt / "texture-transport.obj")
        self.assertEqual(prepared["produced"]["report"], attempt / "uv-transport-report.json")

    def test_a_generated_prop_is_accepted_as_the_triangle_mesh_it_is(self):
        prepared = prepare_uv_unwrap(self.source, self.output, {"allow_triangulated_glb": True})

        # Welding or remeshing it would change the geometry this stage exists
        # to leave alone.
        self.assertIn("-AllowTriangulatedGlb", prepared["arguments"])

    def test_nothing_is_accepted_as_triangulated_unless_asked(self):
        self.assertNotIn("-AllowTriangulatedGlb", prepare_uv_unwrap(self.source, self.output, {})["arguments"])

    def test_each_attempt_claims_its_own_directory(self):
        first = prepare_uv_unwrap(self.source, self.output, {})
        Path(first["payload"]["attempt_directory"]).mkdir(parents=True)
        second = prepare_uv_unwrap(self.source, self.output, {})

        self.assertNotEqual(first["payload"]["attempt_directory"],
                            second["payload"]["attempt_directory"])


class TexturePreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.legacy = paint_stack(self.root / "studio")
        self.source = self.root / "unwrapped.obj"
        self.source.write_text("o mesh", encoding="utf-8")
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"png")
        self.output = self.root / "painted.glb"

    def test_the_painter_is_given_the_mesh_and_the_picture(self):
        prepared = prepare_texture(
            self.source, self.output, {"reference": self.reference}, self.legacy)

        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("-Mesh") + 1], str(self.source.resolve()))
        self.assertEqual(arguments[arguments.index("-Reference") + 1], str(self.reference.resolve()))
        # The launcher insists on an .obj path and derives every other name
        # from it, including the GLB a browser studio actually wants.
        self.assertTrue(arguments[arguments.index("-OutputObj") + 1].endswith("painted.obj"))
        attempt = Path(prepared["payload"]["attempt_directory"])
        self.assertEqual(prepared["produced"]["output"], attempt / "painted.glb")
        self.assertEqual(prepared["produced"]["report"], attempt / "painted.validation.json")

    def test_painting_without_a_reference_refuses(self):
        with self.assertRaises(StageError) as refusal:
            prepare_texture(self.source, self.output, {}, self.legacy)

        # Only the caller knows which picture an asset is of.
        self.assertIn("--reference", str(refusal.exception))

    def test_a_reference_that_is_not_there_is_refused_before_the_gpu(self):
        with self.assertRaises(StageError) as refusal:
            prepare_texture(self.source, self.output,
                            {"reference": self.root / "absent.png"}, self.legacy)

        self.assertIn("does not exist", str(refusal.exception))

    def test_a_machine_without_the_paint_stack_is_told_what_it_lacks(self):
        shutil.rmtree(self.legacy / "models" / "hy3d21" / "Hunyuan3D-2.1")

        with self.assertRaises(StageError) as refusal:
            prepare_texture(self.source, self.output, {"reference": self.reference}, self.legacy)

        self.assertIn("paint-weights", str(refusal.exception))

    def test_view_and_resolution_choices_reach_the_launcher(self):
        prepared = prepare_texture(
            self.source, self.output,
            {"reference": self.reference, "views": 8, "resolution": 768}, self.legacy)

        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("-Views") + 1], "8")
        self.assertEqual(arguments[arguments.index("-Resolution") + 1], "768")

    def test_settings_nobody_chose_are_left_to_the_launcher(self):
        prepared = prepare_texture(
            self.source, self.output, {"reference": self.reference}, self.legacy)

        # Copying the launcher's documented defaults over here would be a
        # second set to keep in step with the first.
        self.assertNotIn("-Views", prepared["arguments"])
        self.assertNotIn("-Resolution", prepared["arguments"])


class PaintVerdictTests(unittest.TestCase):
    """The one stage whose exit code is not its verdict."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.legacy = paint_stack(self.root / "studio")
        self.repo = self.root / "repo"
        (self.repo / "workflows" / "geometry" / "hunyuan3d").mkdir(parents=True)
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "scripts" / "run_hy3d21_texture.ps1").write_text("param()", encoding="utf-8")
        self.source = self.root / "unwrapped.obj"
        self.source.write_text("o mesh", encoding="utf-8")
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"png")

    def paint(self, returncode, write):
        def pretend(command, **keywords):
            if write:
                attempt = Path(command[command.index("-OutputObj") + 1]).parent
                attempt.mkdir(parents=True, exist_ok=True)
                (attempt / "painted.glb").write_bytes(b"glTF-painted")
                (attempt / "painted.validation.json").write_text(
                    json.dumps({"faces_equal": True, "geometry_delta": 1e-9, "uv_delta": 1e-9}),
                    encoding="utf-8")
            return type("Finished", (), {"returncode": returncode, "stdout": "", "stderr": "boom"})()

        original = stages.subprocess.run
        stages.subprocess.run = pretend
        try:
            return run_stage("texture", self.source, self.root / "out.glb", self.root / "out.json",
                             repo_root=self.repo, legacy_root=self.legacy,
                             options={"reference": str(self.reference)})
        finally:
            stages.subprocess.run = original

    def test_a_painter_that_faults_after_finishing_is_still_a_result(self):
        payload = self.paint(returncode=-1073741819, write=True)

        # The launcher says it in as many words: process health is separate
        # from whether the paint is sound. Throwing away a validated result
        # because a library faulted on the way out would cost a GPU run.
        self.assertTrue(payload["ok"])
        self.assertEqual((self.root / "out.glb").read_bytes(), b"glTF-painted")
        # Recorded rather than hidden, so the next reader knows it happened.
        self.assertEqual(payload["runner_exit_code"], -1073741819)
        self.assertIn("abnormally", payload["runner_exit_note"])

    def test_a_painter_that_fails_without_producing_anything_is_a_failure(self):
        payload = self.paint(returncode=1, write=False)

        self.assertFalse(payload["ok"])
        self.assertNotIn("runner_exit_code", payload)
        self.assertFalse((self.root / "out.glb").exists())

    def test_a_clean_run_carries_no_abnormal_exit_note(self):
        payload = self.paint(returncode=0, write=True)

        self.assertTrue(payload["ok"])
        self.assertNotIn("runner_exit_code", payload)

    def test_no_other_stage_may_survive_a_nonzero_exit(self):
        """The reason this leniency is granted to exactly one stage.

        A rejected reduction writes both a candidate and a report and *then*
        exits nonzero, because rejecting is how it says the collapse cost too
        much. A stage that treated "it produced its files" as success would
        deliver that rejection as a finished asset.
        """
        (self.repo / "scripts" / "run_feature_qem_reduction.ps1").write_text(
            "param()", encoding="utf-8")
        source = self.root / "staged.blend"
        source.write_bytes(b"blend")

        def pretend(command, **keywords):
            attempt = Path(command[command.index("-OutputDirectory") + 1])
            attempt.mkdir(parents=True, exist_ok=True)
            (attempt / "feature-qem-candidate.glb").write_bytes(b"glTF-rejected")
            (attempt / "reduction-report.json").write_text(
                json.dumps({"status": "rejected",
                            "failures": ["p99 surface deviation exceeds 0.005 m"]}),
                encoding="utf-8")
            return type("Finished", (), {"returncode": 1, "stdout": "", "stderr": "rejected"})()

        original = stages.subprocess.run
        stages.subprocess.run = pretend
        try:
            payload = run_stage("reduce-mesh", source, self.root / "runtime.glb",
                                self.root / "runtime.json", repo_root=self.repo,
                                blender="C:/blender.exe")
        finally:
            stages.subprocess.run = original

        self.assertFalse(payload["ok"])
        # And nothing was handed back as though it had passed.
        self.assertFalse((self.root / "runtime.glb").exists())


class RegistryTests(unittest.TestCase):
    def test_the_paint_stages_report_what_they_write(self):
        described = describe_stages(None, blender=None, legacy_root=None)
        by_name = {stage["stage"]: stage for stage in described["stages"]}

        # A consumer chaining these has to name each file before the stage
        # runs, and an unwrap writes an .obj where everything else writes glTF.
        self.assertEqual(by_name["uv-unwrap"]["output_suffix"], ".obj")
        self.assertEqual(by_name["texture"]["output_suffix"], ".glb")
        self.assertIn("legacy-root", by_name["texture"]["missing"])


if __name__ == "__main__":
    unittest.main()
