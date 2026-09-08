import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from map_face_donor import warp_coordinates, pad_face_gutters


class FaceMappingTests(unittest.TestCase):
    def setUp(self):
        self.landmarks = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [.4, .6]], float)

    def test_identity_registration_preserves_coordinates(self):
        points = np.array([[.2, .3], [.8, .5], [.4, .6]])
        mapped, valid = warp_coordinates(points, self.landmarks, self.landmarks)
        np.testing.assert_allclose(mapped, points, atol=1e-12)
        self.assertTrue(valid.all())

    def test_affine_registration_matches_paired_landmarks(self):
        donor = self.landmarks * [2, 3] + [5, 7]
        mapped, valid = warp_coordinates(self.landmarks, self.landmarks, donor)
        np.testing.assert_allclose(mapped, donor, atol=1e-12)
        self.assertTrue(valid.all())

    def test_outside_hull_cannot_be_transferred(self):
        _mapped, valid = warp_coordinates(np.array([[-1, .3], [2, 2], [.5, .5]]),
                                          self.landmarks, self.landmarks)
        self.assertEqual(valid.tolist(), [False, False, True])

    def test_padding_preserves_occupied_neighbors_and_radius(self):
        pixels = np.zeros((12, 12, 3), np.uint8)
        occupied = np.zeros((12, 12), bool)
        occupied[5, 4] = occupied[5, 7] = True
        pixels[5, 4] = [200, 100, 50]
        pixels[5, 7] = [10, 20, 30]
        support = np.zeros_like(occupied)
        support[5, 4] = True
        padded, mask = pad_face_gutters(pixels, occupied, support, 2)
        np.testing.assert_array_equal(padded[occupied], pixels[occupied])
        np.testing.assert_array_equal(padded[5, 5], pixels[5, 4])
        self.assertFalse(mask[5, 6])  # Nearest surface belongs to protected art.
        self.assertFalse(mask[5, 1])
        self.assertFalse((mask & occupied).any())

    def test_zero_padding_is_exact_noop(self):
        pixels = np.arange(75, dtype=np.uint8).reshape(5, 5, 3)
        occupied = np.zeros((5, 5), bool)
        occupied[2, 2] = True
        padded, mask = pad_face_gutters(pixels, occupied, occupied, 0)
        np.testing.assert_array_equal(padded, pixels)
        self.assertFalse(mask.any())
