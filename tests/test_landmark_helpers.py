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


HEIGHT = 1.7
SHOULDER = np.array([0.20, 0.0, 1.35])


def tube(start, direction, length, radius_at, step=0.002, around=24):
    """Rings of points along a straight limb piece; radius_at(distance) gives its radius there."""
    direction = direction / np.linalg.norm(direction)
    side = np.cross(direction, [0.0, 1.0, 0.0])
    side /= np.linalg.norm(side)
    other = np.cross(direction, side)
    angles = np.linspace(0, 2 * np.pi, around, endpoint=False)
    rings = [start + direction * d + radius_at(d) * (np.outer(np.cos(angles), side) + np.outer(np.sin(angles), other))
             for d in np.arange(0.0, length, step)]
    return np.vstack(rings)


def a_pose_arm(bend_deg=20.0, torso=True):
    """A left arm hanging 20 degrees out from the body: upper arm 22 cm, forearm 24 cm narrowing to the wrist, hand
    18 cm, the elbow bent forward by bend_deg, beside a torso it touches at the armpit. Returns the points, the
    fingertip, and the elbow and wrist as distances along the shoulder-to-fingertip line."""
    upper = np.array([np.sin(np.radians(20)), 0.0, -np.cos(np.radians(20))])
    fore = upper + np.tan(np.radians(bend_deg)) * np.array([0.0, -1.0, 0.0])
    fore /= np.linalg.norm(fore)
    elbow = SHOULDER + upper * 0.22
    wrist = elbow + fore * 0.24
    tip = wrist + fore * 0.18
    parts = [tube(SHOULDER, upper, 0.22, lambda d: 0.040),
             tube(elbow, fore, 0.24, lambda d: 0.040 - 0.018 * d / 0.24),
             tube(wrist, fore, 0.18, lambda d: min(0.022 + 0.018 * d / 0.06, 0.040))]
    if torso:      # a block of body from the midline out to where the arm leaves it
        x, y, z = np.meshgrid(np.arange(0.0, 0.171, 0.005), np.arange(-0.10, 0.101, 0.005), np.arange(0.90, 1.50, 0.005))
        parts.append(np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1))
    axis = (tip - SHOULDER) / np.linalg.norm(tip - SHOULDER)
    return np.vstack(parts), tip, float((elbow - SHOULDER) @ axis), float((wrist - SHOULDER) @ axis)


class MeasuredArmTests(unittest.TestCase):
    """--arm-joints measured: the elbow and wrist found on the arm (Remora's template elbow sat 8 cm low)."""
    LATERAL = np.array([1.0, 0.0, 0.0])

    def test_sample_triangles_covers_the_face_the_same_way_every_time(self):
        tri = np.array([[[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]], float)
        points = humanoid.sample_triangles(tri, 0.005)
        self.assertIn(len(points), (200, 201))                  # 50 cm2 of face, one point per 0.25 cm2 (rounded up)
        self.assertTrue(np.all(points[:, 2] == 0) and np.all(points[:, :2] >= 0) and np.all(points[:, :2].sum(axis=1) <= 0.1 + 1e-12))
        np.testing.assert_array_equal(points, humanoid.sample_triangles(tri, 0.005))

    def test_two_line_break_finds_the_corner(self):
        leg_a = np.stack([np.zeros(10), np.zeros(10), -0.01 * np.arange(10)], axis=1)
        leg_b = leg_a[-1] + np.stack([np.zeros(10), -0.005 * np.arange(1, 11), -0.00866 * np.arange(1, 11)], axis=1)
        index, bend, ratio = humanoid.two_line_break(np.vstack([leg_a, leg_b]))
        self.assertEqual(index, 9)
        self.assertAlmostEqual(bend, 30.0, delta=0.5)
        self.assertLess(ratio, 0.01)
        _, straight_bend, straight_ratio = humanoid.two_line_break(np.vstack([leg_a, leg_a[-1] + leg_a[1:]]))
        self.assertLess(straight_bend, 0.5)                     # nothing to find on a straight line

    def test_slices_leave_the_torso_out_once_there_is_a_gap(self):
        points, tip, _, _ = a_pose_arm()
        slices, total = humanoid.arm_slices(points, SHOULDER, tip, self.LATERAL, HEIGHT)
        self.assertAlmostEqual(total, float(np.linalg.norm(tip - SHOULDER)))
        at = {round(s["t"], 3): s for s in slices if s}
        self.assertTrue(at[0.015]["merged"])                    # at the armpit the arm and the body are one piece
        mid_upper = at[0.155]
        self.assertFalse(mid_upper["merged"])
        self.assertAlmostEqual(mid_upper["wide"], 0.08, delta=0.01)   # the arm's own 8 cm, not the body beside it
        self.assertAlmostEqual(mid_upper["deep"], 0.08, delta=0.01)

    def test_elbow_at_the_bend_and_wrist_past_the_thinnest_girth(self):
        points, tip, elbow_t, wrist_t = a_pose_arm()
        got = humanoid.measure_arm(points, SHOULDER, tip, self.LATERAL, HEIGHT)
        self.assertTrue(got["elbow_measured"] and got["wrist_measured"])
        self.assertAlmostEqual(got["elbow_t"], elbow_t, delta=0.015)
        self.assertAlmostEqual(got["elbow_bend_deg"], 20.0, delta=3.0)
        self.assertAlmostEqual(got["thinnest_t"], wrist_t, delta=0.015)
        self.assertAlmostEqual(got["wrist_t"], got["thinnest_t"] + humanoid.WRIST_PAST_THINNEST * HEIGHT)
        centre = humanoid.centre_at(got["slices"], got["elbow_t"])
        upper = np.array([np.sin(np.radians(20)), 0.0, -np.cos(np.radians(20))])
        np.testing.assert_allclose(centre, SHOULDER + upper * 0.22, atol=0.015)    # in the middle of the arm, at the elbow

    def test_a_straight_arm_has_no_elbow_to_find(self):
        points, tip, _, wrist_t = a_pose_arm(bend_deg=0.0)
        got = humanoid.measure_arm(points, SHOULDER, tip, self.LATERAL, HEIGHT)
        self.assertFalse(got["elbow_measured"])
        self.assertIn("no bend", got["notes"][0])
        self.assertTrue(got["wrist_measured"])                  # the wrist is still there to measure
        self.assertAlmostEqual(got["thinnest_t"], wrist_t, delta=0.02)

    def test_both_arms_get_the_same_shares(self):
        left = {"total": 0.60, "elbow_measured": True, "elbow_t": 0.18, "elbow_error_ratio": 0.0,
                "wrist_measured": True, "wrist_t": 0.42}
        right = {"total": 0.62, "elbow_measured": True, "elbow_t": 0.217, "elbow_error_ratio": 0.5,
                 "wrist_measured": False}
        arms = humanoid.reconcile_arms({"l": left, "r": right, "x": None})
        self.assertAlmostEqual(left["elbow_share"], (0.30 * 1.0 + 0.35 * 0.5) / 1.5)     # the clearer bend counts for more
        self.assertEqual(left["elbow_share"], right["elbow_share"])
        self.assertAlmostEqual(right["wrist_share"], 0.70)      # the unmeasured wrist takes the other arm's
        self.assertIsNone(arms["x"])
        none = humanoid.reconcile_arms({"l": {"total": 0.6, "elbow_measured": False, "wrist_measured": False}})
        self.assertIsNone(none["l"]["elbow_share"])


def ball(centre, radius, count=6000):
    """Points spread evenly over a sphere."""
    k = np.arange(count) + 0.5
    polar, turn = np.arccos(1 - 2 * k / count), np.pi * (1 + 5 ** 0.5) * k
    return centre + radius * np.stack([np.cos(turn) * np.sin(polar), np.sin(turn) * np.sin(polar), np.cos(polar)], axis=1)


class MeasuredShoulderTests(unittest.TestCase):
    """--arm-joints measured_shoulder: the joint found in the shoulder (Remora's template one sat 2 cm low and 2-5 cm
    outside it, so the cap of her shoulder stayed with the collarbone and the arm hinged underneath)."""
    LATERAL = np.array([1.0, 0.0, 0.0])
    UPPER = np.array([np.sin(np.radians(20)), 0.0, -np.cos(np.radians(20))])

    def shoulder(self):
        points, tip, _, _ = a_pose_arm()
        cap = ball(SHOULDER, 0.045)
        cap = cap[(cap - SHOULDER) @ -self.UPPER > -0.02]                   # a rounded shoulder over the top of the arm,
        points = np.vstack([points, cap])                                   # with no surface inside the arm
        template = SHOULDER + self.UPPER * 0.04 + np.array([0.02, 0.0, 0.0])      # 4 cm down the arm and 2 cm outside it
        got = humanoid.measure_arm(points, template, tip, self.LATERAL, HEIGHT)
        humanoid.reconcile_arms({"l": got})
        return points, got, template

    def test_clearance_is_the_nearest_surface_along_a_line(self):
        points = ball(np.zeros(3), 0.05)
        self.assertAlmostEqual(humanoid.clearance(points, np.zeros(3), np.array([0.0, 0.0, 1.0]), 0.01), 0.05, delta=0.002)
        self.assertAlmostEqual(humanoid.clearance(points, np.array([0.02, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]), 0.01), 0.03, delta=0.002)
        self.assertIsNone(humanoid.clearance(points, np.array([0.0, 0.0, 0.2]), np.array([0.0, 0.0, 1.0]), 0.01))

    def test_the_joint_is_found_in_the_middle_of_the_shoulder(self):
        points, got, template = self.shoulder()
        point, facts = humanoid.measure_shoulder(points, got, template, 1.0, HEIGHT)
        self.assertIsNotNone(point, facts)
        np.testing.assert_allclose(point, SHOULDER, atol=0.012)             # the template was 4.5 cm away
        self.assertAlmostEqual(facts["under_top_cm"], 4.5, delta=1.0)       # as far under the top as in from the side
        self.assertAlmostEqual(facts["under_top_cm"], facts["in_from_side_cm"], delta=0.8)
        self.assertAlmostEqual(facts["from_template_cm"], 4.5, delta=1.2)

    def test_an_arm_that_is_not_clear_of_the_body_is_refused(self):
        points, got, template = self.shoulder()
        got = dict(got, slices=got["slices"][:3])
        point, why = humanoid.measure_shoulder(points, got, template, 1.0, HEIGHT)
        self.assertIsNone(point)
        self.assertIn("clear of the body", why)

    def test_both_shoulders_end_level(self):
        templates = {"l": [0.18, 0.03, 1.35], "r": [-0.18, 0.03, 1.35]}
        both = humanoid.reconcile_shoulders({"l": [0.137, 0.039, 1.364], "r": [-0.138, 0.045, 1.380]}, templates)
        np.testing.assert_allclose(both["l"], [0.137, 0.042, 1.372])        # its own width, one height and one depth
        np.testing.assert_allclose(both["r"], [-0.138, 0.042, 1.372])
        one = humanoid.reconcile_shoulders({"l": [0.14, 0.04, 1.38], "r": None}, templates)
        np.testing.assert_allclose(one["r"], [-0.14, 0.04, 1.38])           # the other arm's move, mirrored
        self.assertEqual(humanoid.reconcile_shoulders({"l": None, "r": None}, templates), {})


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
