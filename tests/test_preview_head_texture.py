"""The unlit head-texture preview: which triangle wins a pixel, and the colour it reads."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from preview_head_texture import raster_uv, sample_uv, yaw_view  # noqa: E402


class PreviewTests(unittest.TestCase):
    def setUp(self):
        # Two squares facing the front camera (-y); the near one covers the left half of the far one.
        self.verts = np.array([[-0.05, -0.1, -0.05], [0.05, -0.1, -0.05], [0.05, -0.1, 0.05], [-0.05, -0.1, 0.05],
                               [-0.05, -0.2, -0.05], [0.0, -0.2, -0.05], [0.0, -0.2, 0.05], [-0.05, -0.2, 0.05]])
        self.tris = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]])
        far, near = [0.25, 0.5], [0.75, 0.5]
        self.tri_uv = np.array([[far] * 3, [far] * 3, [near] * 3, [near] * 3], float)
        self.texture = np.zeros((4, 4, 3))
        self.texture[:, :2] = [1.0, 0.0, 0.0]   # u < 0.5: red
        self.texture[:, 2:] = [0.0, 0.0, 1.0]   # u > 0.5: blue

    def test_front_view_keeps_the_nearer_surface(self):
        px, depth = yaw_view(self.verts, np.zeros(3), 0.0, 1000.0, 120)
        img = sample_uv(self.texture, raster_uv(px, depth, self.tris, self.tri_uv, (120, 120)))
        np.testing.assert_allclose(img[60, 40], [0.0, 0.0, 1.0])   # near square (left half)
        np.testing.assert_allclose(img[60, 80], [1.0, 0.0, 0.0])   # far square shows on the right
        np.testing.assert_allclose(img[5, 5], [0.25, 0.25, 0.25])  # backdrop off the mesh

    def test_side_view_puts_the_face_on_the_left(self):
        # Seen from +x (yaw 90) the -y side, where a face looks, is on the image's left.
        px, _ = yaw_view(self.verts, np.zeros(3), 90.0, 1000.0, 400)
        self.assertLess(px[4:, 0].mean(), px[:4, 0].mean())


if __name__ == "__main__":
    unittest.main()
