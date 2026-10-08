"""The face-paint refinement's pure pieces: colour round trips, lines, grain, probes.

The stage itself needs a conformed head and a guidance picture; what it builds
on -- Lab conversion, the smoothed landmark lines, the seeded hair grain, the
shell ray test and the blush measure -- is exercised here on small fixtures.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from refine_face_paint import (  # noqa: E402
    cheek_redness,
    is_skin,
    lab,
    lab_to_rgb,
    polyline,
    ray_hits,
    smoothstep,
    stubble_grain,
    to_linear,
    to_srgb,
)


class ColourTests(unittest.TestCase):
    def test_lab_round_trip(self):
        rng = np.random.default_rng(1)
        rgb = rng.uniform(0.02, 0.98, (500, 3))
        np.testing.assert_allclose(lab_to_rgb(lab(rgb)), rgb, atol=1e-6)

    def test_linear_round_trip(self):
        x = np.linspace(0, 1, 101)
        np.testing.assert_allclose(to_srgb(to_linear(x)), x, atol=1e-9)

    def test_skin_filter_rejects_hair_and_backdrop(self):
        pix = np.array([[0.85, 0.5, 0.3], [0.2, 0.1, 0.05], [0.62, 0.6, 0.58]])
        self.assertEqual(is_skin(pix).tolist(), [True, False, False])

    def test_smoothstep_ends_and_reversed_edges(self):
        self.assertEqual(float(smoothstep(0, 1, -1)), 0.0)
        self.assertEqual(float(smoothstep(0, 1, 2)), 1.0)
        self.assertEqual(float(smoothstep(1, 0, 0)), 1.0)


class LineTests(unittest.TestCase):
    def test_smoothing_keeps_ends_and_orders_knots(self):
        pts = np.array([[0, 0, 0], [0.01, 0.002, 0], [0.02, -0.002, 0], [0.03, 0, 0]], float)
        dense, tang, arc, knots = polyline(pts, step=0.0005, smooth=3)
        np.testing.assert_allclose(dense[0], pts[0])
        np.testing.assert_allclose(dense[-1], pts[-1], atol=1e-3)
        self.assertTrue(np.all(np.diff(knots) >= 0))
        np.testing.assert_allclose(np.linalg.norm(tang, axis=1), 1.0, atol=1e-6)
        # Corner cutting takes out the zigzag: the line stays closer to straight.
        self.assertLess(np.abs(dense[:, 1]).max(), 0.002)


class GrainTests(unittest.TestCase):
    def test_grain_is_seeded_and_local(self):
        rng = np.random.default_rng(3)
        pos = rng.uniform(0, 0.01, (4000, 3))
        a = stubble_grain(pos, 0.0006, 0.00022, 0.6, 7)
        b = stubble_grain(pos, 0.0006, 0.00022, 0.6, 7)
        c = stubble_grain(pos, 0.0006, 0.00022, 0.6, 8)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a, c))
        self.assertTrue((a >= 0).all() and (a <= 1).all())
        # Dots, not a wash: most points sit between hairs.
        self.assertLess(np.median(a), 0.5)
        self.assertGreater(a.max(), 0.9)

    def test_no_hairs_without_fill(self):
        pos = np.random.default_rng(4).uniform(0, 0.01, (500, 3))
        self.assertEqual(float(stubble_grain(pos, 0.0006, 0.00022, 0.0, 7).max()), 0.0)


class ShellTests(unittest.TestCase):
    def test_ray_meets_a_shell_above_only(self):
        verts = np.array([[-1, -1, 0.05], [1, -1, 0.05], [0, 1, 0.05]], float)
        faces = np.array([[0, 1, 2]])
        orig = np.zeros((3, 3))
        dirs = np.array([[0, 0, 1], [0, 0, -1], [0, 0, 1]], float)
        hit = ray_hits(orig, dirs, verts, faces, 0.12)
        self.assertEqual(hit.tolist(), [True, False, True])
        self.assertFalse(ray_hits(orig[:1], dirs[:1], verts, faces, 0.01)[0])


class BlushTests(unittest.TestCase):
    def test_cheek_redness_measures_a_red_patch(self):
        img = np.tile(np.array([0.85, 0.55, 0.35]), (200, 200, 1))
        discs = {"cheek": [((50, 50), 15)], "plain": [((150, 150), 15)]}
        flat = cheek_redness(img, discs, img.shape[:2])
        img[35:65, 35:65] = [0.9, 0.45, 0.33]
        red = cheek_redness(img, discs, img.shape[:2])
        self.assertAlmostEqual(flat, 0.0, places=6)
        self.assertGreater(red, 5.0)


if __name__ == "__main__":
    unittest.main()
