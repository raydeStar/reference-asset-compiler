from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.hand_landmarks import DIGITS, SIDES, validate_hand_landmarks


SOURCE_HASH = "a" * 64


def valid_payload():
    hands = {}
    for side_index, side in enumerate(SIDES):
        sign = 1.0 if side_index == 0 else -1.0
        hands[side] = {
            "wrist": [sign * 0.5, 0.0, 1.0],
            "digits": {
                digit: [[sign * (0.52 + joint * 0.02), 0.0, 0.98 - joint * 0.02]
                        for joint in range(4)]
                for digit in DIGITS
            },
        }
    return {
        "schema": "reference-asset-compiler.hand-landmarks.v1",
        "source": {"path": "candidate.glb", "sha256": SOURCE_HASH},
        "coordinate_space": "mesh_local_after_import_transform_apply",
        "hands": hands,
        "review": {"status": "approved", "approved_by": "artist", "note": "Reviewed"},
    }


class HandLandmarkTests(unittest.TestCase):
    def test_complete_reviewed_source_bound_landmarks_pass(self) -> None:
        result = validate_hand_landmarks(valid_payload(), SOURCE_HASH)
        self.assertEqual(set(SIDES), set(result["hands"]))

    def test_source_hash_drift_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "source mesh hash"):
            validate_hand_landmarks(valid_payload(), "b" * 64)

    def test_missing_digit_joint_fails(self) -> None:
        payload = copy.deepcopy(valid_payload())
        payload["hands"]["l"]["digits"]["index"].pop()
        with self.assertRaisesRegex(ValueError, "four ordered joints"):
            validate_hand_landmarks(payload, SOURCE_HASH)

    def test_unreviewed_landmarks_fail(self) -> None:
        payload = copy.deepcopy(valid_payload())
        payload["review"]["status"] = "draft"
        with self.assertRaisesRegex(ValueError, "reviewer approval"):
            validate_hand_landmarks(payload, SOURCE_HASH)


if __name__ == "__main__":
    unittest.main()
