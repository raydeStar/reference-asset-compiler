"""NumPy-only UV triangle rasterization shared with Blender's bundled Python."""
import numpy as np


def triangle_pixels(triangle, size):
    points = triangle.copy() * size - .5
    points[:, 1] = size - 1 - points[:, 1]
    lo = np.maximum(np.ceil(points.min(axis=0)).astype(int), 0)
    hi = np.minimum(np.floor(points.max(axis=0)).astype(int), size - 1)
    if np.any(hi < lo):
        return None
    xx, yy = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
    a, b, c = points
    det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(det) < 1e-10:
        return None
    w0 = ((b[1] - c[1]) * (xx - c[0]) + (c[0] - b[0]) * (yy - c[1])) / det
    w1 = ((c[1] - a[1]) * (xx - c[0]) + (a[0] - c[0]) * (yy - c[1])) / det
    weights = np.stack([w0, w1, 1 - w0 - w1], axis=-1)
    inside = np.all(weights >= -1e-7, axis=-1)
    return yy[inside], xx[inside], weights[inside]
