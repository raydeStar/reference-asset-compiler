"""Preparing a geometry run, which is everything that happens before the GPU.

The Hunyuan launcher refuses well on its own. What it cannot do is invent the
request, and a studio holding a reference image should not have to know about
workspaces, intakes and attempt numbering to ask for a model. That preparation
is ordinary filesystem work, so it is exercised here in full -- on any machine,
with no weights, no environment and no card -- and the request it writes is then
handed to the real validator to confirm it would actually be accepted.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from reference_asset_compiler.geometry_request import validate_geometry_request
from reference_asset_compiler.geometry_stage import (
    DEFAULT_PARAMETERS,
    GeometryStageError,
    geometry_missing,
    prepare_single_view_request,
    resolve_legacy_root,
    slugify,
)
from reference_asset_compiler.io import read_json, sha256_file


def repo_like(root: Path) -> Path:
    """The parts of a checkout the geometry stage looks for."""
    (root / "workflows" / "geometry" / "hunyuan3d").mkdir(parents=True)
    (root / "work").mkdir()
    return root


def legacy_like(root: Path) -> Path:
    """The parts of a studio tree the geometry stage looks for."""
    interpreter = root / ".venv-hy3d" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"python")
    (root / "upstream" / "Hunyuan3D-2").mkdir(parents=True)
    return root


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = Path(tempfile.mkdtemp())
        self.repo = repo_like(self.temporary / "repo")
        self.image = self.temporary / "warden-concept.png"
        self.image.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png, but a stable one")

    def prepare(self, **overrides):
        return prepare_single_view_request(self.image, self.repo, **overrides)

    def test_the_request_the_real_validator_accepts(self):
        prepared = self.prepare()

        # The point of the whole module: what it writes is what the launcher's
        # own preflight demands, checked by that preflight rather than by a
        # second opinion written here.
        preflight = validate_geometry_request(
            prepared["request"], legacy_root=self.temporary, repo_root=self.repo)

        self.assertTrue(preflight["launch_ready"])
        self.assertFalse(preflight["inference_launched"])
        self.assertEqual(preflight["mode"], "single_view")
        self.assertEqual(preflight["asset_id"], "warden-concept")
        self.assertEqual(preflight["source_authority"]["sha256"], sha256_file(self.image))

    def test_the_workspace_records_the_picture_it_came_from(self):
        prepared = self.prepare()

        intake = read_json(prepared["workspace"] / "intake.json")

        self.assertEqual(intake["asset_id"], "warden-concept")
        self.assertEqual(intake["source"]["path"], "references/primary.png")
        self.assertEqual(intake["source"]["sha256"], sha256_file(self.image))
        # The original name is kept even though the copy is renamed, because it
        # is the only thing connecting the workspace to what a person chose.
        self.assertEqual(intake["source"]["original_filename"], "warden-concept.png")
        copied = prepared["workspace"] / "references" / "primary.png"
        self.assertEqual(sha256_file(copied), sha256_file(self.image))

    def test_a_second_request_for_the_same_image_is_a_new_attempt(self):
        first = self.prepare()
        second = self.prepare()

        # The launcher refuses to write into a directory that exists, so two
        # requests that named the same one would make the second unrunnable.
        self.assertNotEqual(first["attempt_directory"], second["attempt_directory"])
        self.assertTrue(first["attempt_directory"].name.endswith("attempt001"))
        self.assertTrue(second["attempt_directory"].name.endswith("attempt002"))
        # One workspace and one intake, though: the source has not changed.
        self.assertEqual(first["workspace"], second["workspace"])

    def test_the_seed_is_visible_in_the_attempt_name(self):
        prepared = self.prepare(parameters={"seed": 7})

        # A disappointing result stays on disk beside the settings that made
        # it; a directory that does not name them is a result you cannot place.
        self.assertIn("seed7", prepared["attempt_directory"].name)

    def test_a_different_image_under_a_taken_name_is_refused(self):
        self.prepare(asset_name="warden")
        other = self.temporary / "someone-else.png"
        other.write_bytes(b"\x89PNG\r\n\x1a\na different picture entirely")

        with self.assertRaises(GeometryStageError) as refusal:
            prepare_single_view_request(other, self.repo, asset_name="warden")

        # Overwriting would orphan every candidate, receipt and rig already
        # bound to the first intake, silently.
        self.assertIn("different image", str(refusal.exception))

    def test_the_same_image_under_a_taken_name_is_allowed(self):
        first = self.prepare(asset_name="warden")
        again = self.prepare(asset_name="warden")

        self.assertEqual(first["workspace"], again["workspace"])
        self.assertEqual(first["source_sha256"], again["source_sha256"])

    def test_defaults_are_the_settings_that_have_worked_here(self):
        prepared = self.prepare()

        self.assertEqual(prepared["parameters"], DEFAULT_PARAMETERS)
        request = read_json(prepared["request"])
        self.assertEqual(request["parameters"]["octree_resolution"], 512)

    def test_a_setting_outside_its_range_is_named(self):
        for parameters, expected in (
            ({"steps": 90}, "steps"),
            ({"seed": -1}, "seed"),
            ({"octree_resolution": 1024}, "octree_resolution"),
            ({"chunks": 10}, "chunks"),
        ):
            with self.subTest(parameters=parameters):
                with self.assertRaises(GeometryStageError) as refusal:
                    self.prepare(parameters=parameters)
                # The launcher would reject these too, an hour and a queue slot
                # later, in terms the caller would have to decode.
                self.assertIn(expected, str(refusal.exception))

    def test_something_that_is_not_an_image_is_refused_before_anything_is_written(self):
        mesh = self.temporary / "already-a-model.glb"
        mesh.write_bytes(b"glTF")

        with self.assertRaises(GeometryStageError) as refusal:
            prepare_single_view_request(mesh, self.repo)

        self.assertIn(".glb is not one of", str(refusal.exception))
        self.assertEqual(list((self.repo / "work").iterdir()), [])

    def test_a_missing_image_is_refused(self):
        with self.assertRaises(GeometryStageError):
            prepare_single_view_request(self.temporary / "nothing.png", self.repo)

    def test_an_asset_name_cannot_escape_the_workspace_root(self):
        prepared = self.prepare(asset_name="../../elsewhere")

        # A name is a slug, not a path: the separators become ordinary
        # characters rather than a traversal, so the workspace lands under the
        # work root whatever was asked for.
        self.assertEqual(prepared["workspace"].parent, (self.repo / "work").resolve())
        self.assertEqual(prepared["asset_id"], "elsewhere")

    def test_a_name_with_nothing_usable_in_it_is_refused(self):
        with self.assertRaises(GeometryStageError):
            self.prepare(asset_name="///")


class SlugTests(unittest.TestCase):
    def test_names_become_paths_that_survive_every_filesystem(self):
        self.assertEqual(slugify("Warden's Lantern v2"), "warden-s-lantern-v2")
        self.assertEqual(slugify("  spaced  out  "), "spaced-out")
        self.assertEqual(slugify("LAB-010"), "lab-010")

    def test_a_long_name_is_bounded(self):
        self.assertEqual(len(slugify("a" * 200)), 64)


class CapabilityTests(unittest.TestCase):
    """What a studio asks before queueing anything."""

    def setUp(self):
        self.temporary = Path(tempfile.mkdtemp())
        self.repo = repo_like(self.temporary / "repo")
        self.legacy = legacy_like(self.temporary / "studio")

    def test_a_complete_machine_is_missing_nothing(self):
        self.assertEqual(geometry_missing(self.repo, self.legacy), [])

    def test_no_studio_tree_at_all(self):
        self.assertEqual(geometry_missing(self.repo, None), ["legacy-root"])

    def test_a_studio_tree_without_its_environment(self):
        shutil.rmtree(self.legacy / ".venv-hy3d")

        # This is the common case on a machine that has the repository but has
        # never installed the weights, and it must not read as "ready".
        self.assertEqual(geometry_missing(self.repo, self.legacy), ["geometry-environment"])

    def test_an_environment_without_the_upstream_checkout(self):
        shutil.rmtree(self.legacy / "upstream" / "Hunyuan3D-2")

        self.assertEqual(geometry_missing(self.repo, self.legacy), ["hunyuan-checkout"])

    def test_a_checkout_without_the_runners(self):
        shutil.rmtree(self.repo / "workflows" / "geometry" / "hunyuan3d")

        self.assertEqual(geometry_missing(self.repo, self.legacy), ["runners"])

    def test_the_studio_tree_is_named_and_never_searched_for(self):
        # A guessed tree is a different set of weights from the one an asset
        # was gated with, and nothing in a receipt would show the difference.
        self.assertEqual(resolve_legacy_root(self.legacy), self.legacy.resolve())
        self.assertIsNone(resolve_legacy_root(self.temporary / "absent", required=False))
        with self.assertRaises(GeometryStageError):
            resolve_legacy_root(self.temporary / "absent")


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = Path(tempfile.mkdtemp())
        self.repo = repo_like(self.temporary / "repo")
        (self.repo / "scripts").mkdir()
        (self.repo / "scripts" / "run_hy3d_geometry.ps1").write_text("param()", encoding="utf-8")

    def test_geometry_reports_what_it_lacks_rather_than_failing_later(self):
        from reference_asset_compiler.stages import describe_stages

        described = describe_stages(self.repo, blender=None, legacy_root=None)
        geometry = next(s for s in described["stages"] if s["stage"] == "geometry")

        self.assertFalse(geometry["available"])
        self.assertIn("legacy-root", geometry["missing"])
        self.assertEqual(geometry["produces"], "reference-asset-compiler.geometry-candidate.v1")

    def test_the_launcher_is_handed_the_request_and_its_result_is_collected(self):
        """The one link the rest of these tests cannot reach, with nothing launched.

        Everything above stops before the subprocess. This stands in for it, so
        that the argument list the launcher would actually receive, and the
        copying of what it produces, are checked on a machine with no GPU.
        """
        from reference_asset_compiler import stages

        legacy = legacy_like(self.temporary / "studio")
        image = self.temporary / "concept.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")
        seen = {}

        def pretend_to_launch(command, **keywords):
            seen["command"] = command
            seen["keywords"] = keywords
            request = read_json(Path(command[command.index("-Request") + 1]))
            attempt = Path(request["output_directory"])
            attempt.mkdir(parents=True)
            (attempt / "candidate.glb").write_bytes(b"glTF-the-candidate")
            (attempt / "candidate-receipt.json").write_text(
                json.dumps({"schema": "reference-asset-compiler.geometry-candidate.v1",
                            "status": "candidate -- not approved, not an asset"}),
                encoding="utf-8")
            return type("Finished", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        original = stages.subprocess.run
        stages.subprocess.run = pretend_to_launch
        try:
            payload = stages.run_stage(
                "geometry", image, self.temporary / "model.glb", self.temporary / "receipt.json",
                repo_root=self.repo, legacy_root=legacy)
        finally:
            stages.subprocess.run = original

        command = seen["command"]
        self.assertEqual(command[0], stages.POWERSHELL)
        # -NonInteractive matters: a launcher that stops to ask something on a
        # queue worker hangs until the timeout rather than failing.
        self.assertIn("-NonInteractive", command)
        # Windows runners may spell TEMP with an 8.3 alias; the launcher resolves it.
        self.assertEqual(command[command.index("-LegacyRoot") + 1], str(legacy.resolve()))
        self.assertTrue(command[command.index("-File") + 1].endswith("run_hy3d_geometry.ps1"))
        # A stage is run by a queue worker whose own input is whatever its
        # parent handed it -- under a service, a pipe nobody will ever write to.
        # A child that can read it waits for ever, holding a lease and spending
        # no CPU, which is indistinguishable from slow work. This was not
        # hypothetical: it stopped the first live run dead for nine minutes.
        self.assertEqual(seen["keywords"].get("stdin"), stages.subprocess.DEVNULL)

        self.assertTrue(payload["ok"])
        # The launcher writes into its own attempt directory and will not be
        # told otherwise; the caller still gets an answer where it asked.
        self.assertEqual((self.temporary / "model.glb").read_bytes(), b"glTF-the-candidate")
        self.assertEqual(payload["receipt"]["schema"],
                         "reference-asset-compiler.geometry-candidate.v1")
        # And the attempt stays on disk, named in the answer, for the record.
        self.assertTrue(Path(payload["attempt_directory"]).is_dir())
        self.assertEqual(payload["asset_id"], "concept")

    def test_a_launcher_that_writes_nothing_is_not_reported_as_success(self):
        from reference_asset_compiler import stages

        legacy = legacy_like(self.temporary / "studio")
        image = self.temporary / "concept.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")

        def pretend_to_launch(command, **keywords):
            return type("Finished", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        original = stages.subprocess.run
        stages.subprocess.run = pretend_to_launch
        try:
            payload = stages.run_stage(
                "geometry", image, self.temporary / "model.glb", self.temporary / "receipt.json",
                repo_root=self.repo, legacy_root=legacy)
        finally:
            stages.subprocess.run = original

        # An exit code of zero is a claim, not evidence. Without the candidate
        # there is nothing to deliver, and saying so beats handing back a
        # success whose output does not exist.
        self.assertFalse(payload["ok"])
        self.assertIn("could not be collected", payload["error"])
        self.assertFalse((self.temporary / "model.glb").exists())

    def test_running_geometry_without_a_studio_tree_starts_nothing(self):
        from reference_asset_compiler.stages import StageError, run_stage

        image = self.temporary / "concept.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n")

        with self.assertRaises(Exception) as refusal:
            run_stage("geometry", image, self.temporary / "out.glb", self.temporary / "out.json",
                      repo_root=self.repo, legacy_root=self.temporary / "absent")

        self.assertIsInstance(refusal.exception, (StageError, GeometryStageError))
        # Nothing was written: a refused run leaves no half-made workspace for
        # the next attempt to trip over.
        self.assertEqual(list((self.repo / "work").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
