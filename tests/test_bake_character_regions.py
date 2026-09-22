"""Reject stale paint/UV pairings before opening or mutating an authority."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import numpy as np

SPEC = importlib.util.spec_from_file_location('bake_character_regions', Path(__file__).resolve().parents[1] / 'scripts/blender/bake_character_regions.py')
BAKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BAKE)


class RegionalPaintContracts(unittest.TestCase):
    def test_clothing_paint_fades_across_uv_split_at_cuff_join(self):
        # Vertices 1/3 and 2/4 share positions but not UV indices at a cuff.
        points = [[-1, 0, 0], [0, 0, 0], [0, 1, 0],
                  [0, 0, 0], [0, 1, 0], [1, 0, 0], [3, 0, 0]]
        faces = [[0, 1, 2], [3, 5, 4], [4, 5, 6]]
        weights = BAKE.clothing_paint_weights(points, faces, ['skin', 'clothing', 'clothing'], 2)
        np.testing.assert_allclose(weights[[1, 2, 3, 4, 5, 6]], [0, 0, 0, 0, .5, 1])

    def test_height_cut_does_not_allow_head_paint_to_recolor_vest_shoulders(self):
        # The real regression: a high shoulder shares the head's atlas but is
        # still wardrobe. The neck joins gradually; the face keeps full detail.
        heights = np.array([1.58, 1.55, 1.70, 1.50])
        skin_weights = np.array([.1, 1., 1., 1.])
        weights = BAKE.head_paint_weights(heights, skin_weights, 1.53, .04)
        np.testing.assert_allclose(weights, [0., .5, 1., 0.])

    def test_skin_is_dielectric_and_clothing_can_keep_metal_fasteners(self):
        self.assertEqual(BAKE.material_policy('skin')['metallic'], 0)
        self.assertEqual(BAKE.material_policy('head')['roughness_floor'], .55)
        self.assertIsNone(BAKE.material_policy('clothing')['metallic'])

    def test_changed_layout_and_changed_map_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            paint = Path(directory) / 'paint.png'
            report.write_text('source UV receipt')
            paint.write_bytes(b'pinned-paint')
            config = {'layout_report_sha256': BAKE.sha(report),
                      'maps': {'head': {'BaseColor': {'path': str(paint), 'sha256': BAKE.sha(paint)}}}}
            BAKE.verify_paint_config(config, report)
            paint.write_bytes(b'changed-paint')
            with self.assertRaisesRegex(ValueError, 'changed paint'):
                BAKE.verify_paint_config(config, report)
            report.write_text('different UV receipt')
            with self.assertRaisesRegex(ValueError, 'different UV authority'):
                BAKE.verify_paint_config(config, report)

    def test_unknown_atlas_cannot_silently_drop_a_paint_override(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / 'report.json'
            report.write_text('layout')
            with self.assertRaisesRegex(ValueError, 'Unknown atlas'):
                BAKE.verify_paint_config({'layout_report_sha256': BAKE.sha(report), 'maps': {'typo': {}}}, report)
