import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gate_texture import sample_repeat_triangle_colours, repeat_uv_islands


class RepeatTextureSamplingTests(unittest.TestCase):
    def test_integer_translation_preserves_repeated_sample(self):
        rgb = np.arange(32 * 32 * 3).reshape(32, 32, 3).astype(float)
        uv = np.array([[[.13, .17], [.34, .21], [.2, .4]]])
        a = sample_repeat_triangle_colours(rgb, uv, [0])
        b = sample_repeat_triangle_colours(rgb, uv + [-3, 5], [0])
        np.testing.assert_array_equal(a, b)

    def test_wrap_does_not_clamp_to_border(self):
        rgb = np.zeros((16, 16, 3))
        rgb[:, 3:9] = 200
        uv = np.array([[[2.25, -.5], [2.27, -.5], [2.25, -.47]]])
        np.testing.assert_array_equal(sample_repeat_triangle_colours(rgb, uv, [0]), [[200, 200, 200]])

    def test_islands_use_unwrapped_edges(self):
        uv = np.array([[[0, 0], [2, 0], [0, 2]],
                       [[2, 0], [2, 2], [0, 2]],
                       [[10, 10], [11, 10], [10, 11]]], dtype=float)
        self.assertEqual(repeat_uv_islands(uv, [0, 1, 2])['islands'], 2)

    def test_nonfinite_uvs_refused(self):
        uv = np.full((1, 3, 2), np.nan)
        with self.assertRaises(ValueError):
            sample_repeat_triangle_colours(np.zeros((4, 4, 3)), uv, [0])
