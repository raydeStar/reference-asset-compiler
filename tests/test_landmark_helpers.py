"""Pure geometry helpers of the landmark derivation stages.

The stages run inside Blender, which supplies ``bpy`` and ``mathutils``. Only
the numpy helpers are exercised here, under stub modules, so a regression in
the centreline or slab maths is caught without a Blender round trip.
"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

import numpy as np

STAGES = Path(__file__).resolve().parents[1] / "scripts" / "blender"


def load_stage_without_blender(name):
    saved = {key: sys.modules.get(key) for key in ("bpy", "mathutils")}
    bpy = types.ModuleType("bpy")
    bpy.ops = bpy.data = bpy.context = types.SimpleNamespace()
    mathutils = types.ModuleType("mathutils")
    mathutils.Vector = tuple
    sys.modules["bpy"] = bpy
    sys.modules["mathutils"] = mathutils
    try:
        spec = importlib.util.spec_from_file_location(name, STAGES / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


humanoid = load_stage_without_blender("derive_humanoid_landmarks")
mascot = load_stage_without_blender("derive_mascot_landmarks")


def ring(z, count=4, radius=0.1):
    """Points arranged symmetrically around the z axis at one height; their mean is on the axis."""
    angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
    return np.stack([radius * np.cos(angles), radius * np.sin(angles), np.full(count, z)], axis=1)


class HumanoidHelperTests(unittest.TestCase):
    def test_slab_keeps_only_points_within_half_height(self):
        points = np.array([[0, 0, 0.0], [0, 0, 1.0], [0, 0, 1.05], [0, 0, 1.2], [0, 0, 2.0]])
        selected = humanoid.slab(points, 1.0, 0.1)
        np.testing.assert_allclose(sorted(selected[:, 2]), [1.0, 1.05])

    def test_centerline_bins_along_axis_and_accumulates_arc(self):
        points = np.vstack([ring(0.0), ring(0.5), ring(1.0), ring(1.5)])
        centres, arc = humanoid.centerline(points, points[:, 2], bins=4)
        self.assertEqual(centres.shape, (4, 3))
        np.testing.assert_allclose(centres[:, :2], 0, atol=1e-12)
        np.testing.assert_allclose(centres[:, 2], [0.0, 0.5, 1.0, 1.5])
        np.testing.assert_allclose(arc, [0.0, 0.5, 1.0, 1.5])

    def test_centerline_skips_bins_with_fewer_than_three_points(self):
        sparse = np.array([[0.3, 0, 0.5], [-0.3, 0, 0.5]])  # two points: not enough for a centroid
        points = np.vstack([ring(0.0), sparse, ring(1.0)])
        # Three bins over z in [0, 1]: the middle one holds only the two sparse points.
        centres, arc = humanoid.centerline(points, points[:, 2], bins=3)
        self.assertEqual(len(centres), 2)
        np.testing.assert_allclose(centres[:, 2], [0.0, 1.0])
        self.assertAlmostEqual(arc[-1], 1.0)

    def test_at_arc_interpolates_along_the_polyline(self):
        centres = np.array([[0, 0, 0.0], [0, 0, 1.0], [1, 0, 1.0]])
        arc = np.array([0.0, 1.0, 2.0])
        np.testing.assert_allclose(humanoid.at_arc(centres, arc, 0.0), [0, 0, 0])
        np.testing.assert_allclose(humanoid.at_arc(centres, arc, 0.5), [0, 0, 1])
        np.testing.assert_allclose(humanoid.at_arc(centres, arc, 0.75), [0.5, 0, 1])
        np.testing.assert_allclose(humanoid.at_arc(centres, arc, 1.0), [1, 0, 1])


class MascotHelperTests(unittest.TestCase):
    def test_slab_centroid_needs_eight_points(self):
        points = ring(1.0, count=7)
        self.assertIsNone(mascot.slab_centroid(points, 1.0, 0.05, x_window=1.0, x_center=0.0))
        centroid = mascot.slab_centroid(ring(1.0, count=8), 1.0, 0.05, x_window=1.0, x_center=0.0)
        np.testing.assert_allclose(centroid, [0, 0, 1.0], atol=1e-12)

    def test_slab_centroid_respects_the_x_window(self):
        left = ring(1.0, count=8) + np.array([-0.5, 0, 0])
        right = ring(1.0, count=8) + np.array([0.5, 0, 0])
        points = np.vstack([left, right])
        centroid = mascot.slab_centroid(points, 1.0, 0.05, x_window=0.2, x_center=0.5)
        np.testing.assert_allclose(centroid, [0.5, 0, 1.0], atol=1e-12)
        self.assertIsNone(mascot.slab_centroid(points, 1.0, 0.05, x_window=0.05, x_center=0.0))


if __name__ == "__main__":
    unittest.main()
