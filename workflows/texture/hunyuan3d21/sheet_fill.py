"""Filling the texels of a painted sheet that no view saw, near the mesh only.

Upstream fills every unpainted texel of the sheet with OpenCV's Navier-Stokes
inpaint, on one core per map. A section of a large model uses a few percent of
an 8192 sheet, so that fill spent 140 s of a section's 210 s on texels the
section pass never reads. `inpaint_near` keeps upstream's fill where the mesh
is, within `reach` texels of its own texels, and fills the rest of the sheet
from the nearest paint first, so the band OpenCV works in is edged with paint
and not with the black of an empty sheet.
"""
from __future__ import annotations

import numpy as np


def fill_from_coarser(image, known):
    """Every texel `known` does not hold, from the mean of the held texels in the smallest block round it with any.

    A pull-push fill: the held texels are averaged into blocks of 2, 4, 8 ...
    texels, and each empty texel takes the finest block mean that exists over it.
    Held texels are returned unchanged. `image` is uint8, one channel or more,
    with sides a power of two; about two seconds at 8192.
    """
    import cv2  # noqa: PLC0415

    image = np.asarray(image)
    known = np.asarray(known, dtype=bool)
    if not known.any() or known.all():
        return image.copy()
    flat = image.ndim == 2
    pixels = image[..., None] if flat else image
    channels = pixels.shape[2]

    def halve(array):
        # A block mean of 2 x 2, the same as summing and dividing by four.
        out = cv2.resize(array, (array.shape[1] // 2, array.shape[0] // 2), interpolation=cv2.INTER_AREA)
        return out.reshape(out.shape[0], out.shape[1], -1)

    colour = halve(pixels.astype(np.float32) * known[..., None])
    weight = halve(known.astype(np.float32))[..., 0]
    levels = [(colour, weight)]
    while min(weight.shape) > 1 and weight.shape[0] % 2 == 0 and weight.shape[1] % 2 == 0:
        colour = halve(np.ascontiguousarray(colour))
        weight = halve(np.ascontiguousarray(weight))[..., 0]
        levels.append((colour, weight))

    def grow(array, shape):
        out = cv2.resize(array, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
        return out.reshape(shape[0], shape[1], -1)

    filled = levels[-1][0] / np.maximum(levels[-1][1], 1e-12)[..., None]
    for colour, weight in reversed(levels[:-1]):
        grown = grow(np.ascontiguousarray(filled), weight.shape)
        filled = np.where((weight > 0)[..., None], colour / np.maximum(weight, 1e-12)[..., None], grown)
    top = np.iinfo(pixels.dtype).max if pixels.dtype.kind in "ui" else None
    coarse = np.clip(filled + 0.5, 0, top).astype(pixels.dtype)
    out = np.where(known[..., None], pixels, grow(np.ascontiguousarray(coarse), known.shape)[..., :channels])
    return out[..., 0] if flat else out


def inpaint_near(image, mask, footprint, reach, radius=3):
    """Upstream's OpenCV fill within `reach` texels of the mesh; the rest of the sheet from the nearest paint.

    `image` is the sheet as upstream converts it (uint8), `mask` upstream's
    (255 where a view painted the texel), `footprint` the texels the mesh itself
    covers. OpenCV fills, as upstream asks it to, every texel that is not 255,
    but only inside the footprint grown by `reach`. Returns the filled sheet and
    how many texels OpenCV filled.
    """
    import cv2  # noqa: PLC0415 -- the painter's environment has it; tests import it too

    known = np.asarray(mask) == 255
    kernel = np.ones((2 * reach + 1, 2 * reach + 1), np.uint8)
    near = cv2.dilate(np.asarray(footprint, dtype=np.uint8), kernel) > 0
    holes = near & ~known
    filled = cv2.inpaint(fill_from_coarser(image, known), holes.astype(np.uint8) * 255, radius, cv2.INPAINT_NS)
    return filled, int(holes.sum())
