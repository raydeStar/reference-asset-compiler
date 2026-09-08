import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from calibrate_pbr_region import calibrate


class PbrRegionCalibrationTests(unittest.TestCase):
    def test_bounds_apply_only_inside_mask(self):
        rough = np.array([[20, 200], [100, 250]], dtype=np.uint8)
        metal = np.array([[240, 50], [150, 0]], dtype=np.uint8)
        mask = np.array([[True, False], [False, True]])
        r, m = calibrate(rough, metal, mask, .6, 0)
        np.testing.assert_array_equal(r, [[153, 200], [100, 250]])
        np.testing.assert_array_equal(m, [[0, 50], [150, 0]])
        self.assertEqual(rough[0, 0], 20)

    def test_refuses_misaligned_mask(self):
        a = np.zeros((2, 2), dtype=np.uint8)
        with self.assertRaises(ValueError):
            calibrate(a, a, np.zeros((4, 4), dtype=bool), .6, 0)

    def test_refuses_invalid_material_bounds(self):
        a = np.zeros((2, 2), dtype=np.uint8)
        with self.assertRaises(ValueError):
            calibrate(a, a, a.astype(bool), 1.5, 0)
