"""The skeleton fingerprint a browser studio and this compiler both compute.

Two programs in two languages have to arrive at the same hex string from the
same skeleton, so every step that could differ between them is pinned here and
in `docs/BROWSER_STUDIO_CONTRACT.md`:

- joints are ordered by name using ordinal byte comparison, not tree order, not
  locale-aware collation;
- numbers are quantized to integers rather than formatted as decimals, because
  .NET's ``ToString("F6")`` rounds halfway values away from zero while Python's
  ``format(x, '.6f')`` rounds them to even, and a skeleton that lands on a
  halfway value would otherwise fingerprint differently on each side;
- a quaternion and its negation are the same rotation, so the sign is
  canonicalized before quantizing, or one skeleton yields two fingerprints.

A fingerprint says *these clips were authored against this skeleton*. It is not
a retargeting promise and carries no claim about any other rig.
"""

from __future__ import annotations

import hashlib
import math
from typing import Any, Iterable

ALGORITHM = "rac-skeleton-v1"
"""Prefix and version. A change in how this is computed is a new prefix."""

QUANTIZATION = 1000000
"""Six decimal places, expressed as an integer scale rather than a format."""


class SkeletonFingerprintError(ValueError):
    """The skeleton cannot be fingerprinted, and no fallback is invented."""


FORBIDDEN_IN_NAMES = ("|", "\n", "\r")
"""The field and line separators. A name carrying one could shift the fields,
so two different skeletons could canonicalize to the same text. Blender permits
such names; every engine target discourages them; this refuses them rather than
adding an escaping scheme that both languages would have to get right."""


def _check_name(name: str, what: str) -> None:
    for character in FORBIDDEN_IN_NAMES:
        if character in name:
            raise SkeletonFingerprintError(
                "A {0} cannot contain a field or line separator: {1!r}".format(what, name))


def quantize(value: float) -> int:
    """Round half away from zero at six decimal places, stated explicitly.

    Python's round() and format() both round halves to even, and .NET's "F6"
    does not. Neither default is used, so both sides can agree.
    """
    number = float(value)
    if not math.isfinite(number):
        raise SkeletonFingerprintError("A skeleton value must be a finite number.")
    scaled = number * QUANTIZATION
    rounded = math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)
    # -0 and 0 are the same position and must produce the same text.
    return int(rounded) + 0


def canonical_rotation(rotation: Iterable[float]) -> tuple[float, float, float, float]:
    """Normalize a quaternion and fix its sign so w is not negative."""
    parts = [float(value) for value in rotation]
    if len(parts) != 4:
        raise SkeletonFingerprintError("A rest rotation must be a quaternion of four numbers.")
    if not all(math.isfinite(value) for value in parts):
        raise SkeletonFingerprintError("A rest rotation must be finite.")

    x, y, z, w = parts
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 0:
        raise SkeletonFingerprintError("A rest rotation must not be a zero quaternion.")
    x, y, z, w = x / length, y / length, z / length, w / length
    # q and -q are the same rotation. Without this a rig can fingerprint twice.
    if w < 0:
        x, y, z, w = -x, -y, -z, -w
    return x, y, z, w


def _triple(values: Iterable[float], what: str) -> tuple[float, float, float]:
    parts = [float(value) for value in values]
    if len(parts) != 3:
        raise SkeletonFingerprintError("A rest {0} must be three numbers.".format(what))
    return parts[0], parts[1], parts[2]


def canonical_text(joints: Iterable[dict[str, Any]]) -> str:
    """The exact text that gets hashed, so a mismatch can be diffed by eye."""
    prepared = []
    seen = set()
    for joint in joints:
        name = joint.get("name")
        if not isinstance(name, str) or not name:
            raise SkeletonFingerprintError("Every joint needs a name.")
        if name in seen:
            raise SkeletonFingerprintError("Joint {0} appears more than once.".format(name))
        _check_name(name, "joint name")
        seen.add(name)

        parent = joint.get("parent") or ""
        if not isinstance(parent, str):
            raise SkeletonFingerprintError("A joint's parent must be a name or nothing.")
        _check_name(parent, "parent name")

        translation = _triple(joint.get("translation", (0.0, 0.0, 0.0)), "translation")
        scale = _triple(joint.get("scale", (1.0, 1.0, 1.0)), "scale")
        rotation = canonical_rotation(joint.get("rotation", (0.0, 0.0, 0.0, 1.0)))
        prepared.append((name, parent, translation, rotation, scale))

    if not prepared:
        raise SkeletonFingerprintError("A skeleton with no joints has no fingerprint.")

    # Ordinal order: compare the UTF-8 bytes, never a locale's idea of order.
    prepared.sort(key=lambda entry: entry[0].encode("utf-8"))

    lines = [ALGORITHM]
    for name, parent, translation, rotation, scale in prepared:
        numbers = [
            ",".join(str(quantize(value)) for value in translation),
            ",".join(str(quantize(value)) for value in rotation),
            ",".join(str(quantize(value)) for value in scale),
        ]
        lines.append("|".join([name, parent] + numbers))
    return "\n".join(lines) + "\n"


def skeleton_fingerprint(joints: Iterable[dict[str, Any]]) -> str:
    """Lowercase hex SHA-256 of the canonical text."""
    text = canonical_text(joints)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint_report(joints: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """What a stage writes beside a payload so a consumer can check its work."""
    prepared = list(joints)
    return {
        "schema": "reference-asset-compiler.skeleton-fingerprint.v1",
        "algorithm": ALGORITHM,
        "joint_count": len(prepared),
        "fingerprint": skeleton_fingerprint(prepared),
    }
