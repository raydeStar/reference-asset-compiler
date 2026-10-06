"""Paint a conformed head and its hair shell from a front/side/back turnaround.

The front picture is registered by the face landmarks the conform stage
already matched (its receipt carries the similarity); the side and back
pictures by silhouette. The opposite side is the side picture mirrored. Each
mesh's texels take the average of the pictures that see them squarely, and
unseen texels are grown in from their painted neighbours.

Writes the head texture (in the template's own UV layout), the hair texture,
and a views JSON with every registration and its silhouette agreement.

Usage:
  python scripts/paint_head_from_views.py <template.npz> <conform.npz> <conform.json> \
      <hair_shell.npz> <front.png> <side.png> <back.png> <out_dir> [--head-size 4096]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler import template_conform as tc  # noqa: E402
from reference_asset_compiler import view_projection as vp  # noqa: E402

# Visible in a profile and bound on the template: outer eye corner and inner,
# brow tail, nose tip and base, mouth corner, upper and lower lip, chin.
SIDE_LANDMARKS = (93, 89, 101, 86, 80, 61, 71, 53, 0)
# The same in the 68-point layout, for a left profile (the subject's left side shows):
# outer corner of the left eye, its brow tail, nose tip and base, left mouth corner,
# upper and lower lip. The hidden side's points are guesses and stay out.
SIDE_LANDMARKS_68 = (45, 26, 30, 33, 54, 51, 57)


def read_landmarks(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if "landmarks_68" in d:
        return np.array(d["landmarks_68"], float), SIDE_LANDMARKS_68
    return np.array(d["landmarks_106"], float), SIDE_LANDMARKS
FRONT_SHARPNESS = 2.0
HAIR_MIN_FACING = 0.06
# The crown faces no picture. Rolled back over the top of the head by CROWN_ROLL degrees it
# lands on the back picture's upper hair, so it takes real painted strands instead of a smear
# grown in from the edges. Blended in as the hair turns upward (normal z from CROWN_FROM to
# CROWN_FULL).
CROWN_ROLL = 55.0
NECK_HAIR_DARKER = 0.88
BROW_CLEARANCE = 0.035   # metres above the eyes' centre: clear of the brows (no landmarks)
LID_CLEARANCE = 0.012    # metres above the eyes' centre: clear of the lid crease
BROW_BAND = 0.007        # metres around the brow landmarks kept as brow
BESIDE_EYES = 0.006      # metres outside the eyeballs where the temples begin
TEMPLE_BEHIND_EYES = 0.02   # metres behind the eyes: the temples, clear of the cheeks
CROWN_FROM = 0.10
CROWN_FULL = 0.4
SIDE_SHARPNESS = 6.0
BACK_SHARPNESS = 4.0
HELPERS = ("helper-l-eye", "helper-r-eye", "helper-upper-teeth", "helper-lower-teeth",
           "helper-tongue")


def head_triangles(z):
    """Fan triangles of the kept skin polygons, as vertex and loop (UV) indices."""
    helper = np.zeros(len(z["verts"]), bool)
    for g in HELPERS:
        if "vg__" + g in z.files:
            helper[z["vg__" + g]] = True
    vt, lt = [], []
    for i in z["keep_polys"]:
        s, n = int(z["loop_starts"][i]), int(z["loop_totals"][i])
        lv = z["loops"][s:s + n]
        if helper[lv].any():
            continue
        for k in range(1, n - 1):
            lt.append((s, s + k, s + k + 1))
            vt.append((lv[0], lv[k], lv[k + 1]))
    return np.array(vt), np.array(lt)


def brow_points(receipt):
    """The front picture's two brows as (x, z) polylines on the head, or None.

    The conform receipt holds the landmarks file and the picture's registration
    (plane (x, -z) -> pixels); its inverse carries each brow landmark onto the head."""
    pic = receipt.get("picture") or {}
    path = pic.get("landmarks")
    if not path or not Path(path).exists():
        return None
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    reg = pic["registration"]
    if "landmarks_68" in d:
        px, runs = np.array(d["landmarks_68"], float), (range(17, 22), range(22, 27))
    else:
        px, runs = np.array(d["landmarks_106"], float), (range(43, 52), range(97, 106))
    plane = (px - np.array(reg["translation_px"])) @ np.array(reg["rotation"]) / reg["scale_px_per_m"]
    xz = np.c_[plane[:, 0], -plane[:, 1]]
    return [xz[list(r)] for r in runs]


def near_polyline(xz, polylines, band):
    """Which (x, z) points lie within `band` of any of the polylines."""
    out = np.zeros(xz.shape[:-1], bool)
    pts = np.concatenate(polylines)
    lo, hi = pts.min(0) - band, pts.max(0) + band
    cand = np.all((xz >= lo) & (xz <= hi), axis=-1)
    q = xz[cand]
    best = np.full(len(q), np.inf)
    for line in polylines:
        for a, b in zip(line[:-1], line[1:]):
            ab = b - a
            t = np.clip(((q - a) @ ab) / (ab @ ab + 1e-12), 0.0, 1.0)
            best = np.minimum(best, np.linalg.norm(q - (a + t[:, None] * ab), axis=1))
    out[cand] = best < band
    return out


def paint_crown(tex, back, verts, normals, tris, uv, tris_uv, size, above):
    """Repaint upward-facing hair from the back picture, rolled over the top.
    Only above `above` (the ears' top): lower ledges of hair face up too, and
    rolled they would land on the picture's neck."""
    tri_id, bary = vp.uv_rasterize(uv, tris_uv, size)
    texel = tri_id >= 0
    ids = tris[tri_id[texel]]
    pos = np.einsum("nk,nkj->nj", bary[texel], verts[ids])
    nrm = np.einsum("nk,nkj->nj", bary[texel], normals[ids])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    weight = np.clip((nrm[:, 2] - CROWN_FROM) / (CROWN_FULL - CROWN_FROM), 0.0, 1.0)
    weight *= np.clip((pos[:, 2] - above) / 0.02, 0.0, 1.0)
    centre = (verts.min(0) + verts.max(0)) / 2
    c, s = np.cos(np.radians(CROWN_ROLL)), np.sin(np.radians(CROWN_ROLL))
    rel = pos - centre
    rolled = centre + np.stack([rel[:, 0], rel[:, 1] * c + rel[:, 2] * s,
                                -rel[:, 1] * s + rel[:, 2] * c], 1)
    px = back.pixels(rolled)
    h, w = back.image.shape[:2]
    xi = np.clip(px[:, 0].astype(int), 0, w - 1)
    yi = np.clip(px[:, 1].astype(int), 0, h - 1)
    ok = (px[:, 0] >= 0) & (px[:, 0] < w) & (px[:, 1] >= 0) & (px[:, 1] < h)
    if back.mask is not None:
        ok &= back.mask[yi, xi]
    weight = weight * ok
    vals = tex[texel]
    tex = tex.copy()
    tex[texel] = vals * (1 - weight[:, None]) + back.colour(px) * weight[:, None]
    return tex, int((weight > 0).sum())


def main():
    p = argparse.ArgumentParser()
    for name in ("template", "conform", "receipt", "hair", "front", "side", "back", "out_dir"):
        p.add_argument(name)
    p.add_argument("--head-size", type=int, default=4096)
    p.add_argument("--side-landmarks", help="detect_face_landmarks.py JSON of the side picture")
    p.add_argument("--template-landmarks", help="landmarks on a front render of the template")
    p.add_argument("--template-camera", help="camera JSON of that render")
    p.add_argument("--hair-size", type=int, default=2048)
    a = p.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    tz = np.load(a.template)
    z = np.load(a.conform)
    receipt = json.loads(Path(a.receipt).read_text(encoding="utf-8"))
    reg = receipt["picture"]["registration"]
    hair = np.load(a.hair)

    head_v = z["verts"]
    head_t, head_lt = head_triangles(z)
    head_uv = tz["loop_uv"].astype(np.float64)
    head_n = tc.vertex_normals(head_v, head_t)
    hair_v, hair_t = hair["verts"], hair["tris"]
    hair_uv = hair["loop_uv"].astype(np.float64)
    hair_lt = np.arange(hair_t.size).reshape(-1, 3)
    hair_n = tc.vertex_normals(hair_v, hair_t)

    occ_v = np.concatenate([head_v, hair_v])
    occ_t = np.concatenate([head_t, hair_t + len(head_v)])

    front_img = vp.load_image(a.front)
    # The front picture is the identity authority: it paints everything it
    # sees at a usable angle; the side and back fill only what faces them.
    front = vp.View("front", front_img, reg["scale_px_per_m"], np.array(reg["rotation"]),
                    np.array(reg["translation_px"]), mask=vp.foreground_mask(front_img, fill=False, shrink=3),
                    weight=1.0, sharpness=FRONT_SHARPNESS)
    views = [front]
    record = {"front": {"image": a.front, "scale": front.scale, "source": "face landmarks"}}
    for name, path in (("left", a.side), ("back", a.back)):
        img = vp.load_image(path)
        v, iou = vp.register_by_silhouette(name, img, occ_v, occ_t, front.scale)
        v.mask = vp.foreground_mask(img, fill=False, shrink=3)
        v.sharpness = SIDE_SHARPNESS if name == "left" else BACK_SHARPNESS
        record[name] = {"image": path, "silhouette_iou": iou, "source": "silhouette"}
        if name == "left" and a.side_landmarks:
            # The features the profile shows -- outer eye corner, brow tail, nose
            # tip and base, mouth corner, lips, chin -- on the fitted head (bound
            # through the template render) against where the profile has them.
            cam = json.loads(Path(a.template_camera).read_text(encoding="utf-8"))
            tpl_px, side_set = read_landmarks(a.template_landmarks)
            side_px, side_set2 = read_landmarks(a.side_landmarks)
            if side_set != side_set2:
                raise SystemExit("side and template landmarks use different layouts")
            rest = tz["verts"].astype(np.float64)
            ids, bary, found = tc.bind_pixels(rest, head_t, cam, tpl_px)
            use = np.array([k for k in side_set if found[k]])
            pts = np.einsum("lk,lkj->lj", bary[use], head_v[ids[use]])
            # The features place the face: the generated hair around it differs
            # from the mesh's by centimetres, so the silhouette cannot. A
            # similarity takes the profile's features onto the mesh's, and a
            # local warp closes what a similarity cannot (the picture's own
            # proportions).
            silhouette_offset = np.linalg.norm(v.pixels(pts) - side_px[use], axis=1)
            s2, r2, t2 = tc.similarity_2d(v.plane(pts), side_px[use])
            v = vp.View(name, img, float(s2), r2, t2, mask=v.mask, sharpness=v.sharpness)
            before = np.linalg.norm(v.pixels(pts) - side_px[use], axis=1)
            v.warp = vp.LocalWarp(v.plane(pts), side_px[use] - v.pixels(pts))
            after = np.linalg.norm(v.pixels(pts) - side_px[use], axis=1)
            record[name].update({"source": "feature similarity, then feature warp",
                                 "landmarks": use.tolist(),
                                 "silhouette_feature_offset_px": float(np.median(silhouette_offset)),
                                 "similarity_residual_px": {"median": float(np.median(before)),
                                                            "max": float(before.max())},
                                 "warped_residual_px": float(after.max())})
        gain, n = vp.match_colour(front, v, head_v, head_n, (occ_v, occ_t))
        v.gain = gain
        record[name].update({"scale": v.scale, "translation": v.translation.tolist(),
                             "colour_gain": gain.tolist(), "colour_match_vertices": n})
        views.append(v)
        if name == "left":
            views.append(vp.mirrored(v, "right"))
            record["right"] = {"image": path, "mirrored_from": "left"}
    # Front silhouette agreement, for the record.
    fpx = front.pixels(occ_v)
    fmask = vp.rasterize_mask(fpx, occ_t, front_img.shape[:2])
    fg = vp.foreground_mask(front_img)
    record["front"]["silhouette_iou"] = float((fmask & fg).sum() / max((fmask | fg).sum(), 1))

    buffers = {}
    tex, cov, painted, where = vp.bake(views, head_v, head_n, head_t, head_uv, head_lt,
                                       a.head_size, (occ_v, occ_t), buffers=buffers)
    texel = vp.uv_rasterize(head_uv, head_lt, a.head_size)[0] >= 0
    # Hair the pictures draw over the neck: the profile shows locks hanging behind the ear,
    # and where the shell no longer covers the neck that hair lands on the skin. Below the
    # ears and behind their front edge (clear of the beard), skin painted much darker than
    # the face (hair is a darker shade of the same hue) is treated as unseen and grown in
    # from the skin around it. (Regrowing the whole neck instead leaves flat streaks.)
    ears = head_v[tz["vg__ears"]]
    lum = tex @ np.array([0.2126, 0.7152, 0.0722])
    face_band = painted & (where[..., 2] > ears[:, 2].min()) & (where[..., 2] < ears[:, 2].max())
    skin_lum = float(np.median(lum[face_band]))
    neck = painted & (where[..., 2] < ears[:, 2].min()) & (where[..., 1] > ears[:, 1].min())
    hairy = neck & (lum < NECK_HAIR_DARKER * skin_lum)
    # The same in the hair zone - above the brows, and the temples behind the eyes' outer
    # corners above the ears' lowest point: the pictures' hair painted onto the skin. A hair
    # shell hides it; strands (grow_hair_groom.py) leave it showing. Texels there that no
    # picture saw (the old shell hid them) are regrown too.
    eyes = head_v[np.concatenate([z["vg__helper-l-eye"], z["vg__helper-r-eye"]])]
    # Above the lids everything dark is hair except the brows themselves: the front picture's
    # brow landmarks, carried onto the head through its registration, mark a band to keep.
    zone = (where[..., 2] > eyes[:, 2].mean() + LID_CLEARANCE) \
        | ((where[..., 1] > eyes[:, 1].mean() + TEMPLE_BEHIND_EYES) & (where[..., 2] > ears[:, 2].min())) \
        | ((np.abs(where[..., 0]) > np.abs(eyes[:, 0]).max() + BESIDE_EYES) & (where[..., 2] > eyes[:, 2].mean() - 0.015))
    brows = brow_points(receipt)
    if brows is not None:
        front = where[..., 1] < eyes[:, 1].mean() + 0.03
        zone &= ~(front & near_polyline(where[..., [0, 2]], brows, BROW_BAND))
    else:
        zone &= where[..., 2] > eyes[:, 2].mean() + BROW_CLEARANCE
    hairy |= painted & zone & (lum < NECK_HAIR_DARKER * skin_lum)
    regrow = hairy | (texel & zone & ~painted)
    # From skin only: the nearest painted neighbours include brows and lashes, which would
    # paint the temples black.
    skin_src = painted & ~hairy & (lum >= NECK_HAIR_DARKER * skin_lum)
    regrown = vp.fill_unseen_3d(tex, skin_src, skin_src | regrow, where)
    tex[regrow] = regrown[regrow]
    painted = painted | regrow
    record["hair_on_skin_texels_regrown"] = int(regrow.sum())
    tex = vp.fill_unseen_3d(tex, painted, texel, where)
    tex = vp.fill_unpainted(tex, texel)
    Image.fromarray((np.clip(tex, 0, 1) * 255).astype(np.uint8)).save(out / "head_basecolor.png")
    # Hair takes paint at shallower angles than skin: a smeared strand on the
    # crown, which no picture faces, beats a flat patch of filled colour.
    htex, hcov, hpainted, hwhere = vp.bake(views, hair_v, hair_n, hair_t, hair_uv, hair_lt,
                                           a.hair_size, (occ_v, occ_t), buffers=buffers,
                                           min_facing=HAIR_MIN_FACING)
    htexel = vp.uv_rasterize(hair_uv, hair_lt, a.hair_size)[0] >= 0
    htex = vp.fill_unseen_3d(htex, hpainted, htexel, hwhere)
    htex = vp.fill_unpainted(htex, htexel)
    htex, crown_texels = paint_crown(htex, next(v for v in views if v.name == "back"),
                                     hair_v, hair_n, hair_t, hair_uv, hair_lt, a.hair_size,
                                     float(head_v[tz["vg__ears"], 2].max()))
    record["crown"] = {"roll_deg": CROWN_ROLL, "from_normal_z": CROWN_FROM,
                       "full_normal_z": CROWN_FULL, "texels": crown_texels}
    Image.fromarray((np.clip(htex, 0, 1) * 255).astype(np.uint8)).save(out / "hair_basecolor.png")

    record["coverage"] = {
        "head_texels": int(texel.sum()), "head_painted": int(painted.sum()),
        "hair_texels": int(htexel.sum()), "hair_painted": int(hpainted.sum()),
    }
    for name in ("head_basecolor.png", "hair_basecolor.png"):
        record[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / "views.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in record.items() if k in ("front", "left", "back", "coverage")},
                     indent=1))


if __name__ == "__main__":
    main()
