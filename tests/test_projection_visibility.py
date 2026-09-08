import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from projection_visibility import project_surface, raster_depth, depth_visible


class ProjectionVisibilityTests(unittest.TestCase):
    def test_projection_uses_world_barycentric_depth(self):
        screen, depth = project_surface(np.array([[.5, .5, 0]]),
                                       np.array([[0, 0], [10, 0], [0, 10]]),
                                       np.array([1, 2, 1]))
        np.testing.assert_allclose(screen, [[20 / 3, 0]])
        np.testing.assert_allclose(depth, [1.5])

    def test_nearer_triangle_occludes_farther_surface(self):
        tri = np.array([[0., 0.], [8., 0.], [0., 8.]])
        buffer = raster_depth(np.array([tri, tri]), np.array([[2., 2., 2.], [1., 1., 1.]]), 8)
        self.assertAlmostEqual(buffer[1, 1], 1)
        visible = depth_visible(np.array([[1.5, 1.5], [1.5, 1.5], [-1., 2.]]),
                                np.array([1., 2., 1.]), buffer, .001)
        self.assertEqual(visible.tolist(), [True, False, False])

    def test_depth_is_perspective_correct(self):
        tri = np.array([[[0., 0.], [8., 0.], [0., 8.]]])
        buffer = raster_depth(tri, np.array([[1., 2., 1.]]), 8)
        self.assertAlmostEqual(buffer[1, 1], 1 / (1 - 1.5 / 16))

    def test_empty_depth_is_not_visible(self):
        result = depth_visible(np.array([[1., 1.]]), np.array([1.]),
                               np.full((3, 3), np.inf), .001)
        self.assertFalse(result.any())
