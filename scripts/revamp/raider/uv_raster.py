"""UV-space rasterizing shared by the Raider texture passes (tone_metal.py, tone_skin.py)."""
import numpy as np


def fill_polygon(mask, pts):
    """Set the texels whose centres fall inside a convex UV polygon (pixel units; Blender's rows run bottom-up)."""
    pts = np.asarray(pts)
    x0, y0 = np.floor(pts.min(0)).astype(int)
    x1, y1 = np.ceil(pts.max(0)).astype(int)
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, mask.shape[1] - 1), min(y1, mask.shape[0] - 1)
    if x1 < x0 or y1 < y0:
        return
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    inside_pos = np.ones(xs.shape, bool)
    inside_neg = np.ones(xs.shape, bool)
    for i in range(len(pts)):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
        cross = (bx - ax) * (ys - ay) - (by - ay) * (xs - ax)
        inside_pos &= cross >= 0
        inside_neg &= cross <= 0
    mask[y0:y1 + 1, x0:x1 + 1] |= inside_pos | inside_neg
