"""How a bake's coverage is measured and repaired, without starting Blender.

Blender 5.2.2's bake leaves alpha opaque on texels the rays never reached
(every texel of a normal map; every missed texel within the margin's reach), so
coverage comes from a white coverage pass instead. What is left to test here is
the arithmetic around it: which texels are island, what the fill writes, and
how a receipt accounts for every texel the rays missed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "blender"))

from bake_coverage import (  # noqa: E402
    FILL_ROUNDS,
    coverage_summary,
    fill_reach,
    fill_unbaked,
    rasterize,
)
from scripts.build_production import bake_reached_islands  # noqa: E402


def reference_raster(tri_uv, raster):
    """Texel centres strictly inside each triangle, one triangle and texel at a time."""
    counts = np.zeros((raster, raster), dtype=np.int32)
    centres = (np.arange(raster) + 0.5) / raster
    u, v = np.meshgrid(centres, centres, indexing="xy")
    for a, b, c in tri_uv:
        def edge(p, q):
            return (q[0] - p[0]) * (v - p[1]) - (q[1] - p[1]) * (u - p[0])
        e1, e2, e3 = edge(a, b), edge(b, c), edge(c, a)
        counts += ((e1 > 0) & (e2 > 0) & (e3 > 0)) | ((e1 < 0) & (e2 < 0) & (e3 < 0))
    return counts


class RasterizeTests(unittest.TestCase):
    def test_agrees_with_a_brute_force_raster_for_small_large_and_clipped_triangles(self):
        rng = np.random.default_rng(20261004)
        small = rng.uniform(0.0, 1.0, (200, 1, 2)) + rng.normal(0.0, 0.03, (200, 3, 2))
        large = rng.uniform(-0.3, 1.3, (25, 3, 2))
        triangles = np.concatenate([small, large])
        np.testing.assert_array_equal(rasterize(triangles, 64), reference_raster(triangles, 64))

    def test_counts_overlaps_and_ignores_what_lies_off_the_sheet(self):
        inside = [[0.1, 0.1], [0.9, 0.1], [0.1, 0.9]]
        off_sheet = [[1.2, 1.2], [1.8, 1.2], [1.2, 1.8]]
        counts = rasterize(np.array([inside, inside, off_sheet]), 32)
        self.assertEqual(counts.max(), 2)
        self.assertEqual(int((counts == 1).sum()), 0)
        self.assertEqual(counts[0, 0], 0)

    def test_rows_start_at_the_bottom_like_blender_images(self):
        bottom_band = np.array([[[0.0, 0.0], [1.0, 0.0], [0.0, 0.2]]])
        counts = rasterize(bottom_band, 10)
        self.assertGreater(int(counts[0].sum()), 0)
        self.assertEqual(int(counts[-1].sum()), 0)

    def test_no_triangles_or_degenerate_ones_cover_nothing(self):
        self.assertFalse(rasterize(np.empty((0, 3, 2)), 16).any())
        sliver = np.array([[[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]]])
        self.assertFalse(rasterize(sliver, 16).any())


def sheet(written, colour=(0.2, 0.4, 0.6)):
    """A bake result: ``colour`` where it wrote, the clear black elsewhere, alpha the mask."""
    pixels = np.zeros(written.shape + (4,), dtype=np.float32)
    pixels[written, :3] = colour
    pixels[..., 3] = written
    return pixels


class FillTests(unittest.TestCase):
    def test_a_hole_takes_its_neighbours_colour_and_is_counted(self):
        written = np.ones((16, 16), dtype=bool)
        written[6:9, 6:9] = False
        pixels = sheet(written)
        self.assertEqual(fill_unbaked(pixels), 9)
        np.testing.assert_allclose(pixels[6:9, 6:9, :3], np.full((3, 3, 3), (0.2, 0.4, 0.6)),
                                   rtol=1e-6)
        self.assertTrue((pixels[..., 3] == 1.0).all())

    def test_counts_only_what_it_reaches_not_everything_unwritten(self):
        written = np.zeros((32, 32), dtype=bool)
        written[:, :2] = True
        pixels = sheet(written)
        # Two rounds reach columns 2-3 and, wrapping round the sheet's edge,
        # columns 30-31; the middle stays at the clear colour.
        self.assertEqual(fill_unbaked(pixels, rounds=2), 4 * 32)
        self.assertTrue((pixels[:, 4:30, :3] == 0.0).all())
        self.assertTrue((pixels[:, 2:4, :3] > 0.0).all())

    def test_counted_within_the_islands_the_gutter_it_grows_into_is_left_out(self):
        written = np.zeros((16, 16), dtype=bool)
        written[:, :4] = True
        islands = np.zeros((16, 16), dtype=bool)
        islands[:, :6] = True
        pixels = sheet(written)
        # Three rounds reach columns 4-6 and, wrapping, 13-15; only 4 and 5
        # are island.
        self.assertEqual(fill_unbaked(pixels, rounds=3, within=islands), 2 * 16)
        self.assertTrue((pixels[:, 6, :3] > 0.0).all())
        self.assertTrue((pixels[:, 13, :3] > 0.0).all())

    def test_nothing_written_means_nothing_to_grow(self):
        pixels = sheet(np.zeros((8, 8), dtype=bool))
        self.assertEqual(fill_unbaked(pixels), 0)
        self.assertTrue((pixels[..., :3] == 0.0).all())

    def test_fill_reach_predicts_exactly_what_the_fill_writes(self):
        rng = np.random.default_rng(7)
        for rounds in (1, 3, FILL_ROUNDS):
            written = rng.random((40, 40)) > 0.97
            pixels = sheet(written, colour=(1.0, 1.0, 1.0))
            filled = fill_unbaked(pixels, rounds=rounds)
            changed = (pixels[..., 0] > 0.0) & ~written
            np.testing.assert_array_equal(fill_reach(written, rounds), changed)
            self.assertEqual(filled, int(changed.sum()))


class CoverageSummaryTests(unittest.TestCase):
    def test_every_missed_island_texel_is_accounted_for_once(self):
        islands = np.zeros((40, 40), dtype=bool)
        islands[5:35, 5:35] = True
        reached = islands.copy()
        reached[10:14, 10:14] = False          # small hole: the margin covers it
        reached[18:34, 18:34] = False          # large hole: margin rim, fill, then nothing
        written = reached.copy()
        written[10:14, 10:14] = True
        written[18:34, 18] = True
        summary = coverage_summary(islands, reached, written, rounds=3)
        self.assertEqual(summary["island_texels"], 900)
        self.assertEqual(summary["unreached_texels"], 16 + 256)
        self.assertEqual(summary["reached_texels"], 900 - 272)
        self.assertEqual(summary["reached_pct"], round(100.0 * 628 / 900, 2))
        self.assertEqual(summary["unreached_written_by_margin"], 16 + 16)
        # The large hole's unwritten 16x15 is walled by the margin column on
        # one side and reached texels on three; three rounds fill a ring three
        # deep and leave its 10x9 middle at the clear colour.
        self.assertEqual(summary["unreached_filled_from_neighbours"], 240 - 90)
        self.assertEqual(summary["unreached_left_unbaked"], 90)
        self.assertEqual(summary["unreached_written_by_margin"]
                         + summary["unreached_filled_from_neighbours"]
                         + summary["unreached_left_unbaked"], summary["unreached_texels"])

    def test_texels_outside_the_islands_do_not_count_as_missed(self):
        islands = np.zeros((20, 20), dtype=bool)
        islands[:10] = True
        summary = coverage_summary(islands, islands, islands)
        self.assertEqual(summary["reached_pct"], 100.0)
        self.assertEqual(summary["unreached_texels"], 0)

    def test_a_layout_with_no_island_texel_has_no_coverage_rather_than_zero(self):
        empty = np.zeros((8, 8), dtype=bool)
        self.assertIsNone(coverage_summary(empty, empty, empty)["reached_pct"])

    def test_masks_of_different_sizes_are_refused(self):
        with self.assertRaises(ValueError):
            coverage_summary(np.ones((8, 8)), np.ones((8, 8)), np.ones((16, 16)))


class BuildProductionReadingTests(unittest.TestCase):
    def test_reads_the_measured_share_of_the_islands(self):
        retopo = {"bake_coverage": {"reached_pct": 87.5},
                  "bake_coverage_pct": {"BaseColor": 87.5, "AO": 87.5, "Normal": 87.5}}
        self.assertEqual(bake_reached_islands(retopo), 0.875)

    def test_an_alpha_reading_from_before_the_coverage_pass_is_not_a_measurement(self):
        self.assertIsNone(bake_reached_islands({"bake_coverage_pct": {"BaseColor": 100.0}}))
        self.assertIsNone(bake_reached_islands({}))

    def test_takes_the_lowest_pass_and_ignores_unmeasured_ones(self):
        retopo = {"bake_coverage": {}, "bake_coverage_pct": {"AO": 95.0, "BaseColor": 91.0,
                                                             "Normal": None}}
        self.assertEqual(bake_reached_islands(retopo), 0.91)


if __name__ == "__main__":
    unittest.main()
