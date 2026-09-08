import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_texture_sampling import surface_colours
from gate_texture import sample_triangle_colours
from repair_workshop_interiors import triangle_pixels


class TextureSamplingDiagnosticTests(unittest.TestCase):
    def test_surface_sampler_excludes_bounding_rectangle_neighbors(self):
        uv = np.array([[[.1,.1],[.9,.9],[.85,.9]]])
        image = np.full((64,64,3), 240., dtype=float)
        yy, xx, _ = triangle_pixels(uv[0], 64)
        image[yy,xx] = [15,30,60]
        sampled, fallback = surface_colours(image, uv)
        np.testing.assert_array_equal(sampled[0], [15,30,60])
        self.assertEqual(fallback, 0)
        rectangle = sample_triangle_colours(image, uv, [0])
        self.assertGreater(np.max(np.abs(rectangle-sampled)), 20)

    def test_subpixel_triangle_uses_finite_centroid(self):
        uv = np.array([[[.5,.5],[.50001,.5],[.5,.50001]]])
        image = np.full((4,4,3), 70., dtype=float)
        sampled, fallback = surface_colours(image, uv)
        np.testing.assert_array_equal(sampled, [[70,70,70]])
        self.assertEqual(fallback, 1)
