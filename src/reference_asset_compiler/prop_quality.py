"""Acceptance measurements on the levelled game mesh before UVs and painting."""
from __future__ import annotations

import math


def game_mesh_check(record: dict, size_m: float, size_is: str, topology: str) -> dict:
    extents = [b - a for a, b in zip(record["min_m"], record["max_m"], strict=True)]
    if len(extents) != 3 or not all(math.isfinite(x) and x >= 0 for x in extents):
        raise ValueError("Invalid game mesh bounds")
    measured = {"height": extents[2], "width": extents[0], "longest": max(extents)}[size_is]
    # Simplification can move the extreme vertex. Allow 1% or one millimetre.
    tolerance = max(0.001, size_m * 0.01)
    reasons = []
    if topology == "closed" and record["open_edges_after"]:
        reasons.append(f'{record["open_edges_after"]} open edges remain on the closed game mesh')
    if abs(measured - size_m) > tolerance:
        reasons.append(f"measured {size_is} {measured:.4f} m, requested {size_m:.4f} m")
    return {"ok": not reasons, "topology": topology, "size_is": size_is, "measured_m": measured,
            "target_m": size_m, "tolerance_m": tolerance, "reasons": reasons}
