"""Bake the original front and retained inferred back onto the acquired outfit.

Body-only UVs keep facial pixels off clothing. Fixed source registration and
normal-weighted views are deterministic; no new generated image is required.

The registration is the character's: how many pixels a metre is in the source
pictures and which pixel the body's origin (centred at z=0) lands on. So are
--side-band, --unmirrored-red and the fill options. rebuild_character.py
passes them from profiles/characters/<name>.json.

What no picture saw squarely is filled. --fill nearest (the default) takes the
nearest painted points in 3D. Without a side picture that is most of a coat's
sides and every shoulder top, and the nearest paint is a picture's outline: it
comes out as grey streaks. --fill surface takes colour only from texels a
picture faced squarely (--fill-trust), spreads it as a smooth membrane over the
mesh's own edges (view_projection.fill_unseen_surface), and fades the paint at
the edge of each picture's view into it. --normal-smoothing judges facing on
normals averaged over a few centimetres, so a scan's wrinkle facets do not take
a picture's outline either.
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
    p.add_argument("--min-facing", type=float, default=0.05,
                   help="how squarely a surface must face a picture to take its paint (cosine). Raise it when "
                        "there is no side picture: grazing sides then come from the 3D fill, not from a "
                        "picture's last pixels smeared across them")
    p.add_argument("--mask-erode-px", type=int, default=1,
                   help="pixels taken off each picture's cut-out edge (a halo of the old background)")
    p.add_argument("--fill", choices=("nearest", "surface"), default="nearest",
                   help="how unseen surface is painted: nearest painted points in 3D, or a membrane over the mesh "
                        "from squarely seen paint (better without a side picture)")
    p.add_argument("--fill-trust", type=float, default=0.6,
                   help="--fill surface: how squarely (cosine) a picture must face a texel for its paint to be a fill "
                        "source and kept whole; between --min-facing and this the paint fades into the fill")
    p.add_argument("--normal-smoothing", type=float, default=0.0, metavar="METRES",
                   help="judge facing on normals averaged over about this distance on the mesh (0: the mesh's own)")
    p.add_argument("--unmirrored-red", type=float, nargs=4, metavar=("R_OVER_G", "R_OVER_B", "BELOW_ROW", "GROW_PX"),
                   help="a red garment on one side only: keep it out of the mirrored side view "
                        "(red beyond both ratios, below the pixel row, grown by GROW_PX)")
    a = p.parse_args()
    if a.side and not a.side_origin:
        p.error("--side needs --side-origin")
    if a.fill == "surface" and not a.min_facing < a.fill_trust <= 1:
        p.error("--fill-trust must lie above --min-facing and at most 1")
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    z = np.load(a.mesh)
    verts, tris, uv, tris_uv = z["verts"], z["tris"], z["uv"], z["tris_uv"]
    normals = vp.smooth_normals(verts, tris, tc.vertex_normals(verts, tris), a.normal_smoothing)
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
                       mask=ndimage.binary_erosion(mask, iterations=a.mask_erode_px), sharpness=2.0)
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
                                     a.size, (verts, tris), min_facing=a.min_facing,
                                     view_weights=weights)
    tri_id, bary = vp.uv_rasterize(uv, tris_uv, a.size)
    valid = tri_id >= 0
    fill_record = {"method": a.fill}
    if a.fill == "surface":
        # How squarely the pictures that paint a texel face it (a side view only within its band).
        ids, w3 = tris[tri_id[valid]], bary[valid]
        pos = np.einsum("nk,nkj->nj", w3, verts[ids])
        nrm = np.einsum("nk,nkj->nj", w3, normals[ids])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        facing = np.zeros(len(nrm))
        for view in views:
            cos = nrm @ -vp.VIEW_AXES[view.name][2]
            if view.name in weights:
                cos = cos * np.clip(weights[view.name](pos), 0.0, 1.0)
            facing = np.maximum(facing, cos)
        keep = np.zeros(valid.shape)
        keep[valid] = np.where(painted[valid], np.clip((facing - a.min_facing) / (a.fill_trust - a.min_facing), 0, 1), 0)
        keep = keep * keep * (3 - 2 * keep)
        tex, stats = vp.fill_unseen_surface(tex, keep, tri_id, bary, verts, tris)
        fill_record.update(stats, trust=a.fill_trust)
        cov = cov * keep          # the outfit stage weighs paint by coverage: the faded edge counts for less
    else:
        tex = vp.fill_unseen_3d(tex, painted, valid, where, k=12)
    tex = vp.fill_unpainted(tex, valid)
    Image.fromarray((np.clip(tex, 0, 1) * 255).astype(np.uint8)).save(out / "body_basecolor.png")
    Image.fromarray((np.clip(cov, 0, 1) * 255).astype(np.uint8)).save(out / "coverage.png")
    record = {"sources": records, "mesh_sha256": hashlib.sha256(Path(a.mesh).read_bytes()).hexdigest(),
              "painted_fraction": float(painted.sum() / valid.sum()),
              "method": "source-registered multiview bake, 3D fill on unseen underside texels",
              "fill": fill_record, "normal_smoothing_m": a.normal_smoothing, "min_facing": a.min_facing,
              "side_region": ("full below abs(x)={0} m, fades to zero at {1} m; arms use front/back".format(*a.side_band)
                              if a.side_band else "everywhere"),
              "review": "Inferred back and unseen surfaces need visual review; candidate only."}
    (out / "body-paint.json").write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
