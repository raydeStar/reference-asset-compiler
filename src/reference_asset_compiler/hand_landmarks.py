"""Validation for reviewed humanoid hand landmarks used by rig authoring."""

from __future__ import annotations

import math
from typing import Any


DIGITS = ("thumb", "index", "middle", "ring", "pinky")
SIDES = ("l", "r")


def _point(value: Any, label: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("{0} must be a three-number point".format(label))
    try:
        point = tuple(float(component) for component in value)
    except (TypeError, ValueError) as error:
        raise ValueError("{0} must contain only numbers".format(label)) from error
    if not all(math.isfinite(component) for component in point):
        raise ValueError("{0} contains a non-finite coordinate".format(label))
    return point


def validate_hand_landmarks(
    payload: dict[str, Any], source_sha256: str
) -> dict[str, Any]:
    """Fail closed unless landmarks are complete, reviewed, and source-bound."""
    if payload.get("schema") != "reference-asset-compiler.hand-landmarks.v1":
        raise ValueError("Unsupported hand landmark schema")
    source = payload.get("source") or {}
    if source.get("sha256", "").casefold() != source_sha256.casefold():
        raise ValueError("Hand landmarks were not measured on this source mesh hash")
    if payload.get("coordinate_space") != "mesh_local_after_import_transform_apply":
        raise ValueError("Hand landmarks use an unsupported coordinate space")
    review = payload.get("review") or {}
    if review.get("status") != "approved" or not review.get("approved_by"):
        raise ValueError("Hand landmarks require an explicit reviewer approval")

    normalized: dict[str, Any] = {"hands": {}}
    hands = payload.get("hands") or {}
    for side in SIDES:
        hand = hands.get(side)
        if not isinstance(hand, dict):
            raise ValueError("Missing hand landmarks for side {0}".format(side))
        entry = {"wrist": _point(hand.get("wrist"), "hands.{0}.wrist".format(side))}
        digits = hand.get("digits") or {}
        entry["digits"] = {}
        for digit in DIGITS:
            joints = digits.get(digit)
            if not isinstance(joints, list) or len(joints) != 4:
                raise ValueError(
                    "hands.{0}.digits.{1} requires four ordered joints".format(
                        side, digit
                    )
                )
            entry["digits"][digit] = [
                _point(point, "hands.{0}.digits.{1}[{2}]".format(side, digit, index))
                for index, point in enumerate(joints)
            ]
        normalized["hands"][side] = entry
    normalized["review"] = review
    return normalized
