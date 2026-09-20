from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.skeleton_fingerprint import (  # noqa: E402
    ALGORITHM,
    SkeletonFingerprintError,
    canonical_rotation,
    canonical_text,
    fingerprint_report,
    quantize,
    skeleton_fingerprint,
)

# Two joints, deliberately out of alphabetical order, with a rotation that is
# not the identity and a translation that lands exactly on a rounding boundary.
# A browser studio computing this from the same skeleton must produce the same
# hex string; both repositories assert against this vector.
SHARED_VECTOR = [
    {
        "name": "Spine",
        "parent": "Hips",
        "translation": (0.0, 0.1234565, 0.0),
        "rotation": (0.0, 0.0, 0.3826834, 0.9238795),
        "scale": (1.0, 1.0, 1.0),
    },
    {
        "name": "Hips",
        "parent": None,
        "translation": (0.0, 0.95, 0.0),
        "rotation": (0.0, 0.0, 0.0, 1.0),
        "scale": (1.0, 1.0, 1.0),
    },
]
SHARED_VECTOR_FINGERPRINT = "18c20df3170c39e2b00a889d44b9f38c2b6309aae636ce1e091e82736058d589"


class SkeletonFingerprintTests(unittest.TestCase):
    def test_canonical_text_orders_by_name_and_states_the_algorithm(self):
        text = canonical_text(SHARED_VECTOR)
        lines = text.splitlines()

        self.assertEqual(lines[0], ALGORITHM)
        # Hips sorts before Spine whatever order the caller supplied.
        self.assertTrue(lines[1].startswith("Hips|"))
        self.assertTrue(lines[2].startswith("Spine|"))
        # A root joint's parent is empty, never the word None.
        self.assertEqual(lines[1].split("|")[1], "")
        self.assertTrue(text.endswith("\n"))

    def test_the_same_skeleton_always_gives_the_same_fingerprint(self):
        once = skeleton_fingerprint(SHARED_VECTOR)
        twice = skeleton_fingerprint(list(reversed(SHARED_VECTOR)))

        self.assertEqual(once, twice)
        self.assertEqual(len(once), 64)
        self.assertEqual(once, once.lower())

    def test_halfway_values_round_away_from_zero_rather_than_to_even(self):
        # 0.1234565 * 1e6 is the case where Python's own round() and .NET's
        # "F6" disagree. Pinning it is the whole point.
        self.assertEqual(quantize(0.1234565), 123457)
        self.assertEqual(quantize(-0.1234565), -123457)
        self.assertEqual(quantize(0.0000005), 1)
        self.assertEqual(quantize(-0.0000005), -1)
        # Negative zero is the same place as zero and must read the same.
        self.assertEqual(str(quantize(-0.0)), "0")
        self.assertEqual(str(quantize(0.0)), "0")

    def test_a_negated_quaternion_is_the_same_rotation(self):
        turned = dict(SHARED_VECTOR[0])
        negated = dict(SHARED_VECTOR[0])
        negated["rotation"] = tuple(-value for value in turned["rotation"])

        self.assertEqual(
            skeleton_fingerprint([turned, SHARED_VECTOR[1]]),
            skeleton_fingerprint([negated, SHARED_VECTOR[1]]),
        )
        self.assertGreaterEqual(canonical_rotation(negated["rotation"])[3], 0)

    def test_an_unnormalized_quaternion_matches_its_normalized_self(self):
        scaled = dict(SHARED_VECTOR[0])
        scaled["rotation"] = tuple(value * 4 for value in SHARED_VECTOR[0]["rotation"])

        self.assertEqual(
            skeleton_fingerprint([scaled, SHARED_VECTOR[1]]),
            skeleton_fingerprint(SHARED_VECTOR),
        )

    def test_a_different_skeleton_is_a_different_fingerprint(self):
        renamed = dict(SHARED_VECTOR[0])
        renamed["name"] = "Chest"
        moved = dict(SHARED_VECTOR[0])
        moved["translation"] = (0.0, 0.1234575, 0.0)
        reparented = dict(SHARED_VECTOR[0])
        reparented["parent"] = None

        base = skeleton_fingerprint(SHARED_VECTOR)
        for changed in (renamed, moved, reparented):
            self.assertNotEqual(base, skeleton_fingerprint([changed, SHARED_VECTOR[1]]))

    def test_a_skeleton_that_cannot_be_fingerprinted_is_refused(self):
        for broken in (
            [{"name": "", "translation": (0, 0, 0)}],
            [{"name": "Hips", "translation": (0, 0)}],
            [{"name": "Hips", "rotation": (0, 0, 0, 0)}],
            [{"name": "Hips", "translation": (0, float("inf"), 0)}],
            [{"name": "Hips"}, {"name": "Hips"}],
            [],
            # A name carrying a field or line separator could shift the fields,
            # so two different skeletons would canonicalize to the same text.
            [{"name": "Hip|s"}],
            [{"name": "Hips\nSpine"}],
            [{"name": "Spine", "parent": "Hip|s"}],
        ):
            with self.assertRaises(SkeletonFingerprintError):
                skeleton_fingerprint(broken)

    def test_the_report_carries_the_algorithm_so_a_consumer_can_refuse_it(self):
        report = fingerprint_report(SHARED_VECTOR)

        self.assertEqual(report["algorithm"], ALGORITHM)
        self.assertEqual(report["joint_count"], 2)
        self.assertEqual(report["fingerprint"], skeleton_fingerprint(SHARED_VECTOR))

    def test_the_shared_vector_hash_is_the_one_both_repositories_assert(self):
        self.assertEqual(skeleton_fingerprint(SHARED_VECTOR), SHARED_VECTOR_FINGERPRINT)


if __name__ == "__main__":
    unittest.main()
