"""Projecting the reference: only onto geometry made from that picture, through a camera that fits it."""
import hashlib
import importlib.util
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from reference_asset_compiler.stages import StageError, prepare_project_reference

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location("project_reference", ROOT / "scripts" / "project_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.picture = self.root / "picture.png"
        Image.new("RGB", (8, 8), (90, 90, 90)).save(self.picture)
        self.report = self.root / "pixal.json"
        self.report.write_text(json.dumps({
            "schema": "reference-asset-compiler.pixal-geometry.v1", "picture": str(self.picture),
            "picture_sha256": hashlib.sha256(self.picture.read_bytes()).hexdigest()}), encoding="utf-8")

    def test_the_picture_the_geometry_was_made_from_is_accepted(self):
        arguments = prepare_project_reference({"geometry": self.report, "reference": self.picture}, "blender")["arguments"]
        self.assertEqual(arguments[arguments.index("--blender") + 1], "blender")
        self.assertEqual(arguments[arguments.index("--geometry") + 1], str(self.report.resolve()))

    def test_a_revised_picture_is_refused_until_the_geometry_is_made_again(self):
        # WK-04.3: the geometry came from the first picture and the revised one
        # was projected, and every bolt was doubled 2 cm beside itself.
        revised = self.root / "revised.png"
        Image.new("RGB", (8, 8), (80, 80, 80)).save(revised)
        with self.assertRaisesRegex(StageError, "make the geometry again"):
            prepare_project_reference({"geometry": self.report, "reference": revised}, "blender")

    def test_a_report_from_another_stage_or_none_at_all_is_refused(self):
        with self.assertRaisesRegex(StageError, "pass --geometry"):
            prepare_project_reference({"reference": self.picture}, "blender")
        other = self.root / "other.json"
        other.write_text(json.dumps({"schema": "reference-asset-compiler.texture-uv-transport.v1"}), encoding="utf-8")
        with self.assertRaisesRegex(StageError, "not a pixal-geometry report"):
            prepare_project_reference({"geometry": other, "reference": self.picture}, "blender")

    def test_the_fit_threshold_must_be_an_overlap(self):
        with self.assertRaisesRegex(StageError, "between 0.5 and 1"):
            prepare_project_reference({"geometry": self.report, "reference": self.picture, "minimum_fit": 3},
                                      "blender")


class CameraFitTests(unittest.TestCase):
    def test_a_known_camera_is_found_again_from_the_outline_alone(self):
        script = load_script()
        # A box, 1 x 0.6 x 0.3, in Pixal3D's raw frame, seen by a camera turned
        # a little and narrower than the fit starts from.
        corners = np.array([[x, y, z] for x in (-0.5, 0.5) for y in (-0.15, 0.15) for z in (-0.3, 0.3)])
        corners = corners @ np.array([[math.cos(0.5), 0, math.sin(0.5)], [0, 1, 0], [-math.sin(0.5), 0, math.cos(0.5)]]).T
        faces = [(0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5), (0, 4, 5), (0, 5, 1),
                 (2, 3, 7), (2, 7, 6), (0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3)]
        truth = (6.0, 0.0, 0.0, 12.0)
        u, v = script.project(truth, corners)
        scale, offset = 900.0, 256.0
        mask = Image.new("L", (512, 512), 0)
        draw = ImageDraw.Draw(mask)
        for face in faces:
            draw.polygon([(u[i] * scale + offset, v[i] * scale + offset) for i in face], fill=255)
        alpha = np.asarray(mask) > 127
        fitted = script.fit_camera(corners, np.array(faces), alpha, start_fov=16.0)
        self.assertGreater(fitted["iou"], 0.98)
        self.assertAlmostEqual(fitted["params"][0], truth[0], delta=2.0)


if __name__ == "__main__":
    unittest.main()
