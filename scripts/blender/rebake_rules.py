"""The judgements a re-bake makes, kept apart from Blender so they can be tested.

How far a bake ray reaches, when a reduction's UVs are too damaged to bake
onto, and which channels of a material need a map rather than a number are
decisions, not mechanics. They live here, where they can be read, tested and
argued with without starting Blender.

No module here imports bpy, on purpose.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

# How much worse than the source's own atlas a reduction may leave its UVs
# before they stop being baked onto. Measured against the source, so a layout
# that was always a little crowded is not blamed on the reduction.
UV_TOLERANCE = {
    "overlap_share": 0.005,
    "flipped_share": 0.005,
    "distorted_share": 0.02,
    "outside_share": 0.001,
}

CHANNELS = ("base_color", "alpha", "roughness", "metallic", "transmission", "emission",
            "occlusion")


def ray_settings(gap_p99_m: float, diagonal_m: float) -> dict[str, Any]:
    """Extrusion and ray length from the measured gap between the two surfaces.

    Sized to the 99th percentile, not the worst point. The few texels where the
    surfaces sit further apart than that miss, are found by the coverage pass
    and filled from their neighbours -- a far smaller error than making every
    ray in the model long enough to land on the next part over, which is what
    baked a pale scalp onto ninja-man (docs/COMPILER.md, "Bake rays must be
    short").
    """
    if gap_p99_m < 0 or diagonal_m <= 0:
        raise ValueError("A gap cannot be negative and an object must have a size")
    extrusion = max(0.0015, min(2.0 * gap_p99_m, 0.01 * diagonal_m))
    return {
        "cage_extrusion_m": round(extrusion, 6),
        "max_ray_distance_m": round(2.0 * extrusion, 6),
        "use_cage": False,
        "rule": "extrusion = max(1.5 mm, min(2 x p99 gap, 1% of diagonal)); "
                "rays reach twice the extrusion",
    }


def uv_verdict(reduced: dict[str, float], source: dict[str, float],
               tolerance: dict[str, float] | None = None) -> tuple[bool, list[str]]:
    """Whether a reduction's own UVs are still an atlas worth baking onto.

    Each share is what the reduction *added* over the source: overlaps (two
    surfaces claiming one texel, which a bake can only give to one of them),
    triangles mirrored against their island, triangles whose texel density is
    off by more than 4x, and UVs pushed outside the sheet.
    """
    tolerance = tolerance or UV_TOLERANCE
    reasons = []
    for key, allowed in tolerance.items():
        introduced = float(reduced.get(key, 0.0)) - float(source.get(key, 0.0))
        if introduced > allowed:
            reasons.append("{0} rose by {1:.2%} over the source's (allowed {2:.2%})".format(
                key.replace("_share", "").replace("_", " "), introduced, allowed))
    return not reasons, reasons


def plan_channels(materials: list[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Which channels need a baked map and which stay a single number.

    ``materials`` holds, per re-baked material, each channel as either
    ``{"linked": True}`` (a texture or node drives it) or ``{"constant": v}``.
    A channel is baked when any material drives it, or when their constants
    disagree -- one number cannot be right for both. Base colour is always
    baked: it is the paint, and the paint is the point.
    """
    if not materials:
        raise ValueError("There is no material to plan a bake for")
    plan: dict[str, dict[str, Any]] = {}
    for channel in CHANNELS:
        entries = [material[channel] for material in materials]
        linked = any(entry.get("linked") for entry in entries)
        constants = {json.dumps(entry.get("constant")) for entry in entries if not entry.get("linked")}
        if channel == "base_color":
            plan[channel] = {"baked": True, "why": "the paint itself"}
        elif linked:
            plan[channel] = {"baked": True, "why": "driven by a texture or node"}
        elif len(constants) > 1:
            plan[channel] = {"baked": True, "why": "its constants differ between the materials"}
        else:
            plan[channel] = {"baked": False, "constant": entries[0]["constant"]}
    cutoffs = {material["alpha"].get("cutoff") for material in materials
               if material["alpha"].get("cutoff") is not None}
    if plan["alpha"]["baked"]:
        # One cutoff carries over as a cutout; several cannot, so the alpha is
        # baked as it ends up and blended.
        plan["alpha"]["cutoff"] = cutoffs.pop() if len(cutoffs) == 1 else None
    return plan


def painted_shares(islands: np.ndarray, reached: np.ndarray,
                   written: np.ndarray) -> dict[str, float | None]:
    """How much of the painted surface the rays reached, and how much the bake wrote.

    All three masks are one size: ``islands`` are the painted faces' texels,
    ``reached`` comes from a white coverage pass baked without a margin, and
    ``written`` from one baked with the maps' margin. Only ``reached`` says how
    much of the surface a ray found: the margin also fills the misses within its
    width, from their neighbours, so a margin-baked mask calls them reached.
    Neither share exists when the painted faces cover no texel.
    """
    islands = np.asarray(islands, dtype=bool)
    reached = np.asarray(reached, dtype=bool)
    written = np.asarray(written, dtype=bool)
    if not (islands.shape == reached.shape == written.shape):
        raise ValueError("The island, reached and written masks must be the same size, not "
                         "{0}, {1} and {2}".format(islands.shape, reached.shape, written.shape))
    if not islands.any():
        return {"painted_surface_reached_share": None, "painted_surface_written_share": None}
    return {"painted_surface_reached_share": round(float(reached[islands].mean()), 4),
            "painted_surface_written_share": round(float(written[islands].mean()), 4)}
