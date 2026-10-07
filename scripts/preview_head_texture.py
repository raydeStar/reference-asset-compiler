"""Unlit views of head textures on their conformed head, for tuning paint without Blender.

A paint stage is judged in renders, but a render takes a minute and mixes the
paint with light. This rasterizes the head's skin triangles orthographically at
chosen yaws (0 = front, 35 = the review's three-quarter, 90 = its side, the
same convention as render_painted_head.py), samples each texture by UV, and
lays the textures out as rows (before / after a stage, say). With --guidance
it adds the front view drawn in the guidance picture's own frame beside the
picture, so paint and picture can be compared pixel for pixel.

These are flat, bald albedo views: tuning aids, not review images to show
beside the painting.

Usage:
  python scripts/preview_head_texture.py --template T.npz --head head.npz out.png \
      before.png after.png [--yaws 0 35 90] [--receipt head.json --guidance head-front.png]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler import view_projection as vp  # noqa: E402
from paint_head_from_views import head_triangles  # noqa: E402


def raster_uv(px, depth, tris, tri_uv, shape):
    """Per-pixel UV of the nearest triangle (orthographic; smaller depth is nearer); NaN off the mesh."""
    h, w = shape
    zbuf = np.full(shape, np.inf)
    uv = np.full((h, w, 2), np.nan)
    for k, t in enumerate(tris):
        a, b, c = px[t[0]], px[t[1]], px[t[2]]
        x0, y0 = np.floor(np.minimum(np.minimum(a, b), c)).astype(int)
        x1, y1 = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        v0, v1 = b - a, c - a
        den = v0[0] * v1[1] - v1[0] * v0[1]
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        dx, dy = gx - a[0], gy - a[1]
        w1 = (dx * v1[1] - v1[0] * dy) / den
        w2 = (v0[0] * dy - dx * v0[1]) / den
        w0 = 1 - w1 - w2
        inside = (w0 >= -1e-3) & (w1 >= -1e-3) & (w2 >= -1e-3)
        if not inside.any():
            continue
        z = w0 * depth[t[0]] + w1 * depth[t[1]] + w2 * depth[t[2]]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        nearer = inside & (z < sub)
        sub[nearer] = z[nearer]
        uv[y0:y1 + 1, x0:x1 + 1][nearer] = (w0[..., None] * tri_uv[k, 0] + w1[..., None] * tri_uv[k, 1]
                                            + w2[..., None] * tri_uv[k, 2])[nearer]
    return uv


def yaw_view(verts, centre, yaw_deg, px_per_m, size):
    """Pixels and depth of `verts` seen orthographically from a yaw round the head."""
    a = math.radians(yaw_deg)
    right = np.array([math.cos(a), math.sin(a), 0.0])
    toward = np.array([math.sin(a), -math.cos(a), 0.0])   # from the head to the camera
    rel = verts - centre
    px = np.c_[rel @ right, -rel[:, 2]] * px_per_m + size / 2
    return px, -(rel @ toward)


def sample_uv(texture, uv, backdrop=0.25):
    n = texture.shape[0]
    ok = ~np.isnan(uv[..., 0])
    q = uv[ok] * n
    q[:, 1] = n - q[:, 1]
    out = np.full(uv.shape[:2] + (3,), backdrop)
    out[ok] = vp.sample(texture, q)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--template", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("out")
    p.add_argument("textures", nargs="+")
    p.add_argument("--yaws", type=float, nargs="+", default=[0.0, 35.0, 90.0])
    p.add_argument("--size", type=int, default=800)
    p.add_argument("--px-per-m", type=float, default=3200.0)
    p.add_argument("--receipt", help="conform receipt (head.json): its picture registration, for --guidance")
    p.add_argument("--guidance", help="the front guidance picture: adds the front view in its frame beside it")
    a = p.parse_args(argv)
    template = np.load(a.template)
    z = dict(np.load(a.head))
    tris, lt = head_triangles(z)
    verts = z["verts"]
    tri_uv = template["loop_uv"][lt]
    centre = verts[np.unique(tris)].mean(0)
    views = []
    for yaw in a.yaws:
        px, depth = yaw_view(verts, centre, yaw, a.px_per_m, a.size)
        views.append(raster_uv(px, depth, tris, tri_uv, (a.size, a.size)))
    guide = None
    if a.guidance:
        if not a.receipt:
            p.error("--guidance needs --receipt (the registration into the picture)")
        reg = json.loads(Path(a.receipt).read_text())["picture"]["registration"]
        guide = vp.load_image(a.guidance)
        px = reg["scale_px_per_m"] * np.c_[verts[:, 0], -verts[:, 2]] @ np.array(reg["rotation"]).T + reg["translation_px"]
        framed = raster_uv(px, verts[:, 1], tris, tri_uv, guide.shape[:2])
    rows = []
    for path in a.textures:
        texture = vp.load_image(path)
        cells = [sample_uv(texture, uv) for uv in views]
        if guide is not None:
            front = sample_uv(texture, framed)
            front = np.where(np.isnan(framed[..., :1]), guide * 0.35, front)
            cells += [np.asarray(Image.fromarray((np.clip(front, 0, 1) * 255).astype(np.uint8))
                                 .resize((a.size, a.size)), float) / 255,
                      np.asarray(Image.fromarray((guide * 255).astype(np.uint8)).resize((a.size, a.size)), float) / 255]
        rows.append(np.concatenate(cells, 1))
    Image.fromarray((np.clip(np.concatenate(rows, 0), 0, 1) * 255).astype(np.uint8)).save(a.out)
    print(json.dumps({"out": str(a.out), "rows": a.textures, "yaws": a.yaws, "guidance": a.guidance}))


if __name__ == "__main__":
    main()
