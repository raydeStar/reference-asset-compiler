"""Fit where the template head sits on the body from the face's landmarks.

assemble_character.py reads `placement.json` (`scale` and `location`): the
conformed head's objects get that uniform scale and location on the body, so a
head vertex v lands at scale * v + location in character space (x across,
y front-negative, z up, feet on z=0). For the first character the numbers came
from a by-hand loop: assemble, render the front, crop the head, detect its 68
DWPose landmarks, match them against the same crop of the painting, repeat.

This needs no render. The template's 68 landmarks are bound once to its surface
(a triangle and barycentric weights for each, through a front render of the
template and its DWPose detection: the files conform_head_template.py takes as
--template-landmarks/--template-camera). The conformed head has the template's
vertex order, so the same binding gives the head's landmarks in 3D. They are
projected through the source pictures' orthographic frame (the profile's
`source_camera` and `body_lift_m`), and the scale and the x/z location are
solved by linear least squares against the reference picture's landmarks:

  u = origin_x + px_per_m * (scale * x + location_x)
  v = origin_y + px_per_m * (body_lift - scale * z - location_z)

Depth (location y) does not show in a front picture. It comes from the neck:
the middle of the head's open neck ring is put over --body-neck-y (0: the scan
is centred on y=0, and assemble_character.py's neck-overlap ellipse is too), or
--location-y sets it outright.

Fit the head the build will place: rebuild_character.py first moves the
conformed head's lower face to the painting's proportions
(transport_face_proportions.py, with the profile's mouth-corner lift).
--transport-receipt runs that stage here, on the reference landmarks, so the
conformed head can be passed as it is; without it, pass a transported head.
On the first character the untransported head put the face 3.1 mm (mean) from
the hand-fitted placement, against 0.8 mm for the transported one.

The reference landmarks are DWPose's on a head crop of the reference picture
(the picture in the source frame: the painting, or the front guidance). Either
pass them (--reference-landmarks, with the crop box they were detected in), or
let this crop the head and run scripts/detect_face_landmarks_dwpose.py on the
CPU (--detect; needs a Python with torch and the DWPose TorchScript weights, the
same RAC_COMFYUI / RAC_TORCH_PYTHON / RAC_DWPOSE as rig_ue5_character.py). The
default crop is 0.34 x 0.31 m from 2 cm above the figure's top, centred on the
body's origin, upscaled about 1000 px tall.

The default landmark set is the 12 the conform registers with (eye corners,
nose tip, base and wings, mouth corners and centres): fixed points, whereas the
jaw contour and brows are silhouettes and painted hair. Projected onto the
first character's front render they sat 0.44 px rms from DWPose's own
detection on it.

Usage (a finished head: finish_template_head.py's head.npz and head.json):
  python scripts/fit_head_placement.py --head <finish>/head.npz --transport-receipt <finish>/head.json \
      --binding profiles/head-templates/hm08-male-face-landmarks.json \
      --profile profiles/characters/<id>.json \
      --reference <pictures>/original.png --detect --out <work>/placement \
      [--compare <bundle>/placement.json]
  or, with a head already transported (a build's head.npz): no --transport-receipt
  or, with landmarks already detected on a crop:
      --reference-landmarks <bundle>/original-landmarks.json --reference-crop 674 5 855 172
  or, binding from the template's own files (and saving it):
      --template <bundle>/template.npz --template-landmarks dw-template-front.json \
      --template-camera template-front-camera.json --save-binding binding.json

Writes <out>/placement.json (what assemble_character.py reads, plus the fit's
receipt) and prints a summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler import template_conform as tc  # noqa: E402

# The 68-point layout (iBUG 300-W; DWPose) with each eye's outline centre
# appended as 68 and 69, as conform_head_template.py reads it.
LANDMARK_SETS = {
    "stable": (36, 39, 42, 45, 30, 33, 31, 35, 48, 54, 51, 57),
    "features": tuple(range(27, 68)),
    "all": tuple(range(68)),
}
# The template head region conform_head_template.py binds landmarks on.
HEAD_WEIGHT = 0.3
# The original workstation's install, used only when RAC_COMFYUI is unset.
LOCAL_COMFYUI = r"C:\Users\Ayric\Source\Repos\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable"
DWPOSE_WEIGHTS = ("ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/hr16/DWPose-TorchScript-BatchSize5/"
                  "dw-ll_ucoco_384_bs5.torchscript.pt")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_landmarks(path):
    """68 DWPose points plus the two eye centres, and the picture size."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if "landmarks_68" not in d:
        raise SystemExit(f"{path}: expected a 68-point DWPose file (detect_face_landmarks_dwpose.py)")
    px = np.array(d["landmarks_68"], float)
    size = d["size"] if not isinstance(d["size"], str) else json.loads(d["size"])
    return np.vstack([px, px[36:42].mean(0), px[42:48].mean(0)]), [float(s) for s in size]


# ----------------------------------------------------------------------------- binding
def bind_template(template, landmarks, camera):
    """Each template landmark as a surface point: (vertex triple, barycentric) or None."""
    t = tc.load_template(template)
    body = np.zeros(len(t.verts), bool)
    body[t.groups["body"]] = True
    active = body & ((t.bone_weight("head") + t.bone_weight("neck_01")) >= HEAD_WEIGHT)
    tris = t.tris[active[t.tris].all(1)]
    cam = json.loads(Path(camera).read_text(encoding="utf-8"))
    pixels, _ = read_landmarks(landmarks)
    ids, bary, found = tc.bind_pixels(t.verts, tris, cam, pixels)
    return {
        "schema": "reference-asset-compiler.face-landmark-binding.v1",
        "_comment": "fit_head_placement.py --save-binding: each DWPose landmark of the template's front render "
                    "as a surface point (three template vertex indices and barycentric weights). A head "
                    "conformed from this template keeps its vertex order, so the binding serves every such head.",
        "layout": "68 DWPose points, then the right and left eye outline centres (68, 69)",
        "template_vertices": int(len(t.verts)),
        "template_sha256": sha(template),
        "template_landmarks_sha256": sha(landmarks),
        "template_camera": cam,
        "vertices": [ids[i].tolist() if found[i] else None for i in range(len(pixels))],
        "barycentric": [bary[i].round(9).tolist() if found[i] else None for i in range(len(pixels))],
    }


def head_points(verts, binding):
    """The head's landmarks in its own space; NaN where the template had none."""
    if len(verts) != binding["template_vertices"]:
        raise SystemExit(f"The head has {len(verts)} vertices; the binding's template has "
                         f"{binding['template_vertices']}. Bind the template this head was conformed from.")
    pts = np.full((len(binding["vertices"]), 3), np.nan)
    for i, (ids, bary) in enumerate(zip(binding["vertices"], binding["barycentric"])):
        if ids is not None:
            pts[i] = np.asarray(bary) @ verts[np.asarray(ids)]
    return pts


def neck_ring_centre_y(head):
    """Middle (in y) of the head's lowest open boundary: where the neck ends."""
    polys = [head["loops"][int(s):int(s) + int(n)]
             for s, n in zip(head["loop_starts"][head["keep_polys"]], head["loop_totals"][head["keep_polys"]])]
    tris = np.concatenate([np.stack([np.repeat(f[0], len(f) - 2), f[1:-1], f[2:]], 1) for f in polys])
    verts = head["verts"]
    ring = tc.boundary_vertices(tris, len(verts))
    low = ring & (verts[:, 2] < verts[ring, 2].min() + 0.03)
    return float((verts[low, 1].min() + verts[low, 1].max()) / 2)


# ----------------------------------------------------------------------------- reference
def default_crop(camera, body_lift, height_m, size_m=(0.34, 0.31), above_m=0.02):
    """A head box in the reference picture: from just above the figure's top, centred on the origin."""
    ppm, (ox, oy) = camera["px_per_m"], camera["front_origin_px"]
    top = oy + (body_lift - height_m) * ppm - above_m * ppm
    half = size_m[0] * ppm / 2
    w, h = camera["image_px"]
    box = [round(ox - half), round(top), round(ox + half), round(top + size_m[1] * ppm)]
    return [max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])]


def detect(picture, box, out, torch_python, model, target_px=1000):
    """Crop the head, upscale it, and run DWPose on it on the CPU."""
    from PIL import Image
    img = Image.open(picture).convert("RGB")
    up = max(1, round(target_px / (box[3] - box[1])))
    crop = img.crop(tuple(box)).resize(((box[2] - box[0]) * up, (box[3] - box[1]) * up), Image.LANCZOS)
    crop_path, lm_path = out / "reference-head-crop.png", out / "reference-landmarks.json"
    crop.save(crop_path)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    subprocess.run([torch_python, str(ROOT / "scripts/detect_face_landmarks_dwpose.py"), str(crop_path),
                    str(lm_path), "--model", str(model), "--overlay", str(out / "reference-landmarks.png")],
                   check=True, env=env)
    return lm_path


def to_picture(pixels, size, box):
    """Crop pixels back to the full reference picture (the crop may have been resized)."""
    if box is None:
        return pixels
    x0, y0, x1, y1 = box
    return np.array([x0, y0]) + pixels / np.array([size[0] / (x1 - x0), size[1] / (y1 - y0)])


# ----------------------------------------------------------------------------- fit
def project(points, scale, location, camera, body_lift):
    ppm, (ox, oy) = camera["px_per_m"], camera["front_origin_px"]
    world = scale * points + np.asarray(location, float)
    return np.c_[ox + ppm * world[:, 0], oy + ppm * (body_lift - world[:, 2])]


def fit_scale_xz(points, pixels, camera, body_lift):
    """Least-squares scale and x/z location putting ``points`` on ``pixels``."""
    ppm, (ox, oy) = camera["px_per_m"], camera["front_origin_px"]
    n = len(points)
    a = np.zeros((2 * n, 3))
    b = np.zeros(2 * n)
    a[0::2, 0], a[0::2, 1], b[0::2] = ppm * points[:, 0], ppm, pixels[:, 0] - ox
    a[1::2, 0], a[1::2, 2], b[1::2] = -ppm * points[:, 2], -ppm, pixels[:, 1] - oy - ppm * body_lift
    (scale, x, z), *_ = np.linalg.lstsq(a, b, rcond=None)
    return float(scale), float(x), float(z)


def compare(points, head_verts, fitted, other, camera, body_lift):
    """How far the face (the fitted landmarks) and the whole head land from another placement."""
    def shift(pts, axes):
        d = (fitted["scale"] - other["scale"]) * pts + np.subtract(fitted["location"], other["location"])
        mm = np.linalg.norm(d[:, axes], axis=1) * 1000
        return {"mean": round(float(mm.mean()), 2), "max": round(float(mm.max()), 2)}
    px = np.linalg.norm(project(points, fitted["scale"], fitted["location"], camera, body_lift)
                        - project(points, other["scale"], other["location"], camera, body_lift), axis=1)
    return {"placement": str(other.get("_path", "")),
            "scale": other["scale"], "location": other["location"],
            "scale_change_percent": round(100 * (fitted["scale"] / other["scale"] - 1), 3),
            "location_change_mm": [round(1000 * (p - q), 2) for p, q in zip(fitted["location"], other["location"])],
            "landmark_shift_xz_mm": shift(points, [0, 2]),
            "landmark_shift_px": {"mean": round(float(px.mean()), 2), "max": round(float(px.max()), 2)},
            "landmark_shift_mm": shift(points, [0, 1, 2]),
            "head_shift_xz_mm": shift(head_verts, [0, 2]),
            "head_shift_mm": shift(head_verts, [0, 1, 2])}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--head", required=True, help="conformed (and proportion-transported) head NPZ")
    p.add_argument("--out", required=True, help="directory for placement.json and detection files")
    bind = p.add_argument_group("landmark binding (one of)")
    bind.add_argument("--binding", help="saved binding JSON, e.g. profiles/head-templates/hm08-male-face-landmarks.json")
    bind.add_argument("--template", help="template NPZ the head was conformed from")
    bind.add_argument("--template-landmarks", help="DWPose JSON of the template's front render")
    bind.add_argument("--template-camera", help="render_mesh_view.py camera JSON of that render")
    bind.add_argument("--save-binding", help="write the binding computed from --template* here")
    frame = p.add_argument_group("source frame")
    frame.add_argument("--profile", help="character profile: source_camera and body_lift_m")
    frame.add_argument("--source-camera", type=float, nargs=5,
                       metavar=("PX_PER_M", "WIDTH", "HEIGHT", "ORIGIN_X", "ORIGIN_Y"))
    frame.add_argument("--body-lift", type=float, help="metres from the centred body's origin to the floor")
    frame.add_argument("--height-m", type=float, help="figure height for the default crop (default 2 x body lift)")
    ref = p.add_argument_group("reference landmarks")
    ref.add_argument("--reference", help="the reference picture in the source frame (the painting)")
    ref.add_argument("--reference-landmarks", help="DWPose JSON detected on a head crop of it")
    ref.add_argument("--reference-crop", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"),
                     help="the crop box those landmarks were detected in (picture pixels); omit if uncropped")
    ref.add_argument("--detect", action="store_true", help="crop the head and run DWPose on the CPU")
    ref.add_argument("--comfyui", default=os.environ.get("RAC_COMFYUI", LOCAL_COMFYUI))
    ref.add_argument("--torch-python", default=os.environ.get("RAC_TORCH_PYTHON"))
    ref.add_argument("--dwpose", default=os.environ.get("RAC_DWPOSE"))
    fit = p.add_argument_group("fit")
    fit.add_argument("--landmarks", default="stable", choices=sorted(LANDMARK_SETS),
                     help="which landmarks to fit (default: the conform's 12 registration points)")
    fit.add_argument("--location-y", type=float, help="depth outright (default: from the neck)")
    fit.add_argument("--body-neck-y", type=float, default=0.0,
                     help="y of the body's neck centre; the head's neck ring is centred over it")
    fit.add_argument("--max-rms-px", type=float, default=3.0, help="refuse a worse fit (exit 1)")
    fit.add_argument("--compare", help="another placement.json to report the difference from")
    fit.add_argument("--transport-receipt",
                     help="the head's conform receipt (head.json): first move --head's lower face to the "
                          "reference's proportions with transport_face_proportions.py, as the build does, "
                          "and fit that head (written to <out>/head-transported.npz)")
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    if a.binding:
        binding = json.loads(Path(a.binding).read_text(encoding="utf-8"))
    elif a.template and a.template_landmarks and a.template_camera:
        binding = bind_template(a.template, a.template_landmarks, a.template_camera)
        if a.save_binding:
            Path(a.save_binding).write_text(json.dumps(binding, indent=1) + "\n", encoding="utf-8")
    else:
        p.error("give --binding, or --template with --template-landmarks and --template-camera")

    profile = json.loads(Path(a.profile).read_text(encoding="utf-8")) if a.profile else {}
    if a.source_camera:
        ppm, w, h, ox, oy = a.source_camera
        camera = {"px_per_m": ppm, "image_px": [int(w), int(h)], "front_origin_px": [ox, oy]}
    elif "source_camera" in profile:
        camera = profile["source_camera"]
    else:
        p.error("give --profile (with source_camera) or --source-camera")
    body_lift = a.body_lift if a.body_lift is not None else profile.get("body_lift_m")
    if body_lift is None:
        p.error("give --body-lift or a profile with body_lift_m")

    crop = list(a.reference_crop) if a.reference_crop else None
    if a.detect:
        if not a.reference:
            p.error("--detect needs --reference")
        crop = crop or default_crop(camera, body_lift, a.height_m or 2 * body_lift)
        comfyui = Path(a.comfyui)
        torch_python = a.torch_python or str(comfyui / "python_embeded" / "python.exe")
        model = a.dwpose or str(comfyui / DWPOSE_WEIGHTS)
        reference_landmarks = detect(a.reference, [int(c) for c in crop], out, torch_python, model)
    elif a.reference_landmarks:
        reference_landmarks = Path(a.reference_landmarks)
    else:
        p.error("give --reference-landmarks (with --reference-crop) or --reference with --detect")
    crop_pixels, crop_size = read_landmarks(reference_landmarks)
    pixels = to_picture(crop_pixels, crop_size, crop)

    head_path, transported_by = Path(a.head), None
    if a.transport_receipt:
        head_path = out / "head-transported.npz"
        lift = profile.get("face_proportions", {}).get("mouth_corner_lift_mm")
        command = [sys.executable, str(ROOT / "scripts/transport_face_proportions.py"), str(a.head),
                   str(a.transport_receipt), str(reference_landmarks), str(head_path)]
        command += ["--mouth-corner-lift", *map(str, lift)] if lift else []
        subprocess.run(command, check=True)
        transported_by = command[1:]
    z = np.load(head_path)
    head = {k: z[k] for k in ("verts", "loops", "loop_starts", "loop_totals", "keep_polys")}
    points = head_points(head["verts"], binding)
    use = np.array([i for i in LANDMARK_SETS[a.landmarks] if not np.isnan(points[i]).any()])
    if len(use) < 6:
        raise SystemExit(f"Only {len(use)} landmarks are bound on the template; need at least 6")
    scale, x, zloc = fit_scale_xz(points[use], pixels[use], camera, body_lift)
    if a.location_y is not None:
        y, y_from = a.location_y, "--location-y"
    else:
        neck_y = neck_ring_centre_y(head)
        y = a.body_neck_y - scale * neck_y
        y_from = f"head neck ring centre y {neck_y:.4f} m placed over body neck y {a.body_neck_y} m"
    residual = project(points[use], scale, (x, y, zloc), camera, body_lift) - pixels[use]
    rms = float(np.sqrt((residual ** 2).sum(1).mean()))
    placement = {
        "scale": scale, "location": [x, y, zloc], "rms_error_px": rms,
        "method": "template landmarks projected through the source frame; least-squares scale and x/z",
        "landmarks": a.landmarks, "landmark_indices": use.tolist(),
        "residual_px": {str(i): np.round(r, 2).tolist() for i, r in zip(use, residual)},
        "location_y_from": y_from,
        "source_camera": {k: camera[k] for k in ("image_px", "px_per_m", "front_origin_px")},
        "body_lift_m": body_lift,
        "reference": {"landmarks": str(Path(reference_landmarks).resolve()), "landmarks_sha256": sha(reference_landmarks),
                      "crop_box_px": crop, "picture": str(Path(a.reference).resolve()) if a.reference else None},
        "head": {"path": str(head_path.resolve()), "sha256": sha(head_path), "transported_by": transported_by},
        "binding_template_sha256": binding["template_sha256"],
    }
    if a.compare:
        other = json.loads(Path(a.compare).read_text(encoding="utf-8"))
        other["_path"] = str(Path(a.compare).resolve())
        kept = np.unique(np.concatenate([head["loops"][int(s):int(s) + int(n)] for s, n in
                                         zip(head["loop_starts"][head["keep_polys"]],
                                             head["loop_totals"][head["keep_polys"]])]))
        placement["compared_with"] = compare(points[use], head["verts"][kept], placement, other, camera, body_lift)
    (out / "placement.json").write_text(json.dumps(placement, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: placement[k] for k in ("scale", "location", "rms_error_px", "location_y_from")
                      + (("compared_with",) if a.compare else ())}, indent=2))
    if rms > a.max_rms_px:
        print(f"Fit rms {rms:.2f} px exceeds --max-rms-px {a.max_rms_px}: check the crop and the landmarks.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
