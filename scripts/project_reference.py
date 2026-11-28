"""Project the reference picture onto the faces of a Pixal3D model it shows, over the paint.

  python scripts/project_reference.py <painted.glb> <output.glb> <report.json> \
      --geometry <pixal-geometry report.json> --reference <picture> --blender <blender> [--minimum-fit 0.97]

The painter smooths away fine, high-contrast wear: on the WK-04.3 landing a pass
in 21 sections at 8192 still lost the reference's scratches and painted its dark
steel pale, on either geometry route. But Pixal3D builds its mesh in the
picture's own camera, so the picture itself can be laid onto the faces it shows,
scratch for scratch, and the painter kept for the faces it cannot see.

1. The picture must be the one the geometry was made from (the pixal-geometry
   report's picture hash). A revised reference renders the same object with its
   details a little elsewhere: projecting it onto geometry made from the earlier
   one doubled every bolt by 2 cm. Revise the picture, then make the geometry
   again.
2. The camera. Pixal3D crops the cutout to a square 1.1 times the object, sets
   the camera on the depth axis of its frame (x across, z depth, y up in the GLB
   it exports, x mirrored) at 0.5 / tan(fov / 2), with the field of view MoGe-2
   estimates and its log records. That camera is refined against the cutout's
   outline (small turns, the field of view, the framing), and a fit below
   --minimum-fit (intersection over union) is refused.
3. Where the painted model is. Levelling, sizing and unwrapping move the mesh;
   an affine map from Pixal3D's own game mesh to the painted one is fitted by
   nearest points, starting from the levelling transform, and refused above
   2 mm.
4. Blender lays the picture into the model's own layout and blends it with the
   paint, per texel, by how squarely each texel faces the camera, whether
   anything stands between them, and whether it is inside the (eroded) cutout
   (scripts/blender/project_reference_bake.py).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]
BAKE = ROOT / "scripts" / "blender" / "project_reference_bake.py"
MAX_AFFINE_RMS_M = 0.002
COMPONENTS = {5126: np.float32, 5125: np.uint32, 5123: np.uint16, 5121: np.uint8}
WIDTHS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _accessor(gltf, binary, index):
    accessor = gltf["accessors"][index]
    view = gltf["bufferViews"][accessor["bufferView"]]
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    kind = COMPONENTS[accessor["componentType"]]
    width = WIDTHS[accessor["type"]]
    item = np.dtype(kind).itemsize * width
    stride = view.get("byteStride", 0)
    if stride and stride != item:
        raw = np.frombuffer(binary, np.uint8, count=stride * accessor["count"], offset=offset)
        raw = raw.reshape(accessor["count"], stride)[:, :item]
        return np.frombuffer(raw.tobytes(), kind).reshape(accessor["count"], width)
    values = np.frombuffer(binary, kind, count=accessor["count"] * width, offset=offset)
    return values.reshape(accessor["count"], width) if width > 1 else values


def _node_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    if "scale" in node:
        matrix = np.diag(list(node["scale"]) + [1.0]) @ matrix
    if "rotation" in node:
        x, y, z, w = node["rotation"]
        rotation = np.eye(4)
        rotation[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
        matrix = rotation @ matrix
    if "translation" in node:
        move = np.eye(4)
        move[:3, 3] = node["translation"]
        matrix = move @ matrix
    return matrix


def load_glb(path: Path):
    """Every triangle of a GLB in its own world frame: positions and indices."""
    data = path.read_bytes()
    length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + length])
    binary = data[20 + length + 8:]
    positions, triangles, base = [], [], 0

    def walk(index, parent):
        nonlocal base
        node = gltf["nodes"][index]
        matrix = parent @ _node_matrix(node)
        if "mesh" in node:
            for primitive in gltf["meshes"][node["mesh"]]["primitives"]:
                points = _accessor(gltf, binary, primitive["attributes"]["POSITION"]).astype(np.float64)
                points = (np.c_[points, np.ones(len(points))] @ matrix.T)[:, :3]
                if "indices" in primitive:
                    indices = _accessor(gltf, binary, primitive["indices"]).astype(np.int64).reshape(-1, 3)
                else:
                    indices = np.arange(len(points)).reshape(-1, 3)
                positions.append(points)
                triangles.append(indices + base)
                base += len(points)
        for child in node.get("children", []):
            walk(child, matrix)

    for index in gltf["scenes"][gltf.get("scene", 0)]["nodes"]:
        walk(index, np.eye(4))
    return np.vstack(positions), np.vstack(triangles)


def turn(pitch: float, yaw: float, roll: float) -> np.ndarray:
    p, y, r = (math.radians(value) for value in (pitch, yaw, roll))
    about_x = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    about_z = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    about_y = np.array([[math.cos(r), 0, math.sin(r)], [0, 1, 0], [-math.sin(r), 0, math.cos(r)]])
    return about_y @ about_x @ about_z


def camera_frame(raw: np.ndarray) -> np.ndarray:
    """Pixal3D's camera frame from its exported GLB: x across (mirrored), z depth, y up."""
    return np.c_[-raw[:, 0], raw[:, 2], raw[:, 1]]


def project(params, raw: np.ndarray):
    pitch, yaw, roll, fov = params
    points = camera_frame(raw) @ turn(pitch, yaw, roll).T
    distance = 0.5 / math.tan(math.radians(fov) / 2.0)
    return points[:, 0] / (distance + points[:, 1]), -points[:, 2] / (distance + points[:, 1])


def fit_camera(raw, triangles, alpha, start_fov):
    """Small turns, field of view and framing that lay the mesh's outline over the cutout's."""
    height, width = alpha.shape
    ys, xs = np.nonzero(alpha)
    box = (xs.min(), ys.min(), xs.max(), ys.max())
    shrink = 384.0 / max(width, height)
    target = np.asarray(Image.fromarray(alpha.astype(np.uint8) * 255).resize(
        (int(width * shrink), int(height * shrink)))) > 127

    def framing(params):
        u, v = project(params, raw)
        scale = max(box[2] - box[0], box[3] - box[1]) / max(np.ptp(u), np.ptp(v))
        return (scale, (box[0] + box[2]) / 2 - scale * (u.max() + u.min()) / 2,
                (box[1] + box[3]) / 2 - scale * (v.max() + v.min()) / 2)

    def overlap(params):
        scale, ox, oy = framing(params)
        u, v = project(params, raw)
        points = np.c_[(u * scale + ox) * shrink, (v * scale + oy) * shrink]
        mask = Image.new("L", target.shape[::-1], 0)
        draw = ImageDraw.Draw(mask)
        for triangle in triangles:
            draw.polygon([tuple(points[index]) for index in triangle], fill=255)
        drawn = np.asarray(mask) > 127
        return float((drawn & target).sum()) / max(float((drawn | target).sum()), 1.0)

    best = (overlap((0.0, 0.0, 0.0, start_fov)), (0.0, 0.0, 0.0, start_fov))
    for step in (4.0, 2.0, 1.0, 0.5, 0.25):
        improved = True
        while improved:
            improved = False
            for index, sign in itertools.product(range(4), (-1, 1)):
                params = list(best[1])
                params[index] += sign * step * (2.0 if index == 3 else 1.0)
                if not 2.0 <= params[3] <= 60.0:
                    continue
                score = overlap(tuple(params))
                if score > best[0] + 1e-5:
                    best, improved = (score, tuple(params)), True
    scale, ox, oy = framing(best[1])
    return {"params": list(best[1]), "scale": scale, "offset": [ox, oy], "iou": best[0]}


def fit_affine(raw, painted, level_transform):
    """The affine map from Pixal3D's game mesh to the painted one, by nearest points."""
    raw = np.unique(np.round(raw, 6), axis=0)
    painted = np.unique(np.round(painted, 6), axis=0)
    tree = cKDTree(painted)
    gltf_to_blender = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float64)
    best = None
    for out in (gltf_to_blender.T, np.eye(3)):
        for stretch_axis, stretch in itertools.product(range(3), (1.0, 1.08)):
            sizing = np.eye(3)
            sizing[stretch_axis, stretch_axis] = stretch
            matrix = out @ sizing @ level_transform[:3, :3] @ gltf_to_blender
            shift = painted.mean(axis=0) - (raw @ matrix.T).mean(axis=0)
            for _ in range(40):
                distances, nearest = tree.query(raw @ matrix.T + shift)
                keep = distances < np.percentile(distances, 90)
                solved, *_ = np.linalg.lstsq(np.c_[raw[keep], np.ones(keep.sum())], painted[nearest[keep]],
                                             rcond=None)
                matrix, shift = solved[:3].T, solved[3]
            distances, _ = tree.query(raw @ matrix.T + shift)
            rms = float(np.sqrt((distances ** 2).mean()))
            if best is None or rms < best[0]:
                best = (rms, matrix, shift)
    return {"matrix": best[1].tolist(), "translation": best[2].tolist(), "rms_m": best[0]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--geometry", type=Path, required=True,
                        help="The pixal-geometry report of the mesh this model was painted on")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--blender", required=True)
    parser.add_argument("--minimum-fit", type=float, default=0.97)
    parser.add_argument("--timeout", type=int, default=3600)
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    args = parser.parse_args(argv)
    started = time.time()

    def refuse(message):
        print("[PROJECT] FAILED: " + message)
        return 1

    geometry = json.loads(args.geometry.read_text(encoding="utf-8"))
    if sha256(args.reference) != geometry.get("picture_sha256"):
        return refuse("the reference is not the picture this geometry was made from ({0}). A revised picture "
                      "renders its details a little elsewhere; make the geometry again from it with "
                      "pixal-geometry, then paint and project.".format(geometry.get("picture")))
    attempt = Path(geometry["attempt"])
    raw_path = attempt / "pixal-v{0}.glb".format(geometry["vertex_target"])
    cutout_path = attempt / "cutout.png"
    for needed in (raw_path, cutout_path):
        if not needed.is_file():
            return refuse("the geometry's attempt folder has no {0}".format(needed.name))
    logged = re.search(r"camera_angle_x=([0-9.]+)", (attempt / "pixal.log").read_text(encoding="utf-8",
                                                                                        errors="replace")) \
        if (attempt / "pixal.log").is_file() else None
    start_fov = math.degrees(float(logged.group(1))) if logged else 15.0

    raw, triangles = load_glb(raw_path)
    alpha = np.asarray(Image.open(cutout_path).convert("RGBA"))[:, :, 3] > 127
    if geometry.get("frame_check") is not None or geometry.get("mounts"):
        from pixal_frame import overlap, pixel_vertices, rasterize
        checked = geometry.get("frame_check", {})
        if (not checked.get("ok") or sha256(raw_path) != geometry["pixal"]["game_sha256"]
                or sha256(cutout_path) != geometry["cutout_sha256"]):
            return refuse("the mounted frame needs a passing check on these exact meshes and cutout")
        camera = dict(checked["camera"])
        camera["iou"] = overlap(alpha, rasterize(pixel_vertices(raw, camera), triangles, alpha.shape))
    else:
        camera = fit_camera(raw, triangles, alpha, start_fov)
    camera["logged_fov_degrees"] = round(start_fov, 3) if logged else None
    print("[PROJECT] camera fit {0:.4f}: turn {1}, fov {2:.2f} (Pixal3D logged {3})".format(
        camera["iou"], [round(value, 2) for value in camera["params"][:3]], camera["params"][3],
        camera["logged_fov_degrees"]))
    if camera["iou"] < args.minimum_fit:
        return refuse("the mesh's outline overlaps the cutout's by {0:.3f}, under {1}: the picture does not "
                      "line up with the geometry".format(camera["iou"], args.minimum_fit))
    painted, _ = load_glb(args.source)
    affine = fit_affine(raw, painted, np.array(geometry["level"]["transform"], dtype=np.float64))
    print("[PROJECT] painted model found from Pixal3D's mesh to {0:.2f} mm".format(affine["rms_m"] * 1000))
    if affine["rms_m"] > MAX_AFFINE_RMS_M:
        return refuse("the painted model is not Pixal3D's mesh moved and sized ({0:.1f} mm apart): paint the "
                      "game mesh this geometry report made".format(affine["rms_m"] * 1000))

    work = args.output.with_name(args.output.stem + "-projection")
    work.mkdir(parents=True, exist_ok=True)
    (work / "camera.json").write_text(json.dumps(camera, indent=1), encoding="utf-8")
    (work / "affine.json").write_text(json.dumps(affine, indent=1), encoding="utf-8")
    bake_report = work / "bake.json"
    done = subprocess.run([args.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(BAKE),
                           "--", str(args.source), str(args.output), str(bake_report), str(args.reference),
                           str(cutout_path), str(work / "camera.json"), str(work / "affine.json")],
                          capture_output=True, text=True, timeout=args.timeout)
    (work / "bake.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    if done.returncode != 0 or not args.output.is_file():
        return refuse("the projection bake did not finish (see {0})".format(work / "bake.log"))
    bake = json.loads(bake_report.read_text(encoding="utf-8"))
    report = {
        "schema": "reference-asset-compiler.reference-projection.v1",
        "source": str(args.source), "source_sha256": sha256(args.source),
        "output": str(args.output), "output_sha256": sha256(args.output),
        "reference": str(args.reference), "reference_sha256": sha256(args.reference),
        "geometry": str(args.geometry), "same_picture_as_geometry": True,
        "camera": camera, "affine_rms_m": round(affine["rms_m"], 6), "bake": bake,
        "next": "bake-detail without --relief-tilt: the picture's grain is not relief",
        "seconds": round(time.time() - started, 1),
        "requires_fixed_view_review": True, "production_grade": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[PROJECT] {0:.1%} of the sheet from the picture, in {1:.0f} s".format(
        bake.get("texels_from_picture_share", 0.0), report["seconds"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
