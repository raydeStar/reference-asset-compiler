"""Bake the original front and retained inferred back onto the acquired outfit.

Body-only UVs keep facial pixels off clothing. Fixed source registration and
normal-weighted views are deterministic; no new generated image is required.

The registration is the character's: how many pixels a metre is in the source
pictures and which pixel the body's origin (centred at z=0) lands on. So are
--side-band and --unmirrored-red. rebuild_character.py passes them from
profiles/characters/<name>.json.
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
    p.add_argument("--px-per-m", type=float, required=True, help="source pictures' scale")
    p.add_argument("--front-origin", type=float, nargs=2, required=True, metavar=("X", "Y"),
                   help="pixel of the front and back pictures the body's origin lands on")
    p.add_argument("--side-origin", type=float, nargs=2, metavar=("X", "Y"),
                   help="the same for the side picture (required with --side)")
    p.add_argument("--side-band", type=float, nargs=2, metavar=("FULL_BELOW", "ZERO_AT"),
                   help="side views weigh fully within |x| FULL_BELOW m and fade to nothing at ZERO_AT, "
                        "so end-on arms take the front and back pictures (default: everywhere)")
    p.add_argument("--unmirrored-red", type=float, nargs=4, metavar=("R_OVER_G", "R_OVER_B", "BELOW_ROW", "GROW_PX"),
                   help="a red garment on one side only: keep it out of the mirrored side view "
                        "(red beyond both ratios, below the pixel row, grown by GROW_PX)")
    a = p.parse_args()
    if a.side and not a.side_origin:
        p.error("--side needs --side-origin")
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
        # The retained body is centred at z=0; foot and hand landmarks anchor
        # the registration.
        view = vp.View(name, raw[..., :3], a.px_per_m, np.eye(2), np.array(a.front_origin),
                       mask=ndimage.binary_erosion(mask, iterations=1), sharpness=2.0)
        views.append(view)
        records[name] = {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                         "scale": view.scale, "translation": view.translation.tolist()}
    if a.side:
        im = np.asarray(Image.open(a.side).convert("RGBA")) / 255.0
        mask = im[..., 3] > 0.5
        side = vp.View("left", im[..., :3], a.px_per_m, np.eye(2), np.array(a.side_origin),
                       mask=ndimage.binary_erosion(mask, iterations=1), sharpness=4.0, weight=1.5)
        views.append(side)
        other = vp.mirrored(side, "right")
        if a.unmirrored_red:
            # A sash hanging from one hip: a mirrored witness cannot invent a
            # second one on the hidden leg.
            r_over_g, r_over_b, below_row, grow = a.unmirrored_red
            other.mask = other.mask.copy()
            image = other.image
            yy = np.indices(other.mask.shape)[0]
            sash = (image[..., 0] > image[..., 1] * r_over_g) & (image[..., 0] > image[..., 2] * r_over_b) & (yy > below_row)
            other.mask &= ~ndimage.binary_dilation(sash, iterations=int(grow))
        views.append(other)
        records["side"] = {"path": str(Path(a.side).resolve()), "sha256": hashlib.sha256(Path(a.side).read_bytes()).hexdigest(),
                           "scale": side.scale, "translation": side.translation.tolist(), "inferred": True}
    def side_region(points):
        # The end-on arm hides almost the entire sleeve in the side picture.
        # Let the front/back witnesses dress it; one glove was quite enough.
        full, zero = a.side_band
        return np.clip((zero - np.abs(points[:, 0])) / (zero - full), 0, 1)

    weights = {"left": side_region, "right": side_region} if a.side_band else {}
    tex, cov, painted, where = vp.bake(views, verts, normals, tris, uv, tris_uv,
                                     a.size, (verts, tris), min_facing=0.05,
                                     view_weights=weights)
    valid = vp.uv_rasterize(uv, tris_uv, a.size)[0] >= 0
    tex = vp.fill_unseen_3d(tex, painted, valid, where, k=12)
    tex = vp.fill_unpainted(tex, valid)
    Image.fromarray((np.clip(tex, 0, 1) * 255).astype(np.uint8)).save(out / "body_basecolor.png")
    Image.fromarray((np.clip(cov, 0, 1) * 255).astype(np.uint8)).save(out / "coverage.png")
    record = {"sources": records, "mesh_sha256": hashlib.sha256(Path(a.mesh).read_bytes()).hexdigest(),
              "painted_fraction": float(painted.sum() / valid.sum()),
              "method": "source-registered multiview bake, 3D fill on unseen underside texels",
              "side_region": ("full below abs(x)={0} m, fades to zero at {1} m; arms use front/back".format(*a.side_band)
                              if a.side_band else "everywhere"),
              "review": "Inferred back and unseen surfaces need visual review; candidate only."}
    (out / "body-paint.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
