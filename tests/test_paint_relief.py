"""The normal derived from paint must not carry the atlas's own seams.

A texture is islands on a gutter. Read naively as height, every island edge is
a cliff, and a derived normal map outlines every UV island in the file -- which
on a generated character was hundreds of them, and looked like the face had
been drawn on triangles. These tests pin the behaviour that stops it, and the
scaling that keeps one strength meaning one relief across sheet sizes.

Plain numpy; no Blender.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "blender"))
from paint_relief import (  # noqa: E402
    coverage_at,
    fill_outside,
    normal_from_paint,
)

FLAT = np.array([0.5, 0.5, 1.0], dtype=np.float32)


def island_on_gutter(size=256, colour=0.8, gutter=0.0):
    """One flat island of paint in the middle of an unpainted sheet."""
    albedo = np.full((size, size, 3), gutter, dtype=np.float32)
    coverage = np.zeros((size, size), dtype=bool)
    lo, hi = size // 4, 3 * size // 4
    albedo[lo:hi, lo:hi] = colour
    coverage[lo:hi, lo:hi] = True
    return albedo, coverage


def tilt(encoded):
    """How far each texel's normal leans away from straight up."""
    return np.linalg.norm(encoded[..., :2] - 0.5, axis=2)


class SeamTests(unittest.TestCase):
    def test_an_island_edge_is_read_as_a_cliff_without_coverage(self):
        albedo, _ = island_on_gutter()
        encoded, _ = normal_from_paint(albedo, 0.3)
        # The very mistake: flat paint, and yet the normal leans along the edge.
        self.assertGreater(tilt(encoded).max(), 0.05)

    def test_with_coverage_flat_paint_gives_a_flat_normal_everywhere(self):
        albedo, coverage = island_on_gutter()
        encoded, local = normal_from_paint(albedo, 0.3, coverage=coverage)
        self.assertLess(tilt(encoded).max(), 1e-3)
        self.assertLess(local, 1e-4)

    def test_relief_inside_the_island_survives_the_fill(self):
        albedo, coverage = island_on_gutter()
        # A painted stripe well inside the island: this is what the derivation
        # is for, and the fill must not sand it away.
        albedo[120:136, 64:192] = 0.2
        encoded, local = normal_from_paint(albedo, 0.3, coverage=coverage)
        inside = tilt(encoded)[118:139, 64:192]
        self.assertGreater(inside.max(), 0.05)
        self.assertGreater(local, 1e-3)
        # And the gutter is still flat: nothing outside the paint tilts.
        self.assertTrue(np.allclose(encoded[~coverage][:, :3], FLAT, atol=1e-6))

    def test_texels_no_geometry_reaches_come_back_flat(self):
        albedo, coverage = island_on_gutter()
        rng = np.random.default_rng(3)
        albedo[~coverage] = rng.random((int((~coverage).sum()), 3))
        encoded, _ = normal_from_paint(albedo, 0.3, coverage=coverage)
        self.assertTrue(np.allclose(encoded[~coverage][:, :3], FLAT, atol=1e-6))


class ScaleTests(unittest.TestCase):
    def test_the_same_strength_raises_the_same_relief_on_a_larger_sheet(self):
        # The same weave at two sheet sizes: a sinusoid whose period is a
        # fixed fraction of the sheet, so the physical feature is identical.
        results = []
        for size in (1024, 2048):
            x = np.arange(size) / size
            wave = 0.5 + 0.3 * np.sin(2 * np.pi * x * 16)
            albedo = np.dstack([np.tile(wave, (size, 1))] * 3).astype(np.float32)
            encoded, _ = normal_from_paint(albedo, 0.3)
            results.append(tilt(encoded).max())
        small, large = results
        # Within a fifth. The blur is a box of 2r+1 texels, so its width is
        # not exactly proportional to the sheet, and the residual it leaves
        # in a fine weave differs by that odd texel; the gain itself scales.
        self.assertAlmostEqual(small, large, delta=0.2 * max(small, large))


class HelperTests(unittest.TestCase):
    def test_coverage_is_resampled_by_nearest_texel(self):
        mask = np.zeros((4, 4), dtype=bool)
        mask[1:3, 1:3] = True
        grown = coverage_at(mask, 8)
        self.assertEqual(grown.shape, (8, 8))
        self.assertTrue(grown[2:6, 2:6].all())
        self.assertFalse(grown[0].any())
        self.assertFalse(grown[:, 7].any())
        shrunk = coverage_at(grown, 4)
        self.assertTrue(np.array_equal(shrunk, mask))

    def test_the_fill_carries_edge_values_outward_and_no_further_than_asked(self):
        plane = np.zeros((16, 16), dtype=np.float32)
        coverage = np.zeros((16, 16), dtype=bool)
        plane[6:10, 6:10] = 1.0
        coverage[6:10, 6:10] = True
        filled = fill_outside(plane, coverage, 2)
        # Two texels out: reached, and carrying the island's value.
        self.assertEqual(filled[4, 8], 1.0)
        self.assertEqual(filled[8, 11], 1.0)
        # Beyond that: the covered mean, which here is also 1.0 -- so use a
        # sheet whose mean differs to tell the two apart.
        plane[6:10, 6:10] = np.linspace(0.0, 1.0, 16).reshape(4, 4)
        filled = fill_outside(plane, coverage, 2)
        self.assertAlmostEqual(float(filled[0, 0]), float(plane[coverage].mean()), places=5)

    def test_a_sheet_nothing_reaches_is_returned_unchanged(self):
        plane = np.arange(16, dtype=np.float32).reshape(4, 4)
        self.assertTrue(np.array_equal(fill_outside(plane, np.zeros((4, 4), bool), 3), plane))


if __name__ == "__main__":
    unittest.main()
