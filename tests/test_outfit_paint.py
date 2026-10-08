"""The outfit-paint stage's pure pieces: Lab rules, the neighbour vote, tileable detail normals.

The stage itself needs a body build; the garment rules, the mesh vote and the
procedural detail it builds on are exercised here on small fixtures.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from refine_outfit_paint import (  # noqa: E402
    CLOTH,
    DEFAULTS,
    FABRIC,
    LEATHER,
    SKIN,
    classify,
    height_to_normal,
    leather_height,
    srgb_to_lab,
    vote,
    weave_height,
)


def rgb(*c):
    return np.array([c], float) / 255.0


# A character's garment gates, as a profile gives them (profiles/outfit-paint/).
GATED = dict(DEFAULTS, cloth_box_m={"abs_x": 0.17, "z": [0.17, 0.62], "max_y": 0.02}, cloth_max_L=27.0,
             skin_region_m={"min_abs_x": 0.58, "neck_abs_x": 0.09, "neck_min_z": 0.58}, skin_region_min_L=34.0,
             hands_beyond_abs_x_m=0.8)


class LabTests(unittest.TestCase):
    def test_white_and_black(self):
        np.testing.assert_allclose(srgb_to_lab(np.array([[1.0, 1.0, 1.0]]))[0], [100, 0, 0], atol=0.05)
        np.testing.assert_allclose(srgb_to_lab(np.array([[0.0, 0.0, 0.0]]))[0], [0, 0, 0], atol=1e-6)


class ClassifyTests(unittest.TestCase):
    def cls(self, colour, centroid, params=GATED):
        return int(classify(srgb_to_lab(colour), np.array([centroid], float), params)[0])

    def test_garments(self):
        forearm, chest, thigh = (0.7, -0.1, 0.4), (0.0, -0.15, 0.35), (0.12, -0.1, -0.3)
        self.assertEqual(self.cls(rgb(190, 125, 90), forearm), SKIN)
        self.assertEqual(self.cls(rgb(170, 45, 38), chest), FABRIC)
        self.assertEqual(self.cls(rgb(95, 62, 45), thigh), LEATHER)
        self.assertEqual(self.cls(rgb(52, 46, 44), chest), CLOTH)

    def test_skin_only_where_bare(self):
        # A worn, skin-coloured highlight on the trousers is leather, not skin.
        self.assertEqual(self.cls(rgb(190, 125, 90), (0.12, -0.1, -0.3)), LEATHER)
        # A grey patch on the trousers is worn leather; cloth is the shirt and vest only.
        self.assertEqual(self.cls(rgb(52, 46, 44), (0.12, -0.1, -0.3)), LEATHER)

    def test_hands_are_skin(self):
        self.assertEqual(self.cls(rgb(60, 40, 30), (0.9, 0.0, 0.4)), SKIN)

    def test_ungated_defaults_use_colour_alone(self):
        self.assertEqual(self.cls(rgb(190, 125, 90), (0.12, -0.1, -0.3), DEFAULTS), SKIN)
        self.assertEqual(self.cls(rgb(52, 46, 44), (0.12, -0.1, -0.3), DEFAULTS), CLOTH)
        self.assertEqual(self.cls(rgb(60, 40, 30), (0.9, 0.0, 0.4), DEFAULTS), LEATHER)


class VoteTests(unittest.TestCase):
    def test_isolated_speck_joins_its_neighbours(self):
        # A fan of 6 triangles around vertex 0; the middle one is the odd class out.
        tris = np.array([[0, k, k % 6 + 1] for k in range(1, 7)])
        cls = np.array([LEATHER, LEATHER, CLOTH, LEATHER, LEATHER, LEATHER])
        out = vote(cls, tris, np.ones(6), 2, np.zeros(6, bool))
        self.assertTrue((out == LEATHER).all())

    def test_locked_triangles_keep_their_class(self):
        tris = np.array([[0, k, k % 6 + 1] for k in range(1, 7)])
        cls = np.array([LEATHER, LEATHER, SKIN, LEATHER, LEATHER, LEATHER])
        locked = cls == SKIN
        out = vote(cls, tris, np.ones(6), 3, locked)
        self.assertEqual(out[2], SKIN)


class DetailTests(unittest.TestCase):
    def test_flat_height_is_a_flat_normal(self):
        n = height_to_normal(np.zeros((8, 8)), 3.0)
        self.assertTrue((n == [128, 128, 255]).all())

    def assert_tiles(self, h):
        # The wrap seam is no rougher than the tile's interior.
        seam = np.abs(h[:, 0] - h[:, -1]).mean() + np.abs(h[0] - h[-1]).mean()
        inner = np.abs(np.diff(h, axis=1)).mean() + np.abs(np.diff(h, axis=0)).mean()
        self.assertLess(seam, 1.5 * inner)

    def test_leather_tiles(self):
        self.assert_tiles(leather_height(128, 300, 10, np.random.default_rng(1)))

    def test_weave_tiles_and_repeats(self):
        h = weave_height(128, 16, np.random.default_rng(1))
        self.assert_tiles(h)
        self.assertGreater(h.std(), 0.1)

    def test_seeded(self):
        a = leather_height(64, 100, 5, np.random.default_rng(7))
        b = leather_height(64, 100, 5, np.random.default_rng(7))
        np.testing.assert_array_equal(a, b)


if __name__ == "__main__":
    unittest.main()
