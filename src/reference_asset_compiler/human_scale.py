"""How big a thing is, said the way a person can actually judge it.

A generator answers in its own units: whatever it makes arrives about two
metres tall, a lantern exactly as much as a person. Nothing downstream can fix
that by measuring, because the mesh carries no claim about the world -- and a
reduction gate that allows a millimetre of surface deviation is meaningless
against a lantern six times its real size.

Asking for the height in metres is the obvious fix and the wrong one. Almost
nobody can say whether a trial lantern is 0.3 m or 0.45 m, and a number
invented to get past a prompt is worse than no number at all. People are good
at a different question: standing next to it, where does it come up to?

So a size is named against a human body. The landmarks are fractions of
stature, so they stay right whatever reference height a production picks, and
``adjust`` covers "a bit under the knee" without inventing a landmark for every
few inches.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "reference-asset-compiler.human-scale.v1"

REFERENCE_HEIGHT_M = 1.75
"""The standing adult these landmarks describe. Everything else is a fraction
of this, so a production that works at a different reference changes one number
rather than a table."""

LANDMARKS: dict[str, float] = {
    "ankle": 0.039,
    "mid-calf": 0.16,
    "knee": 0.285,
    "mid-thigh": 0.42,
    "hip": 0.53,
    "waist": 0.60,
    "chest": 0.72,
    "shoulder": 0.82,
    "eye": 0.936,
    "head": 1.0,
    "overhead": 1.25,
}
"""Fractions of stature, from standard anthropometric proportions. `overhead`
is the one that is not a body part: a thing taller than the person looking at
it, which is how an artist describes an arch or a standing stone."""

DESCRIPTIONS: dict[str, str] = {
    "ankle": "about ankle height",
    "mid-calf": "about mid-calf",
    "knee": "about knee height",
    "mid-thigh": "about mid-thigh",
    "hip": "about hip height",
    "waist": "about waist height",
    "chest": "about chest height",
    "shoulder": "about shoulder height",
    "eye": "about eye level",
    "head": "about as tall as a person",
    "overhead": "taller than a person",
}

MINIMUM_ADJUST = 0.25
MAXIMUM_ADJUST = 4.0
"""An adjustment is for "a bit under the knee", not for turning one landmark
into another. Past these, the landmark is the wrong one and saying so is more
use than silently accepting it."""


class HumanScaleError(ValueError):
    """A size that cannot be resolved, named rather than guessed at."""


def named_sizes() -> list[dict[str, Any]]:
    """Every size a caller may ask for, with what it means in metres."""
    return [
        {
            "size": name,
            "description": DESCRIPTIONS[name],
            "fraction_of_stature": fraction,
            "metres": round(fraction * REFERENCE_HEIGHT_M, 3),
        }
        for name, fraction in sorted(LANDMARKS.items(), key=lambda item: item[1])
    ]


def resolve_height(
    size: str,
    adjust: float = 1.0,
    reference_height_m: float = REFERENCE_HEIGHT_M,
) -> dict[str, Any]:
    """The real-world height a named size means, and how it was arrived at.

    The whole record is returned rather than a bare number because a later
    reviewer reading a receipt needs to know which landmark was chosen and
    against which reference, not only what it worked out to.
    """
    if size not in LANDMARKS:
        raise HumanScaleError(
            "Unknown size {0!r}. Say where it comes up to on a person: {1}.".format(
                size, ", ".join(sorted(LANDMARKS))))
    if not isinstance(adjust, (int, float)) or isinstance(adjust, bool):
        raise HumanScaleError("A size adjustment must be a number")
    if not MINIMUM_ADJUST <= adjust <= MAXIMUM_ADJUST:
        raise HumanScaleError(
            "An adjustment of {0} turns {1!r} into a different size entirely; "
            "choose the landmark that fits instead.".format(adjust, size))
    if not 0.5 <= reference_height_m <= 3.0:
        raise HumanScaleError("A reference human height must be between 0.5 m and 3 m")

    fraction = LANDMARKS[size]
    metres = fraction * reference_height_m * adjust
    return {
        "schema": SCHEMA,
        "size": size,
        "description": DESCRIPTIONS[size],
        "adjust": float(adjust),
        "reference_human_height_m": reference_height_m,
        "fraction_of_stature": fraction,
        "height_m": round(metres, 4),
    }
