"""Where to stand when you want to know whether a face can be seen.

The cull itself needs Blender, because it needs the mesh. Everything it needs
to *decide* does not, so it lives here where it can be tested without a
renderer: the viewpoints, the order they are tried in, and the one judgement
about whether a result is a cleanup or a catastrophe.

No module here imports bpy, on purpose.
"""

from __future__ import annotations

import math


def directions_over_sphere(count: int) -> list[tuple[float, float, float]]:
    """`count` unit vectors spread as evenly as they can be over the sphere.

    A latitude and longitude grid clumps at the poles: with 64 directions it
    would spend a quarter of them looking almost straight down, and a model's
    underside would be examined far more carefully than its side. The Fibonacci
    spiral has no such preference, so every part of a surface gets a comparable
    chance of being seen, which is the only property this needs.
    """
    if count < 1:
        raise ValueError("count must be at least 1")
    golden = math.pi * (1.0 + 5.0 ** 0.5)
    points = []
    for index in range(count):
        offset = index + 0.5
        z = 1.0 - 2.0 * offset / count
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        angle = golden * offset
        points.append((math.cos(angle) * radius, math.sin(angle) * radius, z))
    return points


def viewing_order(directions, normal):
    """Every direction, best-aligned first, each with the side it leaves from.

    The obvious version of this only fires into the hemisphere a face points
    at, on the reasoning that a ray aimed into the surface tells you nothing.
    That reasoning assumes the normal is right, and on a generated mesh it
    frequently is not. Measured on one rigged character: 5,950 faces, a quarter
    of everything the outward-only test called hidden, were in plain sight from
    their other side. Culling on that answer took the boots off and left the
    soles behind, and every number in the report stayed correct.

    So both sides are tried and the normal is treated as a hint about ordering
    rather than a fact about facing. A face is visible when somebody standing
    anywhere outside can see it, which is a question about where it sits, not
    about which way an exporter thought it pointed.

    Ordering still pays for itself: an ordinary exterior face escapes on its
    first or second ray, so the full sweep is paid only by faces that really
    are buried. The returned side is +1 when the ray leaves along the normal
    and -1 when it leaves against it, so an origin can be lifted off the face
    on the side the ray is actually going.
    """
    nx, ny, nz = normal
    ranked = []
    for direction in directions:
        alignment = direction[0] * nx + direction[1] * ny + direction[2] * nz
        if alignment == 0.0:
            continue  # Exactly in plane: it would only graze its own face.
        ranked.append((abs(alignment), direction, 1.0 if alignment > 0.0 else -1.0))
    ranked.sort(key=lambda entry: -entry[0])
    return [(direction, side) for _, direction, side in ranked]


def cull_verdict(total: int, kept: int, most: float) -> str | None:
    """Why this result should not be written, or None if it should.

    Removing most of a model is not a cleanup. The usual cause is a mesh whose
    normals point inward, where every face's outward hemisphere aims into the
    solid and nothing escapes -- and the honest answer to that is to say so,
    not to hand somebody a hollow and let them find out in a scene. The other
    refusal is the opposite: nothing was hidden, so there is no derivative to
    make, and a revision identical to its source is only clutter.
    """
    if total <= 0:
        return "this mesh has no faces to look at"
    removed = total - kept
    if removed == 0:
        return "every face is visible from outside, so there is nothing to remove"
    share = removed / total
    if share > most:
        return ("{0:.1%} of this model's faces were never seen, which is more than the {1:.0%} "
                "this is allowed to remove. The usual cause is inward-facing normals, where "
                "every ray aims into the solid. Check the mesh is not inside out.".format(share, most))
    return None


def whole_parts_removed(neighbours, removed):
    """The sizes of the connected parts this cull would take away entirely.

    Removing a sealed fragment is the point of the exercise. Removing an
    eyeball that happens to sit inside a closed head is the same operation on
    the same arithmetic, and no ray can tell the two apart.

    So the size is reported rather than trusted. Only removed faces are walked,
    and a group that touches nothing surviving is a part that disappears whole.

    `neighbours[face]` lists the faces sharing an edge with it; `removed` is the
    set of face indices nothing could see.
    """
    seen, parts = set(), []
    for start in removed:
        if start in seen:
            continue
        group, queue, touches_survivor = [], [start], False
        seen.add(start)
        while queue:
            face = queue.pop()
            group.append(face)
            for neighbour in neighbours[face]:
                if neighbour not in removed:
                    touches_survivor = True
                elif neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        if not touches_survivor:
            parts.append(len(group))
    return sorted(parts, reverse=True)


def whole_part_verdict(parts, total: int, largest: float) -> str | None:
    """Whether a part disappearing whole is debris or somebody's work.

    Debris is small: a stray interior shell is a fraction of a percent of a
    model. Anything substantial that vanishes whole was modelled on purpose and
    sealed inside something else, and that is a refusal rather than a cleanup.
    """
    if not parts:
        return None
    share = parts[0] / total
    if share > largest:
        return ("one connected part would disappear entirely, and it is {0:.1%} of this "
                "model -- more than the {1:.0%} a piece of debris can be. That is something "
                "somebody modelled, sealed inside something else. Open it, split it out, or "
                "raise --largest-part deliberately.".format(share, largest))
    return None
