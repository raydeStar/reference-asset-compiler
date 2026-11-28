"""A thin rail at a known camera, independent of Blender and GPU inference."""
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pixal_frame import (fit_frame_camera, mounting_transform, opening_errors, overlap, pixel_vertices,
                         rasterize, reduction_weights, resolve_anchor, span_errors, validate_mounts)
from frame_seating import measure_seats, seat_transform
from pixal_frame import frame_check


class FrameTests(unittest.TestCase):
    def setUp(self):
        # Five rectangles in pixel coordinates. The analytical target is half-open
        # at the outer edges, as at a pixel-centre sample on the image plane.
        self.ref = np.zeros((512, 1024), dtype=bool)
        points, faces = [], []
        for x, y, w, h in ((32, 40, 18, 272), (974, 40, 18, 272),
                            (45, 53, 934, 13), (45, 143, 934, 5), (45, 239, 934, 5)):
            n = len(points)
            self.ref[y:y+h, x:x+w] = True
            points.extend(((x, y), (x+w, y), (x+w, y+h), (x, y+h)))
            faces.extend(((n, n+1, n+2), (n, n+2, n+3)))
        self.pixels = np.array(points, dtype=float)
        self.faces = np.array(faces)
        self.truth = {"params": [0, 0, 0, 28], "offset": [512, 256], "scale": 3400}
        distance = .5 / np.tan(np.deg2rad(14))
        xy = (self.pixels - self.truth["offset"]) * distance / self.truth["scale"]
        self.vertices = np.column_stack((-xy, np.zeros(len(xy))))

    def test_known_thin_members_at_native_resolution(self):
        exact = rasterize(pixel_vertices(self.vertices, self.truth), self.faces, self.ref.shape)
        self.assertEqual(overlap(self.ref, exact), 1.)
        fitted = fit_frame_camera(self.vertices, self.faces, self.ref, 28.)
        native = rasterize(pixel_vertices(self.vertices, fitted), self.faces, self.ref.shape)
        self.assertGreaterEqual(overlap(self.ref, native), .97)

    def test_filled_opening_and_broken_bar(self):
        self.assertFalse(opening_errors(self.ref, self.ref))
        broken = self.ref.copy()
        broken[140:150, 500:520] = False
        self.assertTrue(opening_errors(self.ref, broken))
        filled = self.ref.copy()
        filled[65:145, 45:979] = True
        self.assertTrue(opening_errors(self.ref, filled))
        feet = np.array([[41, 300], [983, 300]])
        self.assertFalse(span_errors(self.ref, self.pixels, self.vertices, self.faces, feet))
        no_middle = np.delete(self.faces, [6, 7], axis=0)
        self.assertTrue(span_errors(self.ref, self.pixels, self.vertices, no_middle, feet))

    def test_mounts_preserve_rise_and_pivot(self):
        marks = np.array([[7., 8., 1.], [10., 8., 3.], [7., 8., 2.]])
        t = mounting_transform(marks, 3.)
        np.testing.assert_allclose(marks @ t[:3, :3].T + t[:3, 3], [[0, 0, 0], [3, 0, 2], [0, 0, 1]])
        with self.assertRaises(ValueError):
            validate_mounts({"lowerFoot": [0, 0], "upperFoot": [0, 0], "postTop": [.2, .5], "riseM": 2}, 3)

    def test_landmark_must_hit_a_surface(self):
        sample = [42., 300.]
        hit = resolve_anchor(self.vertices, self.faces, self.pixels, sample, self.truth)
        np.testing.assert_allclose(pixel_vertices(hit[None], self.truth)[0], sample)
        with self.assertRaisesRegex(ValueError, "misses"):
            resolve_anchor(self.vertices, self.faces, self.pixels, [512., 400.], self.truth)

    def test_undersides_set_the_pivot_and_independently_measure_the_game_feet(self):
        feet = np.array([[offset+x, y, bottom+z] for offset, bottom in ((0, .02), (3, 2.02))
                         for x in (-.05, .05) for y in (-.08, .08) for z in (0, .03)])
        transform = seat_transform(feet, np.eye(4), 3.)
        placed = feet @ transform[:3, :3].T + transform[:3, 3]
        measured, reasons = measure_seats(placed, 3., 2.)
        self.assertEqual(reasons, [])
        np.testing.assert_allclose(measured["lower_foot_m"], [0, 0, 0], atol=1e-9)
        placed[placed[:, 0] > 2, 2] -= .04
        self.assertTrue(measure_seats(placed, 3., 2.)[1])

    def test_thin_bars_receive_greater_reduction_protection_than_broad_faces(self):
        mask = self.ref.copy()
        mask[345:495, 31:171] = True
        weights = reduction_weights(mask)
        self.assertGreater(weights[145, 500], weights[420, 100])

    def test_reference_socket_error_is_reported_in_metres_before_acquisition(self):
        from PIL import Image
        from check_socket_layout import measure
        from project_reference import sha256
        with tempfile.TemporaryDirectory() as tmp:
            picture = Path(tmp) / "upright.png"
            Image.new("RGB", (200, 400), "white").save(picture)
            spec = {"picture": str(picture), "picture_sha256": sha256(picture), "top_y": .1,
                    "bottom_y": .9, "height_m": 1., "tolerance_m": .02,
                    "sockets": [{"name": "lower rod", "centre": [.5, .5], "height_m": .5}]}
            self.assertTrue(measure(spec)[1]["ok"])
            spec["sockets"][0]["centre"][1] = .44
            result = measure(spec)[1]
            self.assertFalse(result["ok"])
            self.assertAlmostEqual(result["sockets"][0]["measured_m"]["reference"], .575)
            spec["picture_sha256"] = "from another revision"
            with self.assertRaisesRegex(ValueError, "different reference"):
                measure(spec)

    @unittest.skipUnless(os.environ.get("RAC_BLENDER") and importlib.util.find_spec("trimesh"),
                         "optional Blender round trip")
    def test_real_blender_rebuilds_a_game_member_lost_from_a_sound_dense_control(self):
        import trimesh
        from PIL import Image
        from run_pixal_geometry import recover_frame_reduction, sha256
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dense = root / "pixal.glb"
            game = root / "pixal-v1000.glb"
            trimesh.Trimesh(self.vertices, self.faces, process=False).export(dense)
            trimesh.Trimesh(self.vertices, np.delete(self.faces, [6, 7], axis=0), process=False).export(game)
            alpha = Image.fromarray(self.ref.astype(np.uint8)*255)
            reference = Image.new("RGBA", alpha.size, "white")
            reference.putalpha(alpha)
            reference.save(root / "cutout.png")
            (root / "pixal.log").write_text("known camera", encoding="utf-8")
            mounts = {"lowerFoot": [41/1024, 309/512], "upperFoot": [983/1024, 309/512],
                      "postTop": [41/1024, 45/512], "runM": 3., "riseM": 0.}
            before = frame_check(root, game, mounts, camera=self.truth)
            self.assertFalse(before["ok"])
            self.assertTrue(all(reason.startswith("game") for reason in before["reasons"]))
            report = {"pixal": {}}
            args = SimpleNamespace(blender=os.environ["RAC_BLENDER"], vertex_target=1000)
            after = recover_frame_reduction(args, root, game, before, mounts, report)
            self.assertTrue(after["ok"], after["reasons"])
            self.assertEqual(report["pixal"]["game_sha256"], sha256(game))
            self.assertTrue((root / "protected-reduction" / "original-game.glb").is_file())
