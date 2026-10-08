"""Bake the original front and retained inferred back onto the acquired outfit.

Body-only UVs keep facial pixels off clothing. Fixed source registration and
normal-weighted views are deterministic; no new generated image is required.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler import template_conform as tc
from reference_asset_compiler import view_projection as vp


def main():
    p = argparse.ArgumentParser()
    p.add_argument("mesh")
    p.add_argument("front")
    p.add_argument("back")
    p.add_argument("out")
    p.add_argument("--size", type=int, default=4096)
    p.add_argument("--side", help="retained inferred side view, used only for profile-facing surfaces")
    a = p.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    z = np.load(a.mesh)
    verts, tris, uv, tris_uv = z["verts"], z["tris"], z["uv"], z["tris_uv"]
    normals = tc.vertex_normals(verts, tris)
    views = []
    records = {}
    for name, path in (("front", a.front), ("back", a.back)):
        im = Image.open(path).convert("RGBA")
        raw = np.asarray(im) / 255.0
        mask = raw[..., 3] > 0.5
        if mask.all():
            mask = vp.foreground_mask(raw[..., :3])
        # Source dimensions are the original 1536 x 1024. The retained body
        # is 1.8 m high, centred at z=0; foot and hand landmarks anchor this.
        view = vp.View(name, raw[..., :3], 538.89, np.eye(2), np.array([765.5, 500.0]),
                       mask=ndimage.binary_erosion(mask, iterations=1), sharpness=2.0)
        views.append(view)
        records[name] = {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                         "scale": view.scale, "translation": view.translation.tolist()}
    if a.side:
        im = np.asarray(Image.open(a.side).convert("RGBA")) / 255.0
        mask = im[..., 3] > 0.5
        side = vp.View("left", im[..., :3], 538.89, np.eye(2), np.array([734.0, 500.0]),
                       mask=ndimage.binary_erosion(mask, iterations=1), sharpness=4.0, weight=1.5)
        views.append(side)
        other = vp.mirrored(side, "right")
        # The sash hangs from only one hip. A mirrored witness cannot invent
        # a second red sash on the hidden trouser leg.
        other.mask = other.mask.copy()
        image = other.image
        yy = np.indices(other.mask.shape)[0]
        sash = (image[..., 0] > image[..., 1] * 1.7) & (image[..., 0] > image[..., 2] * 1.8) & (yy > 425)
        other.mask &= ~ndimage.binary_dilation(sash, iterations=5)
        views.append(other)
        records["side"] = {"path": str(Path(a.side).resolve()), "sha256": hashlib.sha256(Path(a.side).read_bytes()).hexdigest(),
                           "scale": side.scale, "translation": side.translation.tolist(), "inferred": True}
    def side_region(points):
        # The end-on arm hides almost the entire sleeve in the side picture.
        # Let the front/back witnesses dress it; one glove was quite enough.
        return np.clip((0.45 - np.abs(points[:, 0])) / 0.12, 0, 1)

    tex, cov, painted, where = vp.bake(views, verts, normals, tris, uv, tris_uv,
                                     a.size, (verts, tris), min_facing=0.05,
                                     view_weights={"left": side_region, "right": side_region})
    valid = vp.uv_rasterize(uv, tris_uv, a.size)[0] >= 0
    tex = vp.fill_unseen_3d(tex, painted, valid, where, k=12)
    tex = vp.fill_unpainted(tex, valid)
    Image.fromarray((np.clip(tex, 0, 1) * 255).astype(np.uint8)).save(out / "body_basecolor.png")
    Image.fromarray((np.clip(cov, 0, 1) * 255).astype(np.uint8)).save(out / "coverage.png")
    record = {"sources": records, "mesh_sha256": hashlib.sha256(Path(a.mesh).read_bytes()).hexdigest(),
              "painted_fraction": float(painted.sum() / valid.sum()),
              "method": "source-registered multiview bake, 3D fill on unseen underside texels",
              "side_region": "full below abs(x)=0.33 m, fades to zero at 0.45 m; arms use front/back",
              "review": "Inferred back and unseen surfaces need visual review; candidate only."}
    (out / "body-paint.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
