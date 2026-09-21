"""Whether an open candidate is inheritance or damage.

This is the one judgement in the reduction that is not arithmetic, so it lives
on its own, away from Blender, where it can be read and argued with.

The reduction stage was written to judge a candidate production authority: a
closed two-manifold surface somebody will build on. Anything with a boundary or
a non-manifold edge is rejected, and that is right for an authority.

A runtime derivative of a mesh that is already in somebody's library is a
different thing. That mesh is ordinary game art -- open shells, separate glass,
cloth with a free edge -- and somebody reviewed and accepted it in that state.
Judged as an authority it can only ever be rejected, for a reason that was true
before the reduction ran.

So the relaxation is bounded by exactly that reason: an open candidate is
accepted only where the source was open too. A closed surface that comes back
open has been torn, and no mode makes that acceptable -- which is the check
that stops "runtime derivative" from meaning "do not look".

No module here imports bpy, on purpose.
"""

from __future__ import annotations

from typing import Any


def is_open(topology: dict[str, Any]) -> bool:
    """Whether a surface has anywhere it is not closed and two-manifold."""
    return bool(topology.get("boundary_edges") or topology.get("nonmanifold_edges"))


def surface_verdict(source: dict[str, Any], candidate: dict[str, Any],
                    runtime_derivative: bool) -> tuple[list[str], list[str]]:
    """What the surface's openness costs this candidate.

    Returns the failures it earns and the findings that were accepted instead,
    so a receipt can carry both. A finding that is not written down is a
    relaxation nobody can hold anybody to.
    """
    if not is_open(candidate):
        return [], []
    if not runtime_derivative:
        return ["candidate is not a closed two-manifold surface"], []
    if not is_open(source):
        return ([
            "the reduction opened a surface that was closed: "
            "{0} boundary and {1} non-manifold edges where the source had none".format(
                candidate.get("boundary_edges", 0), candidate.get("nonmanifold_edges", 0))
        ], [])
    return [], [
        "Open surface inherited from the reviewed source: {0} boundary and {1} "
        "non-manifold edges, against {2} and {3} in the source.".format(
            candidate.get("boundary_edges", 0), candidate.get("nonmanifold_edges", 0),
            source.get("boundary_edges", 0), source.get("nonmanifold_edges", 0))
    ]
