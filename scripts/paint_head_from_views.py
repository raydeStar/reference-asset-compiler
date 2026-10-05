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
FRONT_SHARPNESS = 2.0
HAIR_MIN_FACING = 0.06
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
            tpl_px = np.array(json.loads(Path(a.template_landmarks).read_text())["landmarks_106"])
            side_px = np.array(json.loads(Path(a.side_landmarks).read_text())["landmarks_106"])
            rest = tz["verts"].astype(np.float64)
            ids, bary, found = tc.bind_pixels(rest, head_t, cam, tpl_px)
            use = np.array([k for k in SIDE_LANDMARKS if found[k]])
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
