"""Relief read out of paint, without the seams the atlas put there.

The bake stage derives a normal map from the base colour's local luminance: the
paint is read as the relief it was drawn to represent. That derivation has one
input the paint never had -- the atlas layout. A texture is islands on a
gutter, and at every island edge the luminance steps from paint to fill. Read
as height, that step is a cliff running along every UV seam, and on a
generated character with six hundred islands the derived normal outlined all
six hundred: the eye region of a ninja came out looking like it was drawn on
triangles, because it was.

So the gutter is filled first, with the nearest paint pushed outward until the
blur can no longer reach an edge, and whatever the atlas does not cover is left
flat. Every function here is plain numpy so the behaviour can be tested with
no Blender in the room.
"""

from __future__ import annotations

import numpy as np

# The size the strength was tuned at. A feature of a given physical size spans
# twice the texels at 4096 that it spans at 2048, so its per-texel gradient is
# half as steep; without scaling, the same strength would raise half the relief.
REFERENCE_SIZE = 2048


def blur(plane, radius):
    """A cheap separable box blur, run three times so it reads as a gaussian."""
    radius = max(1, int(radius))
    result = plane
    for _ in range(3):
        padded = np.pad(result, radius, mode="edge")
        totals = np.cumsum(np.cumsum(padded, axis=0), axis=1)
        totals = np.pad(totals, ((1, 0), (1, 0)), mode="constant")
        size = 2 * radius + 1
        rows, columns = plane.shape
        result = (totals[size:size + rows, size:size + columns]
                  - totals[0:rows, size:size + columns]
                  - totals[size:size + rows, 0:columns]
                  + totals[0:rows, 0:columns]) / (size * size)
    return result


def coverage_at(mask, size):
    """A coverage mask resampled to another square size, nearest texel.

    The bake reaches the sheet at its own resolution and the paint may be at
    another; a mask that is a texel off would flatten a texel of real relief.
    Nearest rather than smooth, because coverage is a yes or a no.
    """
    mask = np.asarray(mask, dtype=bool)
    rows = np.arange(size) * mask.shape[0] // size
    columns = np.arange(size) * mask.shape[1] // size
    return mask[rows][:, columns]


def fill_outside(plane, coverage, steps):
    """Push covered values outward into uncovered texels, one texel a step.

    An uncovered texel next to covered ones takes their mean, and then counts
    as covered for the next step. After `steps` of this, every texel within
    that distance of an island carries that island's edge colour, so a blur
    that looks across the edge sees no edge. Texels further out than the blur
    can reach take the covered mean, which is neutral by construction.
    """
    coverage = np.asarray(coverage, dtype=bool)
    if not coverage.any():
        return np.asarray(plane, dtype=np.float32).copy()
    filled = np.where(coverage, plane, 0.0).astype(np.float32)
    known = coverage.copy()
    for _ in range(int(steps)):
        if known.all():
            break
        total = np.zeros_like(filled)
        count = np.zeros(filled.shape, dtype=np.int32)
        for axis in (0, 1):
            for shift in (1, -1):
                neighbour = np.roll(filled, shift, axis=axis)
                seen = np.roll(known, shift, axis=axis)
                total += np.where(seen, neighbour, 0.0)
                count += seen
        grow = (~known) & (count > 0)
        filled = np.where(grow, total / np.maximum(count, 1), filled)
        known |= grow
    if not known.all():
        filled = np.where(known, filled, float(plane[coverage].mean()))
    return filled


def luminance_of(albedo):
    albedo = np.asarray(albedo, dtype=np.float32)
    return 0.2126 * albedo[..., 0] + 0.7152 * albedo[..., 1] + 0.0722 * albedo[..., 2]


def normal_from_paint(albedo, strength, coverage=None, radius=6):
    """A surface normal derived from the relief somebody painted.

    Only the local part of the paint is read: the luminance has its own blurred
    self subtracted first, because the broad steps between one colour and
    another are where one material meets another, not where the surface rises.

    With `coverage` -- which texels geometry actually reaches -- the gutter is
    filled from the islands before anything is measured, and uncovered texels
    come back flat. Without it the atlas's own seams are read as relief, which
    is the mistake this module exists to stop.

    The blur radius and the gain both scale with the sheet, so "0.3" means the
    same relief on a 4096 sheet as on the 2048 it was chosen on.

    Returns the encoded RGBA normal in [0, 1] and the mean absolute relief where
    the paint is, which is what "there is nothing here to raise" is judged by.
    """
    luminance = luminance_of(albedo)
    size = luminance.shape[0]
    scale = size / float(REFERENCE_SIZE)
    radius = max(1, int(round(radius * scale)))
    if coverage is not None:
        coverage = np.asarray(coverage, dtype=bool)
        if coverage.shape != luminance.shape:
            coverage = coverage_at(coverage, size)
        # Past three blur passes' reach, plus one so the last texel the blur
        # touches is also one the fill reached.
        luminance = fill_outside(luminance, coverage, 3 * radius + 1)
    relief = luminance - blur(luminance, radius)
    # Gradients along the map, which is the direction the surface tilts.
    dy, dx = np.gradient(relief)
    gain = strength * 32.0 * scale
    normal = np.dstack([-dx * gain, -dy * gain, np.ones_like(relief)])
    if coverage is not None:
        normal[~coverage] = (0.0, 0.0, 1.0)
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    encoded = np.clip(normal * 0.5 + 0.5, 0.0, 1.0)
    measured = relief[coverage] if coverage is not None else relief
    local = float(np.abs(measured).mean()) if measured.size else 0.0
    return np.dstack([encoded, np.ones_like(relief)]), local
