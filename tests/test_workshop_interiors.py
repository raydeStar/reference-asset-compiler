import unittest

import numpy as np

from scripts.repair_workshop_interiors import mirror_repeat, select_interior, triangle_pixels


class WorkshopInteriorTests(unittest.TestCase):
    def test_mug_preserves_outer_wall_rim_and_handle(self):
        centres = np.array([[-.028, 0, .007], [-.028, -.064, .06],
                            [-.028, -.072, .06], [-.028, -.064, .139], [.095, 0, .06]])
        normals = np.array([[0, 0, 1], [0, 1, 0], [0, -1, 0], [0, 1, 0], [-1, 0, 0]])
        self.assertEqual([True, True, False, False, False],
                         select_interior("sunset-mug", centres, normals).tolist())

    def test_bench_only_inward_cabinet_sides(self):
        centres = np.array([[-.27, 0, .4], [.27, 0, .4], [-.9, 0, .4], [-.27, -.4, .4]])
        normals = np.array([[1, 0, 0], [-1, 0, 0], [-1, 0, 0], [0, -1, 0]])
        self.assertEqual([True, True, False, False],
                         select_interior("sunset-workbench", centres, normals).tolist())

    def test_unknown_asset_cannot_inherit_geometric_selection(self):
        with self.assertRaises(ValueError):
            select_interior("unrelated", np.zeros((1, 3)), np.zeros((1, 3)))

    def test_barycentric_rasterizer_preserves_world_interpolation(self):
        uv = np.array([[0., 0.], [1., 0.], [0., 1.]])
        yy, xx, weights = triangle_pixels(uv, 16)
        self.assertTrue(np.allclose(weights.sum(axis=1), 1))
        self.assertTrue(np.all(weights >= -1e-7))
        projected = weights @ uv
        self.assertTrue(np.allclose(projected[:, 0], (xx + .5) / 16))
        self.assertTrue(np.allclose(projected[:, 1], 1 - (yy + .5) / 16))

    def test_material_repeat_is_continuous_and_bounded(self):
        samples = mirror_repeat(np.linspace(-4, 4, 1001))
        self.assertGreaterEqual(samples.min(), 0)
        self.assertLessEqual(samples.max(), 1)
        self.assertLess(np.abs(np.diff(samples)).max(), .01)


if __name__ == "__main__":
    unittest.main()
