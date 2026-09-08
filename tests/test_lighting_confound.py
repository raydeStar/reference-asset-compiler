import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from diagnose_lighting_confound import split_covariance, controls


class LightingConfoundTests(unittest.TestCase):
    def test_covariance_decomposition_is_exact(self):
        rng = np.random.default_rng(52)
        result = split_covariance(rng.random(100), rng.random(100),
                                  rng.random(100), np.arange(100) % 4)
        self.assertLess(result["decomposition_absolute_error"], 1e-14)

    def test_unlit_palette_is_a_false_positive_and_shading_still_detected(self):
        result = controls()
        self.assertGreater(abs(result["unlit_multicolor_cube"]["correlation"]), .9)
        self.assertGreater(result["single_material_lambertian_positive_control"]["correlation"], .999)

    def test_constant_group_colors_have_only_between_covariance(self):
        result = split_covariance(np.array([1., 1., 3., 3.]), np.array([0., .2, .7, 1.]),
                                  np.ones(4), np.array([0, 0, 1, 1]))
        self.assertAlmostEqual(result["within_covariance"], 0)
        self.assertAlmostEqual(result["total_covariance"], result["between_covariance"])
