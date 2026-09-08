"""Perspective-correct surface projection and read-only camera depth rasterization."""
import numpy as np

from raster_geometry import triangle_pixels


def project_surface(weights, screen_vertices, depth_vertices):
    depth = weights @ depth_vertices
    screen = (weights @ (screen_vertices * depth_vertices[:, None])) / depth[:, None]
    return screen, depth


def raster_depth(screen, depths, size):
    buffer = np.full((size, size), np.inf, dtype=np.float64)
    for vertices, z in zip(screen, depths):
        if np.any(z <= 0):
            continue
        uv = np.column_stack((vertices[:, 0] / size, 1 - vertices[:, 1] / size))
        pixels = triangle_pixels(uv, size)
        if pixels is None:
            continue
        yy, xx, weights = pixels
        depth = 1 / (weights @ (1 / z))
        buffer[yy, xx] = np.minimum(buffer[yy, xx], depth)
    return buffer


def depth_visible(screen, depth, buffer, tolerance):
    xy = np.floor(screen).astype(int)
    inside = ((xy[:, 0] >= 0) & (xy[:, 0] < buffer.shape[1])
              & (xy[:, 1] >= 0) & (xy[:, 1] < buffer.shape[0]))
    visible = np.zeros(len(screen), dtype=bool)
    sampled = buffer[xy[inside, 1], xy[inside, 0]]
    visible[inside] = np.isfinite(sampled) & (np.abs(depth[inside] - sampled) <= tolerance)
    return visible
