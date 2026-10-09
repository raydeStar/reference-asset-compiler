"""Carry mesh hair from the head it was cut from to another head conformed from the same template.

Mesh hair, step three (docs/CHARACTER_MESH_HAIR.md). Both heads are the same
template with the same vertex order, conformed to different scans.

Skin-follow (the default): each hair vertex moves with the skin under it, the
inverse-distance-squared weighted displacement of its --k nearest head vertices
(skull, face and upper neck) between the two heads. Hair cut from one scan then
sits on the skull of a head built from another (or on another character's).

--place-by-face: the template conformed to a stylised scan can be squashed (on
character-02's Pixal3D head its brow-to-chin was 10.0 cm against the scan's
own 13.5 cm, its brows 1.1 cm low), and hair that follows that skin keeps the
scan's absolute height: about 1 cm high against the character's brows, at the
scan's scale. Placed by the face instead, the hair goes where the scan's own
upper face (brows, nose bridge, eyes) lands on the character's:

1. the scan's landmarks: the detector's 68 points on a front render of the scan
   (render_mesh_view.py --arrays and detect_face_landmarks_dwpose.py, as for the
   conform's seed), bound to the scan's surface and carried into template
   metres by the conform's alignment (its receipt);
2. the same points on the character's head through the template's landmark
   binding (fit_head_placement.py --save-binding);
3. one similarity, with scale, from the first to the second on the upper face
   (UPPER_FACE), applied to the hair.

The placed hair can end up in or against the character's skin, which has a
different skull: keep_hair_clear.py pushes it out, after the reduction
(build_mesh_hair.py runs both).

Usage:
  python scripts/transfer_mesh_hair.py <hair.npz> <from-head.npz> <to-head.npz> <out.npz> [--k 12]
  python scripts/transfer_mesh_hair.py <hair.npz> <scan-conform.npz> <to-head.npz> <out.npz> --place-by-face \\
      --scan-landmarks dw-acq-front.json --scan-camera acq-front-camera.json --scan-receipt conform.json \\
      [--binding profiles/head-templates/hm08-male-face-landmarks.json]

The heads are conform_head_template.py or finish_template_head.py NPZs (verts,
loops, vg__body, vg__helper-l-eye); with --place-by-face the from-head is the
scan's conform NPZ (it carries the scan as acq_verts and acq_tris). Every other
array in hair.npz is copied unchanged. Prints a JSON report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from reference_asset_compiler import template_conform as tc  # noqa: E402

BINDING = ROOT / "profiles/head-templates/hm08-male-face-landmarks.json"
# The 68-point layout's brows (17-26), nose bridge (27-30) and eyes (36-47): what hair is placed by. The mouth and
# jaw are left out: they move with expression and are where a stylised scan's face differs most.
UPPER_FACE = tuple(range(17, 31)) + tuple(range(36, 48))


def transfer(points, src, dst, body, eye, k=12):
    """Displace points by the skin's motion from src to dst (same template vertex order)."""
    eye_z = src[eye][:, 2].mean()
    head = body[src[body, 2] > eye_z - 0.12]
    dist, j = cKDTree(src[head]).query(points, k=k)
    w = 1.0 / np.maximum(dist, 1e-4) ** 2
    w /= w.sum(1, keepdims=True)
    return points + np.einsum("nk,nkc->nc", w, dst[head][j] - src[head][j])


def head_points(verts, binding):
    """The head's landmarks through a template landmark binding; NaN where the template had none."""
    if len(verts) != binding["template_vertices"]:
        raise ValueError(f"the head has {len(verts)} vertices; the binding's template has "
                         f"{binding['template_vertices']}")
    pts = np.full((len(binding["vertices"]), 3), np.nan)
    for i, (ids, bary) in enumerate(zip(binding["vertices"], binding["barycentric"])):
        if ids is not None:
            pts[i] = np.asarray(bary) @ verts[np.asarray(ids)]
    return pts


def scan_points(acq_m, acq_tris, camera, pixels, alignment):
    """Landmark pixels on a front render of the scan, as scan surface points in template metres: (points, found).

    The conform NPZ keeps the scan in template metres (acq_verts); the render saw it in its own units. The
    conform's alignment (scan ~= s * template @ R.T + t) takes it back to those units to find each pixel's
    triangle, and the point is read off the template-metre copy.
    """
    s, r, t = (float(alignment["scale_template_to_acquisition"]), np.asarray(alignment["rotation"], float),
               np.asarray(alignment["translation"], float))
    with np.errstate(invalid="ignore"):   # degenerate triangles' barycentrics are NaN, and never inside
        ids, bary, found = tc.bind_pixels(tc.apply_similarity(acq_m, s, r, t), acq_tris, camera, pixels)
    return np.einsum("lk,lkj->lj", bary, acq_m[ids]), found


def place_by_face(points, scan_conform, receipt, to_head, scan_pixels, camera, binding):
    """Hair points placed by the scan's upper face on the head's: (points, report)."""
    marks = np.array(UPPER_FACE)
    src, found = scan_points(np.asarray(scan_conform["acq_verts"], float), np.asarray(scan_conform["acq_tris"]),
                             camera, np.asarray(scan_pixels, float)[marks], receipt["alignment"])
    dst = head_points(np.asarray(to_head["verts"], float), binding)[marks]
    ok = found & np.isfinite(dst).all(1)
    if ok.sum() < 6:
        raise ValueError(f"only {int(ok.sum())} upper-face landmarks land on both the scan and the head")
    s, r, t = tc.umeyama(src[ok], dst[ok])
    residual = np.linalg.norm(tc.apply_similarity(src[ok], s, r, t) - dst[ok], axis=1)
    report = {"placement": "face", "landmarks": marks[ok].tolist(), "scale": round(float(s), 5),
              "rotation_deg": round(float(np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1)))), 3),
              "residual_mm": {"median": round(float(np.median(residual)) * 1000, 2),
                              "max": round(float(residual.max()) * 1000, 2)}}
    return tc.apply_similarity(points, s, r, t), report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("hair")
    p.add_argument("from_head")
    p.add_argument("to_head")
    p.add_argument("out")
    p.add_argument("--k", type=int, default=12)
    p.add_argument("--place-by-face", action="store_true",
                   help="place the hair by the scan's upper face on the head's (the from-head is the scan's conform)")
    p.add_argument("--scan-landmarks", help="detect_face_landmarks_dwpose.py JSON of the scan's front render")
    p.add_argument("--scan-camera", help="that render's camera JSON (render_mesh_view.py)")
    p.add_argument("--scan-receipt", help="the scan's conform receipt (its alignment)")
    p.add_argument("--binding", default=str(BINDING), help="the template's face landmark binding")
    a = p.parse_args(argv)
    if a.place_by_face and not (a.scan_landmarks and a.scan_camera and a.scan_receipt):
        p.error("--place-by-face needs --scan-landmarks, --scan-camera and --scan-receipt")
    hair = dict(np.load(a.hair))
    src, dst = np.load(a.from_head, allow_pickle=True), np.load(a.to_head, allow_pickle=True)
    if src["verts"].shape != dst["verts"].shape:
        raise SystemExit("the two heads are not the same template (vertex counts differ)")
    points = hair["verts"].astype(np.float64)
    if a.place_by_face:
        pixels = json.loads(Path(a.scan_landmarks).read_text(encoding="utf-8"))["landmarks_68"]
        try:
            moved, report = place_by_face(
                points, src, json.loads(Path(a.scan_receipt).read_text(encoding="utf-8")), dst, pixels,
                json.loads(Path(a.scan_camera).read_text(encoding="utf-8")),
                json.loads(Path(a.binding).read_text(encoding="utf-8")))
        except ValueError as error:
            raise SystemExit(str(error)) from error
    else:
        moved = transfer(points, src["verts"], dst["verts"], src["vg__body"], src["vg__helper-l-eye"], a.k)
        report = {"placement": "skin"}
    shift = moved - points
    hair["verts"] = moved.astype(np.float32)
    np.savez(a.out, **hair)
    distance = np.linalg.norm(shift, axis=1) * 1000
    print(json.dumps({"vertices": int(len(moved)), **report,
                      "mean_shift_mm": np.round(shift.mean(0) * 1000, 1).tolist(),
                      "moved_mm": dict(zip(("p50", "p95", "max"), np.percentile(distance, [50, 95, 100]).round(1).tolist()))}))


if __name__ == "__main__":
    main()
