"""The Pixal3D geometry stage: its environment, its command, and what it refuses before a GPU is asked for."""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import run_pixal_geometry as rpg  # noqa: E402
from reference_asset_compiler.pixal import linux_path, pixal_command  # noqa: E402
from reference_asset_compiler.prop_quality import game_mesh_check
from reference_asset_compiler.stages import STAGES, StageError, prepare_pixal_geometry  # noqa: E402


class PathTests(unittest.TestCase):
    def test_a_windows_path_is_given_as_wsl_sees_it(self):
        self.assertEqual(linux_path(r"C:\Users\A\scratch\cut out.png"), "/mnt/c/Users/A/scratch/cut out.png")
        self.assertEqual(linux_path("D:/x/y.glb"), "/mnt/d/x/y.glb")
        self.assertEqual(linux_path("/home/a/b.glb"), "/home/a/b.glb")

    def test_the_command_runs_in_the_checkout_with_the_environments_own_packages(self):
        paths = {"root": "/home/a/Pixal3D", "python": "/home/a/env/bin/python", "distro": "Ubuntu-22.04"}
        command = pixal_command(["/mnt/c/run.py", "--image", "/mnt/c/it's.png"], paths, on_windows=True)
        self.assertEqual(command[:6], ["wsl.exe", "-d", "Ubuntu-22.04", "--", "bash", "-c"])
        script = command[6]
        self.assertIn("PYTHONNOUSERSITE=1", script)
        self.assertIn("cd \"$PIXAL3D_ROOT\"", script)
        self.assertIn(r"'/home/a/env/bin/python' '/mnt/c/run.py' '--image' '/mnt/c/it'\''s.png'", script)
        self.assertEqual(pixal_command(["x"], paths, on_windows=False)[:2], ["bash", "-c"])


class PinTests(unittest.TestCase):
    def test_the_runner_matches_its_pinned_hash(self):
        self.assertEqual(rpg.sha256(rpg.RUNNER), rpg.pinned_runner_hash())


class PictureTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_only_a_picture_with_a_transparent_background_counts_as_a_cutout(self):
        opaque = self.root / "opaque.png"
        Image.new("RGB", (32, 32), (200, 200, 200)).save(opaque)
        cut = np.zeros((32, 32, 4), np.uint8)
        cut[8:24, 8:24] = (120, 80, 40, 255)
        cutout = self.root / "cutout.png"
        Image.fromarray(cut, "RGBA").save(cutout)
        self.assertFalse(rpg.has_transparency(opaque))
        self.assertTrue(rpg.has_transparency(cutout))

    def test_the_stage_refuses_before_any_work(self):
        picture = self.root / "p.png"
        Image.new("RGB", (8, 8)).save(picture)
        report = self.root / "r.json"
        blender = self.root / "blender.exe"
        blender.write_bytes(b"")
        self.assertEqual(rpg.main(["--", str(picture), str(self.root / "o.glb"), str(report), "--size-m", "2",
                                   "--blender", str(blender)]), 1)
        self.assertEqual(rpg.main(["--", str(picture), str(self.root / "o.blend"), str(report), "--size-m", "90",
                                   "--blender", str(blender)]), 1)
        self.assertFalse(any(self.root.glob("o-pixal-attempt*")))


class PreparationTests(unittest.TestCase):
    def test_game_mesh_bounds_and_shell_are_checked_independently(self):
        mesh = {"min_m": [0, 0, 0], "max_m": [.55, .61, .65], "open_edges_after": 105}
        check = game_mesh_check(mesh, .55, "longest", "closed")
        self.assertEqual(len(check["reasons"]), 2)
        self.assertFalse(check["ok"])
        self.assertTrue(game_mesh_check(mesh, .55, "width", "open")["ok"])
        mesh["open_edges_after"] = 0
        self.assertTrue(game_mesh_check(mesh, .55, "width", "closed")["ok"])
        self.assertTrue(game_mesh_check(mesh, .65, "height", "closed")["ok"])

    def test_a_landmark_is_a_height_and_metres_are_the_longest_side(self):
        landmark = prepare_pixal_geometry({"size": "knee", "seed": 45, "vertex_target": 100000}, "blender.exe", None)
        arguments = landmark["arguments"]
        self.assertEqual(arguments[arguments.index("--size-is") + 1], "height")
        self.assertAlmostEqual(float(arguments[arguments.index("--size-m") + 1]), landmark["payload"]["size_m"])
        self.assertEqual(arguments[arguments.index("--seed") + 1], "45")
        self.assertEqual(arguments[arguments.index("--vertex-target") + 1], "100000")
        metres = prepare_pixal_geometry({"size_m": 2.2, "up": "longest", "flip": True}, "blender.exe",
                                        Path("C:/studio"))["arguments"]
        self.assertEqual(metres[metres.index("--size-is") + 1], "longest")
        self.assertEqual(metres[metres.index("--up") + 1], "longest")
        self.assertIn("--flip", metres)
        self.assertEqual(Path(metres[metres.index("--legacy-root") + 1]), Path("C:/studio"))

    def test_it_refuses_a_missing_double_or_implausible_size_and_an_unknown_up(self):
        for options in ({}, {"size": "knee", "size_m": 1.0}, {"size_m": 0.001}, {"size": "giraffe"},
                        {"size_m": 1.0, "up": "sideways"}, {"size_m": 1.0, "size_is": "diagonal"}):
            with self.assertRaises(StageError):
                prepare_pixal_geometry(options, "blender.exe", None)

    def test_the_stage_is_listed_with_its_cost_and_writes_a_blend(self):
        stage = STAGES["pixal-geometry"]
        self.assertEqual(stage["output_suffix"], ".blend")
        self.assertIn("pixal", stage["needs"])
        self.assertEqual(stage["estimate"]["unit"], "seed")
        from reference_asset_compiler import cli  # noqa: PLC0415
        args = cli.build_parser().parse_args([
            "run-stage", "pixal-geometry", "--source", "p.png", "--output", "o.blend", "--report", "o.json",
            "--size-m", "2.2", "--seed", "45", "--vertex-target", "100000", "--up", "longest", "--flip"])
        self.assertEqual((args.size_m, args.seed, args.vertex_target, args.up, args.flip), (2.2, 45, 100000, "longest", True))


if __name__ == "__main__":
    unittest.main()
