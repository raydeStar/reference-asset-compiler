"""Which texels a bake actually reached, kept apart from Blender so it can be tested.

A selected-to-active bake casts one ray per texel of the light mesh's UV
islands. Where the ray finds nothing, the texel keeps the clear colour, and
for a base colour or occlusion map that is black. So a bake has to say how
much of the surface its rays reached, and repair what they did not.

The image's alpha cannot say. Measured on Blender 5.2.2 after
``bake(use_clear=True)``: a normal map comes back with alpha 1 on every texel,
reached or not; the margin writes alpha 1 (and a neighbour's colour) into every
missed texel within its reach; and outside the islands alpha differed between
two identical bakes. What can say is a coverage pass: the same bake with every
source surface emitting plain white. Whatever is still black there was never
reached. Baked once without a margin, it is what the rays reached; baked again
with the passes' own margin, it is everything the bake wrote, so the rest is
what ``fill_unbaked`` has to repair.

Reached is only meaningful inside the islands -- the rest of the sheet is gutter
-- so the islands are found by rasterising the light mesh's UV triangles.

No module here imports bpy, on purpose.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# How far the fill grows written colour into unwritten texels, one texel ring
# per round.
FILL_ROUNDS = 12

NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))


def rasterize(tri_uv: np.ndarray, raster: int) -> np.ndarray:
    """How many triangles claim each texel centre (row 0 is the bottom, as in Blender).

    ``tri_uv`` is (triangles, 3, 2) in UV units. A texel counts when its centre
    lies strictly inside a triangle, so one centred exactly on a shared edge is
    claimed by neither side rather than by both -- two claims would read as an
    overlap. Triangles reaching past the sheet are clipped to it.
    """
    counts = np.zeros((raster, raster), dtype=np.int32)
    tri_uv = np.asarray(tri_uv, dtype=np.float64).reshape(-1, 3, 2)
    if len(tri_uv) == 0:
        return counts
    pixels = tri_uv * raster
    lows = np.floor(pixels.min(axis=1)).astype(np.int64)
    highs = np.ceil(pixels.max(axis=1)).astype(np.int64)
    lows = np.clip(lows, 0, raster - 1)
    highs = np.clip(highs, 0, raster)
    a, b, c = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    denominator = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    usable = np.abs(denominator) > 1e-12
    span = np.maximum(highs - lows, 0)
    # Small triangles in one vectorised sweep; the few large ones one at a time.
    small = usable & (span[:, 0] <= 4) & (span[:, 1] <= 4)
    grid = np.stack(np.meshgrid(np.arange(4), np.arange(4), indexing="xy"), axis=-1).reshape(-1, 2)

    def mark(indices, offsets):
        px = lows[indices, None, 0] + offsets[None, :, 0]
        py = lows[indices, None, 1] + offsets[None, :, 1]
        cx, cy = px + 0.5, py + 0.5
        aa, bb, cc, dd = a[indices], b[indices], c[indices], denominator[indices]
        w1 = ((bb[:, None, 1] - cc[:, None, 1]) * (cx - cc[:, None, 0])
              + (cc[:, None, 0] - bb[:, None, 0]) * (cy - cc[:, None, 1])) / dd[:, None]
        w2 = ((cc[:, None, 1] - aa[:, None, 1]) * (cx - cc[:, None, 0])
              + (aa[:, None, 0] - cc[:, None, 0]) * (cy - cc[:, None, 1])) / dd[:, None]
        w3 = 1.0 - w1 - w2
        inside = (w1 > 1e-6) & (w2 > 1e-6) & (w3 > 1e-6) & (px < raster) & (py < raster)
        np.add.at(counts, (py[inside], px[inside]), 1)

    indices = np.flatnonzero(small)
    for start in range(0, len(indices), 20000):
        mark(indices[start:start + 20000], grid)
    for index in np.flatnonzero(usable & ~small):
        width, height = int(span[index, 0]) + 1, int(span[index, 1]) + 1
        offsets = np.stack(np.meshgrid(np.arange(width), np.arange(height), indexing="xy"),
                           axis=-1).reshape(-1, 2)
        mark(np.array([index]), offsets)
    return counts


def _neighbours(mask: np.ndarray):
    """Each of a mask's eight neighbours, wrapping at the sheet's edges."""
    for dy, dx in NEIGHBOURS:
        yield np.roll(np.roll(mask, dy, axis=0), dx, axis=1), (dy, dx)


def fill_reach(written: np.ndarray, rounds: int = FILL_ROUNDS) -> np.ndarray:
    """The texels ``fill_unbaked`` writes, given which ones the bake wrote.

    The same growth without the colour, so what the fill will repair can be
    counted before, or without, filling anything.
    """
    known = np.asarray(written, dtype=bool).copy()
    start = known.copy()
    for _ in range(rounds):
        if known.all():
            break
        near = np.zeros(known.shape, dtype=bool)
        for shifted, _ in _neighbours(known):
            near |= shifted
        grow = ~known & near
        if not grow.any():
            break
        known |= grow
    return known & ~start


def fill_unbaked(pixels: np.ndarray, rounds: int = FILL_ROUNDS) -> int:
    """Grow baked colour into texels the bake never wrote.

    A texel with no hit keeps the clear value, and black is exactly the colour
    that reads as damage. Misses cluster along island edges and -- once the mesh
    is cut into body regions and stitched back -- along every region seam, which
    is why the per-region male arrived speckled with dark blotches across an
    otherwise correct jacket.

    Blender's bake margin already dilates outward from what the rays reached,
    into the gutter and into small holes, but it stops at its own width. This
    grows the nearest written colour into anything still unwritten, which also
    gives mip-mapping something better than black to average with.

    Takes HxWx4 float32 whose alpha is the written mask -- which the bake's own
    alpha is not, so the caller has to put a coverage mask there first (see the
    module docstring). Fills in place, leaves alpha at 1, and returns how many
    texels it actually wrote: a texel more than ``rounds`` away from anything
    written keeps its clear value and is not counted.
    """
    rgb = pixels[..., :3]
    known = pixels[..., 3] > 0.5
    start = known.copy()
    for _ in range(rounds):
        if known.all():
            break
        total = np.zeros_like(rgb)
        count = np.zeros(known.shape, dtype=np.float32)
        for shifted_known, (dy, dx) in _neighbours(known):
            shifted_rgb = np.roll(np.roll(rgb, dy, axis=0), dx, axis=1)
            total += shifted_rgb * shifted_known[..., None]
            count += shifted_known
        grow = (~known) & (count > 0)
        if not grow.any():
            break
        rgb[grow] = total[grow] / count[grow][..., None]
        known |= grow
    pixels[..., :3] = rgb
    pixels[..., 3] = 1.0
    return int((known & ~start).sum())


def coverage_summary(islands: np.ndarray, reached: np.ndarray, written: np.ndarray,
                     rounds: int = FILL_ROUNDS) -> dict[str, Any]:
    """What the rays reached of the islands, and how what they missed was repaired.

    All three masks are the same size: ``islands`` from ``rasterize``,
    ``reached`` from the coverage pass without a margin, ``written`` from the
    coverage pass with the passes' margin. Every unreached island texel ends up
    in exactly one of: written by the margin, filled from its neighbours, or
    left at the clear colour.
    """
    islands = np.asarray(islands, dtype=bool)
    reached = np.asarray(reached, dtype=bool)
    written = np.asarray(written, dtype=bool)
    if not (islands.shape == reached.shape == written.shape):
        raise ValueError("The island, reached and written masks must be the same size, not "
                         "{0}, {1} and {2}".format(islands.shape, reached.shape, written.shape))
    total = int(islands.sum())
    hit = int((islands & reached).sum())
    missed = islands & ~reached
    by_margin = missed & written
    filled = missed & ~written & fill_reach(written, rounds)
    left = missed & ~written & ~filled
    return {
        "island_texels": total,
        "reached_texels": hit,
        # Undefined, not zero, when the layout covers no texel at all.
        "reached_pct": round(100.0 * hit / total, 2) if total else None,
        "unreached_texels": int(missed.sum()),
        "unreached_written_by_margin": int(by_margin.sum()),
        "unreached_filled_from_neighbours": int(filled.sum()),
        "unreached_left_unbaked": int(left.sum()),
    }
