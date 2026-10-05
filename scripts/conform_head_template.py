"""Conform the template head onto an acquired head and carry its face rig across.

Stage driver for the head half of template-conforming retopology (see
`reference_asset_compiler.template_conform`). It aligns the template's face to
the acquisition, fits the head and neck non-rigidly, moves the eyeballs and
teeth with the sockets and jaw around them, and carries every expression unit
through the fit. The acquisition is the shape authority; regions it cannot
vouch for (scalp under hair, lids over a fused groove, the mouth's inside)
keep the template's anatomy and ride along.

Writes one NPZ (the fitted head and its expression deltas, in metres) and a
JSON receipt with hashes, the alignment, the fit log and surface-distance
measurements.

Usage:
  python scripts/conform_head_template.py <template.npz> <acquisition.npz> \
      <out.npz> <receipt.json> [--mpfb-data <mpfb data dir>]
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler import template_conform as tc  # noqa: E402

DEFAULT_MPFB_DATA = (Path.home() / "AppData/Roaming/Blender Foundation/Blender/5.2/extensions"
                     / "user_default/mpfb/data")
STIFFNESS = (60.0, 30.0, 15.0, 8.0, 4.0, 2.0, 1.0)
EXPOSED = 0.25          # open-sky fraction below which a vertex is a cavity
# InsightFace 106-point indices held to the picture: lids and eye corners,
# lips (outer and inner), nose wings, nostrils, tip and base. Brows are hair,
# painted with the face; the jaw contour is a silhouette, not a fixed point.
EYE_LANDMARKS = (33, 35, 36, 37, 39, 40, 41, 42, 87, 89, 90, 91, 93, 94, 95, 96)
MOUTH_LANDMARKS = tuple(range(52, 72))
NOSE_LANDMARKS = (76, 77, 78, 79, 80, 82, 83, 84, 85, 86)
# The jaw outline below the ears (never under hair in a front view), held more
# loosely: a contour point is a silhouette, so its template vertex is only
# near the outline once the fit has moved.
JAW_LANDMARKS = (0, 2, 3, 4, 5, 6, 7, 8, 14, 15, 16, 18, 19, 20, 21, 22, 23, 24, 30, 31, 32)
FEATURE_LANDMARKS = EYE_LANDMARKS + MOUTH_LANDMARKS + NOSE_LANDMARKS + JAW_LANDMARKS
REGISTRATION_LANDMARKS = (35, 39, 89, 93, 77, 83, 80, 86, 52, 61, 71, 53)
LANDMARK_WEIGHT = 4.0
JAW_WEIGHT = 1.5
PUPIL_SHIFT_LIMIT = 0.003   # metres an eyeball may move to meet the picture's pupil
HELPER_FOLLOW = {
    # helper group -> template region whose fitted motion it rides
    "helper-l-eye": "eyelids", "helper-r-eye": "eyelids",
    "helper-upper-teeth": "mouth", "helper-lower-teeth": "mouth", "helper-tongue": "mouth",
}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _region(mpfb_data: Path, name: str):
    d = json.load(gzip.open(mpfb_data / "uv_layers" / (name + ".json.gz")))
    return [int(k) for k in d]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("template")
    p.add_argument("acquisition")
    p.add_argument("out")
    p.add_argument("receipt")
    p.add_argument("--mpfb-data", type=Path, default=DEFAULT_MPFB_DATA)
    p.add_argument("--picture-landmarks", help="detect_face_landmarks.py JSON of the front picture")
    p.add_argument("--template-landmarks", help="the same, run on a render of the template")
    p.add_argument("--template-camera", help="render_mesh_view.py camera JSON of that render")
    a = p.parse_args(argv)
    if a.picture_landmarks and not (a.template_landmarks and a.template_camera):
        p.error("--picture-landmarks needs --template-landmarks and --template-camera")

    t = tc.load_template(a.template)
    body = np.zeros(len(t.verts), bool)
    body[t.groups["body"]] = True
    head_w = t.bone_weight("head") + t.bone_weight("neck_01")
    active = body & (head_w >= 0.3)
    scalp = np.zeros_like(body); scalp[t.polygon_vertices(_region(a.mpfb_data, "scalp_solid"))] = True
    lids = np.zeros_like(body); lids[t.polygon_vertices(_region(a.mpfb_data, "eyelids_solid"))] = True
    lips = np.zeros_like(body); lips[t.polygon_vertices(_region(a.mpfb_data, "lips_solid"))] = True
    face = np.zeros_like(body); face[t.polygon_vertices(_region(a.mpfb_data, "face_solid"))] = True

    z = np.load(a.acquisition)
    acq_v, acq_t = z["verts"].astype(np.float64), z["tris"]
    target_raw = tc.Target.from_mesh(acq_v, acq_t)

    # ---------------------------------------------------------------- similarity alignment
    tris = t.tris
    normals = tc.vertex_normals(t.verts, tris)
    face_fit = active & face & ~scalp & ~lids & (normals[:, 1] < -0.2)
    src = t.verts[face_fit]
    src_n = normals[face_fit]
    nose_t = t.verts[np.flatnonzero(active)[np.argmin(t.verts[active, 1])]]
    centre_x = np.median(acq_v[:, 0])
    band = (np.abs(acq_v[:, 0] - centre_x) < 0.2) & (acq_v[:, 2] > np.quantile(acq_v[:, 2], 0.2)) \
        & (acq_v[:, 2] < np.quantile(acq_v[:, 2], 0.7))
    nose_a = acq_v[band][np.argmin(acq_v[band, 1])]
    best = None
    for s0 in np.geomspace(2.0, 20.0, 13):
        t0 = nose_a - s0 * nose_t
        s, r, tt, err = tc.similarity_icp(src, src_n, target_raw, s=s0, t=t0, iterations=80, trim=0.6)
        rel = err / s
        if best is None or rel < best[-1]:
            best = (s, r, tt, err, rel)
    s, r, tt, err, rel = best
    # The acquisition, expressed in template metres.
    acq_m = (acq_v - tt) @ r / s
    target = tc.Target.from_mesh(acq_m, acq_t)

    # ---------------------------------------------------------------- non-rigid fit
    # Cavities (inside the mouth, the eye pockets behind the lids, nostrils,
    # ear canals) face space the acquisition never saw: fitting them folds
    # them onto the outer surface. The scalp region (which in MakeHuman's
    # layout reaches down to the brows) is under hair: it may be pulled in
    # onto skin the acquisition shows, never out onto strands.
    edges = t.edges
    exposed = t.exposure >= EXPOSED if t.exposure is not None else np.ones_like(body)
    data_w = (active & exposed).astype(float)
    fit = tc.nricp(t.verts, edges, active, data_w, target, tris, STIFFNESS,
                   max_dist=(0.02, 0.006), min_cos=0.5, inward_only=scalp)
    fitted = fit.verts

    # ---------------------------------------------------------------- features from the picture
    # The acquisition fixes the head's form; the approved picture fixes where
    # the eyes open, where the mouth sits and how the nose ends. Each detected
    # landmark is bound to the template surface once (through a render of the
    # template), the picture is registered to the first fit, and the fit is
    # rerun with those features held to the picture, depth left free.
    picture = None
    if a.picture_landmarks:
        cam = json.loads(Path(a.template_camera).read_text(encoding="utf-8"))
        tpl_px = np.array(json.loads(Path(a.template_landmarks).read_text())["landmarks_106"])
        img = json.loads(Path(a.picture_landmarks).read_text(encoding="utf-8"))
        img_px = np.array(img["landmarks_106"])
        feature_tris = tris[(active & body)[tris].all(1)]
        ids, bary, found = tc.bind_pixels(t.verts, feature_tris, cam, tpl_px)
        use = np.array([i for i in FEATURE_LANDMARKS if found[i]])
        stable = np.array([i for i in REGISTRATION_LANDMARKS if found[i]])

        def front(points):          # world -> picture-like plane (x right, -z down)
            return np.c_[points[:, 0], -points[:, 2]]

        first = np.einsum("lk,lkj->lj", bary, fitted[ids])
        ps, pr, pt = tc.similarity_2d(front(first[stable]), img_px[stable])
        back = (img_px - pt) @ pr / ps          # picture -> plane
        goal = first.copy()
        goal[:, 0], goal[:, 2] = back[:, 0], -back[:, 1]
        before_mm = np.linalg.norm(front(first[use]) - back[use], axis=1) * 1000
        weight = np.where(np.isin(use, JAW_LANDMARKS), JAW_WEIGHT, LANDMARK_WEIGHT)
        lm = tc.SurfaceLandmarks(ids=ids[use], bary=bary[use], points=goal[use],
                                 weight=weight, free_axis=1)
        # The picture outranks the acquisition at the lid margins and lips. Only
        # the two rings of lid next to the eye pocket let go of the acquisition
        # (its fused groove); the rest of the lid keeps the acquired brow and
        # socket depth.
        eye_pocket = np.flatnonzero(lids & ~exposed & active)
        margin = tc.ring_neighbours(eye_pocket, edges, len(t.verts), rings=2) & lids
        data_w2 = data_w.copy()
        data_w2[margin] = 0.0
        data_w2[lips] *= 0.3
        fit = tc.nricp(t.verts, edges, active, data_w2, target, tris, STIFFNESS, landmarks=lm,
                       max_dist=(0.02, 0.006), min_cos=0.5, inward_only=scalp)
        fitted = fit.verts
        after = np.einsum("lk,lkj->lj", bary, fitted[ids])
        after_mm = np.linalg.norm(front(after[use]) - back[use], axis=1) * 1000
        pupils = {side: back[k] for side, k in (("r", 38), ("l", 88))}
        picture = {
            "landmarks": str(a.picture_landmarks), "image": img.get("image"),
            "image_sha256": img.get("image_sha256"),
            "template_landmarks": str(a.template_landmarks),
            "registration": {"scale_px_per_m": float(ps), "rotation": pr.tolist(),
                             "translation_px": pt.tolist(), "stable": stable.tolist()},
            "constrained": use.tolist(),
            "feature_error_mm_before": {"median": float(np.median(before_mm)),
                                        "max": float(before_mm.max())},
            "feature_error_mm_after": {"median": float(np.median(after_mm)),
                                       "max": float(after_mm.max())},
            "per_landmark_mm_before": dict(zip(map(str, use.tolist()), np.round(before_mm, 2).tolist())),
            "per_landmark_mm_after": dict(zip(map(str, use.tolist()), np.round(after_mm, 2).tolist())),
        }

    # ---------------------------------------------------------------- hidden surfaces, folds
    interior = active & ~exposed
    fitted = tc.carry_interior(t.verts, fitted, interior, active)
    head_tris = tris[active[tris].all(1)]
    fitted, still_turned, unfold_rounds = tc.unfold(t.verts, fitted, head_tris, active, edges)

    # ---------------------------------------------------------------- carry-along parts
    mouth = np.zeros_like(body)
    teeth = np.concatenate([t.groups[g] for g in ("helper-upper-teeth", "helper-lower-teeth")
                            if g in t.groups])
    if len(teeth):
        near = np.linalg.norm(t.verts - t.verts[teeth].mean(0), axis=1) < 0.035
        mouth = interior & near
    region = {"eyelids": lids & active, "mouth": mouth}
    moved = {}
    for helper, follow in HELPER_FOLLOW.items():
        idx = t.groups.get(helper)
        if idx is None:
            continue
        ring = np.flatnonzero(region[follow])
        # Each side's eye follows its own lids.
        if helper in ("helper-l-eye", "helper-r-eye"):
            side = np.sign(t.verts[idx, 0].mean())
            ring = ring[np.sign(t.verts[ring, 0]) == side]
        fitted[idx] = tc.rigid_follow(t.verts[idx], t.verts[ring], fitted[ring])
        moved[helper] = int(len(ring))

    # The picture's pupils say where each eye looks out of its socket.
    if picture is not None:
        shifts = {}
        for side, pupil in pupils.items():
            idx = t.groups.get("helper-{}-eye".format(side))
            if idx is None:
                continue
            front_pt = fitted[idx][np.argmin(fitted[idx, 1])]
            shift = np.array([pupil[0] - front_pt[0], 0.0, -pupil[1] - front_pt[2]])
            shift = np.clip(shift, -PUPIL_SHIFT_LIMIT, PUPIL_SHIFT_LIMIT)
            fitted[idx] += shift
            shifts[side] = (shift * 1000).round(2).tolist()
        picture["eye_shift_mm"] = shifts

    # ---------------------------------------------------------------- expressions
    linear = tc.smooth_per_vertex(tc.rotation_scale(fit.affine), edges, len(t.verts), rounds=4)
    expr = {k: tc.transfer_deltas(d, linear) for k, d in t.expressions.items()}

    # ---------------------------------------------------------------- measurement
    fitted_body = fitted[active]
    d_out, _ = target.tree.query(fitted_body, workers=-1)
    face_sel = (active & face & ~scalp & ~lids)[active]
    keep_polys = []
    in_head = active.copy()
    for helper in HELPER_FOLLOW:
        if helper in t.groups:
            in_head[t.groups[helper]] = True
    for i, (st, tot) in enumerate(zip(t.starts, t.totals)):
        if in_head[t.loops[st:st + tot]].all():
            keep_polys.append(i)
    keep_polys = np.array(keep_polys)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    arrays = {"verts": fitted, "rest": t.verts, "loops": t.loops, "loop_starts": t.starts,
              "loop_totals": t.totals, "keep_polys": keep_polys,
              "acq_verts": acq_m.astype(np.float32), "acq_tris": acq_t}
    for k, d in expr.items():
        arrays["ex__" + k] = d.astype(np.float32)
    for k, idx in t.groups.items():
        if k.startswith("helper-") or k == "body":
            arrays["vg__" + k] = idx
    np.savez_compressed(out, **arrays)

    receipt = {
        "schema": "reference-asset-compiler.template-conform.v1",
        "part": "head",
        "template": {"path": str(a.template), "sha256": _sha(a.template)},
        "acquisition": {"path": str(a.acquisition), "sha256": _sha(a.acquisition)},
        "output": {"path": str(out), "sha256": _sha(out)},
        "alignment": {"scale_template_to_acquisition": float(s), "rotation": r.tolist(),
                      "translation": tt.tolist(), "face_rms_acquisition_units": float(err),
                      "face_rms_m": float(rel)},
        "active_vertices": int(active.sum()),
        "cavity_vertices": int((active & ~exposed).sum()),
        "turned_triangles_after_unfold": still_turned,
        "unfold_rounds": unfold_rounds,
        "data_vertices": int((data_w > 0).sum()),
        "stiffness": list(STIFFNESS),
        "fit_log": fit.log,
        "helpers_moved": moved,
        "distance_to_acquisition_m": {
            "face_median": float(np.median(d_out[face_sel])),
            "face_p95": float(np.quantile(d_out[face_sel], 0.95)),
            "face_max": float(d_out[face_sel].max()),
            "head_median": float(np.median(d_out)),
        },
        "expression_units": sorted(expr),
        "picture": picture,
    }
    Path(a.receipt).write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("alignment", "distance_to_acquisition_m")}, indent=1))
    print("fit steps", len(fit.log), "last", fit.log[-1])


if __name__ == "__main__":
    main()
