"""Paint a character's head again, on its own, and lay it over the body's atlas.

A full-body paint gives the head what a full-body view gives it. Twelve views
at 768, of a figure 1.85 metres tall, put a face into about ninety pixels of
each; the diffusion that decides what an eye looks like never saw more than
that, and no atlas size or upscaler afterwards can put back what it did not
see. So the head is cut out -- every face entirely above a height -- and
painted a second time with the reference cropped to the same region, so every
view is full of the head. Because no vertex and no UV changes, the second
paint lands in exactly the atlas rectangles the first one did, and laying it
over the body is a mask in UV space: head texels from the head paint, body
texels byte for byte from the body paint, a short blend across the cut.

Nothing here moves a vertex. Nothing here needs Blender: the mesh is read out
of the painted GLB directly, the head is written as an OBJ the painter already
accepts, and the maps are composited with numpy and put back into the same
file around the same buffer views.

The reference crop is the part worth being careful about. The playbook records
what a crop that kept a strip of armour did: the painter spread armour colour
over the whole head. The crop is taken from the figure's own silhouette -- the
background removed, the bounding box measured -- so it holds the head band and
a small margin, and nothing below it.

Usage:
  python scripts/paint_head_detail.py -- <painted.glb> <output.glb> <report.json> \
      --reference <image> --legacy-root <studio tree> \
      [--head-from 0.78] [--feather 0.03] [--views 12] [--resolution 768] [--atlas 4096]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compress_textures import read_glb, write_glb  # noqa: E402

TAG = "[HEAD]"
POWERSHELL = "powershell.exe"

COMPONENT_TYPES = {
    5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32,
}
COMPONENTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def failed(reason: str) -> int:
    print("{0} FAILED: {1}".format(TAG, reason))
    return 1


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--reference", type=Path, required=True,
                        help="The picture the body was painted from; the head is cropped out of it")
    parser.add_argument("--legacy-root", type=Path, required=True,
                        help="The studio tree holding the painter's environment and weights")
    parser.add_argument("--head-from", type=float, default=0.78,
                        help="Height, as a fraction of the model's, above which a face is head")
    parser.add_argument("--feather", type=float, default=0.03,
                        help="Blend band above the cut, as a fraction of the model's height")
    parser.add_argument("--views", type=int, default=12)
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--atlas", type=int, default=4096, choices=(2048, 4096))
    parser.add_argument("--crop-margin", type=float, default=0.06,
                        help="Extra around the head band in the reference crop, as a fraction of it")
    parser.add_argument("--launcher", type=Path,
                        default=Path(__file__).resolve().parent / "run_hy3d21_texture.ps1")
    return parser.parse_args(argv)


# --- reading the mesh out of the GLB ----------------------------------------

def accessor_array(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    dtype = np.dtype(COMPONENT_TYPES[accessor["componentType"]])
    width = COMPONENTS[accessor["type"]]
    count = accessor["count"]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride") or dtype.itemsize * width
    if stride == dtype.itemsize * width:
        flat = np.frombuffer(binary, dtype=dtype, count=count * width, offset=start)
        return flat.reshape(count, width).copy()
    rows = np.frombuffer(binary, dtype=np.uint8, count=stride * (count - 1) + dtype.itemsize * width,
                         offset=start)
    strided = np.lib.stride_tricks.as_strided(rows, shape=(count, dtype.itemsize * width),
                                              strides=(stride, 1))
    return np.ascontiguousarray(strided).view(dtype).reshape(count, width).copy()


def node_matrix(node):
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    scale = np.array(node.get("scale", [1, 1, 1]), dtype=np.float64)
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    rotation = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    matrix[:3, :3] = rotation * scale
    matrix[:3, 3] = node.get("translation", [0, 0, 0])
    return matrix


def mesh_from_glb(document, binary):
    """Every triangle in the file, in world space, with the UVs a painter needs.

    Returns positions (N, 3), uvs (N, 2) and triangles (M, 3) into them. A GLB
    already splits a vertex wherever its UV differs, so one index serves both.
    """
    positions, uvs, triangles = [], [], []
    offset = 0

    def visit(index, parent):
        nonlocal offset
        node = document["nodes"][index]
        world = parent @ node_matrix(node)
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                if primitive.get("mode", 4) != 4:
                    continue
                attributes = primitive["attributes"]
                if "TEXCOORD_0" not in attributes:
                    raise ValueError("a primitive carries no UVs, so its paint has nowhere to land")
                local = accessor_array(document, binary, attributes["POSITION"]).astype(np.float64)
                placed = local @ world[:3, :3].T + world[:3, 3]
                uv = accessor_array(document, binary, attributes["TEXCOORD_0"]).astype(np.float32)
                if "indices" in primitive:
                    faces = accessor_array(document, binary, primitive["indices"]).reshape(-1, 3)
                else:
                    faces = np.arange(len(local)).reshape(-1, 3)
                positions.append(placed.astype(np.float32))
                uvs.append(uv)
                triangles.append(faces.astype(np.int64) + offset)
                offset += len(local)
        for child in node.get("children", []):
            visit(child, world)

    scene = document["scenes"][document.get("scene", 0)]
    for root in scene["nodes"]:
        visit(root, np.eye(4))
    if not triangles:
        raise ValueError("the file carries no triangles")
    return np.concatenate(positions), np.concatenate(uvs), np.concatenate(triangles)


# --- deciding what is head -------------------------------------------------

def head_faces(positions, triangles, head_from):
    """Which triangles sit entirely above the cut, and where the cut is.

    Height is +Y, which is what glTF promises and what the browser payload
    stage exports. A face is head when its lowest vertex is above the cut:
    a face straddling it belongs to the body, so the cut never splits a
    triangle and the second paint never has to guess at half of one.
    """
    heights = positions[:, 1]
    low, high = float(heights.min()), float(heights.max())
    cut = low + head_from * (high - low)
    lowest = heights[triangles].min(axis=1)
    return lowest >= cut, cut, high - low


def face_weights(positions, triangles, kept, cut, height, feather):
    """0 at the cut rising to 1 a feather above it, per kept face."""
    lowest = positions[:, 1][triangles].min(axis=1)
    band = max(feather * height, 1e-9)
    weights = np.clip((lowest - cut) / band, 0.0, 1.0)
    return np.where(kept, weights, 0.0).astype(np.float32)


def write_obj(path: Path, positions, uvs, triangles, kept):
    """The head as the painter reads it: v, vt, and faces indexing both alike.

    Only the vertices the kept faces use, renumbered. The UV values are the
    file's own, so the paint lands where the body's did. glTF's UV origin is
    the top-left and OBJ's the bottom-left, so v is flipped on the way out --
    the same flip Blender's exporter made on the way in.
    """
    used = np.unique(triangles[kept])
    renumber = np.full(len(positions), -1, dtype=np.int64)
    renumber[used] = np.arange(len(used))
    faces = renumber[triangles[kept]] + 1
    lines = ["mtllib {0}.mtl".format(path.stem), "o head"]
    lines += ["v {0:.6f} {1:.6f} {2:.6f}".format(*p) for p in positions[used]]
    lines += ["vt {0:.6f} {1:.6f}".format(u, 1.0 - v) for u, v in uvs[used]]
    lines += ["s 0", "usemtl Material"]
    lines += ["f {0}/{0} {1}/{1} {2}/{2}".format(*face) for face in faces]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.with_suffix(".mtl").write_text(
        "newmtl Material\nKd 0.800 0.800 0.800\nd 1.0\nillum 2\n", encoding="utf-8")
    return len(used), int(kept.sum())


# --- the reference crop -----------------------------------------------------

def head_crop_box(alpha, head_from, margin):
    """A square around the head band of the figure's own silhouette.

    The figure's rows come from its alpha; the head band is the top
    (1 - head_from) of them, with a margin, and the columns are whatever the
    silhouette occupies within that band. Squared and clamped to the picture.
    Returns (left, top, right, bottom) in pixels, or None with no silhouette.
    """
    alpha = np.asarray(alpha)
    rows = np.where(alpha.max(axis=1) > 16)[0]
    if rows.size == 0:
        return None
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    height = bottom - top
    band = max(1, int(round((1.0 - head_from) * height * (1.0 + margin))))
    band_bottom = min(bottom, top + band)
    columns = np.where(alpha[top:band_bottom].max(axis=0) > 16)[0]
    if columns.size == 0:
        return None
    left, right = int(columns[0]), int(columns[-1]) + 1
    side = max(right - left, band_bottom - top)
    side = int(round(side * (1.0 + margin)))
    centre_x = (left + right) / 2.0
    centre_y = (top + band_bottom) / 2.0
    box = [int(round(centre_x - side / 2.0)), int(round(centre_y - side / 2.0))]
    box += [box[0] + side, box[1] + side]
    return tuple(box)


# --- laying the head paint over the body's ---------------------------------

def rasterize_weights(uvs, triangles, weights, size):
    """Per-face weights painted into UV space, higher weights on top."""
    sheet = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(sheet)
    order = np.argsort(weights, kind="stable")
    for face in order:
        weight = float(weights[face])
        if weight <= 0.0:
            continue
        points = [(float(u) * size, float(v) * size) for u, v in uvs[triangles[face]]]
        draw.polygon(points, fill=int(round(weight * 255)), outline=int(round(weight * 255)))
    return np.asarray(sheet, dtype=np.float32) / 255.0


def grow(weights, texels):
    """Push the mask outward so a bilinear sample at an island's edge is covered."""
    out = weights.copy()
    for _ in range(int(texels)):
        shifted = [np.roll(out, s, axis=a) for a in (0, 1) for s in (1, -1)]
        out = np.maximum.reduce([out, *shifted])
    return out


def blend(body: Image.Image, head: Image.Image, weights) -> Image.Image:
    """Head where the mask is, body where it is not, linear in between."""
    if head.size != body.size:
        head = head.resize(body.size, Image.LANCZOS)
    a = np.asarray(body.convert("RGB"), dtype=np.float32)
    b = np.asarray(head.convert("RGB"), dtype=np.float32)
    w = weights[..., None]
    out = a * (1.0 - w) + b * w
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8), "RGB")


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def image_bytes(document, binary, index):
    view = document["bufferViews"][document["images"][index]["bufferView"]]
    start = view.get("byteOffset", 0)
    return binary[start:start + view["byteLength"]]


def texture_image(document, slot):
    """The image index a material slot points at, or None."""
    if not slot or "index" not in slot:
        return None
    return document["textures"][slot["index"]].get("source")


def swap_images(document, binary, replacements):
    """The same file around new image bytes; every other view keeps its meaning."""
    views = document["bufferViews"]
    images = document.get("images", [])
    rebuilt = bytearray()
    for view_index, view in enumerate(views):
        owner = next((i for i, entry in enumerate(images) if entry.get("bufferView") == view_index), None)
        if owner is not None and owner in replacements:
            payload = replacements[owner]
            images[owner]["mimeType"] = "image/png"
        else:
            start = view.get("byteOffset", 0)
            payload = binary[start:start + view["byteLength"]]
        while len(rebuilt) % 4:
            rebuilt.append(0)
        view["byteOffset"] = len(rebuilt)
        view["byteLength"] = len(payload)
        rebuilt.extend(payload)
    while len(rebuilt) % 4:
        rebuilt.append(0)
    if document.get("buffers"):
        document["buffers"][0]["byteLength"] = len(rebuilt)
    return document, bytes(rebuilt)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def next_attempt(output: Path, label: str) -> Path:
    for number in range(1, 1000):
        attempt = output.parent / "{0}-{1}-attempt{2:03d}".format(output.stem, label, number)
        if not attempt.exists():
            return attempt
    raise RuntimeError("There are already 999 {0} attempts beside {1}".format(label, output))


def tail(text: str, lines: int = 12):
    return [line for line in (text or "").splitlines() if line.strip()][-lines:]


# --- the run -----------------------------------------------------------------

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    args = parse_arguments(argv)
    started = time.monotonic()

    if not args.source.is_file():
        return failed("source does not exist: {0}".format(args.source))
    if args.output.exists():
        return failed("refusing to overwrite {0}".format(args.output))
    if not args.reference.is_file():
        return failed("the reference does not exist: {0}".format(args.reference))
    if not 0.4 <= args.head_from <= 0.95:
        return failed("head-from is a fraction of the model's height between 0.4 and 0.95. "
                      "Got {0}".format(args.head_from))
    if not 0.0 <= args.feather <= 0.2:
        return failed("feather runs from 0 to 0.2 of the model's height. Got {0}".format(args.feather))
    if not args.launcher.is_file():
        return failed("the paint launcher is missing: {0}".format(args.launcher))
    venv = args.legacy_root / ".venv-hy3d21" / "Scripts" / "python.exe"
    if not venv.is_file():
        return failed("the painter's environment is missing: {0}".format(venv))

    raw = args.source.read_bytes()
    try:
        document, binary = read_glb(raw)
        positions, uvs, triangles = mesh_from_glb(document, binary)
    except (ValueError, KeyError, IndexError) as problem:
        return failed("the source could not be read as a painted model: {0}".format(problem))

    materials = document.get("materials", [])
    if not materials:
        return failed("the source carries no material, so there is no paint to lay a head over")
    pbr = materials[0].get("pbrMetallicRoughness", {})
    albedo_index = texture_image(document, pbr.get("baseColorTexture"))
    metal_rough_index = texture_image(document, pbr.get("metallicRoughnessTexture"))
    if albedo_index is None:
        return failed("the source's material has no base colour texture to lay a head over")
    if len(materials) > 1:
        # One material is what a painted model carries. More means somebody
        # has already changed its surfaces, and a second paint would fight that.
        return failed("the source carries {0} materials; paint the head before changing "
                      "surfaces, not after".format(len(materials)))

    kept, cut, height = head_faces(positions, triangles, args.head_from)
    share = float(kept.mean())
    if kept.sum() < 50:
        return failed("only {0} faces sit above {1:.0%} of the height, which is not a head. "
                      "Lower --head-from".format(int(kept.sum()), args.head_from))
    if share > 0.6:
        return failed("{0:.0%} of the model sits above {1:.0%} of its height, which is not a head. "
                      "Raise --head-from".format(share, args.head_from))

    attempt = next_attempt(args.output, "head")
    attempt.mkdir(parents=True)
    head_obj = attempt / "head.obj"
    head_vertices, head_triangles = write_obj(head_obj, positions, uvs, triangles, kept)

    # The crop runs in the painter's own environment, which is where the
    # background remover lives; this interpreter has no reason to carry one.
    crop_png = attempt / "reference-head.png"
    crop_json = attempt / "reference-head.json"
    cropper = Path(__file__).resolve().parent / "crop_reference_region.py"
    cropped = subprocess.run(
        [str(venv), str(cropper), str(args.reference), str(crop_png), str(crop_json),
         "--head-from", str(args.head_from), "--margin", str(args.crop_margin)],
        capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL, timeout=600)
    if cropped.returncode != 0 or not crop_png.is_file():
        return failed("the reference could not be cropped to the head: {0}".format(
            " ".join(tail(cropped.stdout + "\n" + cropped.stderr, 4))))
    crop = json.loads(crop_json.read_text(encoding="utf-8"))

    paint_dir = attempt / "paint"
    command = [
        POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(args.launcher),
        "-Mesh", str(head_obj), "-Reference", str(crop_png),
        "-OutputObj", str(paint_dir / "head.obj"), "-LegacyRoot", str(args.legacy_root),
        "-Views", str(args.views), "-Resolution", str(args.resolution),
        "-RunnerKind", "studio", "-Atlas", str(args.atlas),
    ]
    print("{0} painting {1} head faces of {2} ({3:.1%}) above {4:.3f} m, reference cropped to {5}".format(
        TAG, head_triangles, len(triangles), share, cut, crop.get("box")), flush=True)
    painted = subprocess.run(command, capture_output=True, text=True, errors="replace",
                             stdin=subprocess.DEVNULL, timeout=3000)
    head_glb = paint_dir / "head.glb"
    validation = paint_dir / "head.validation.json"
    if not head_glb.is_file() or not validation.is_file():
        return failed("the head paint produced nothing: {0}".format(
            " ".join(tail(painted.stderr, 6)) or " ".join(tail(painted.stdout, 6))))
    gate = json.loads(validation.read_text(encoding="utf-8-sig"))
    if not gate.get("faces_equal") or gate.get("geometry_delta", 1) > 1e-6 or gate.get("uv_delta", 1) > 1e-6:
        return failed("the head paint moved the head: {0}".format(json.dumps(gate, sort_keys=True)))

    head_document, head_binary = read_glb(head_glb.read_bytes())
    head_pbr = head_document["materials"][0].get("pbrMetallicRoughness", {})
    head_albedo_index = texture_image(head_document, head_pbr.get("baseColorTexture"))
    head_mr_index = texture_image(head_document, head_pbr.get("metallicRoughnessTexture"))
    if head_albedo_index is None:
        return failed("the head paint carries no base colour")

    body_albedo = Image.open(io.BytesIO(image_bytes(document, binary, albedo_index)))
    body_albedo.load()
    head_albedo = Image.open(io.BytesIO(image_bytes(head_document, head_binary, head_albedo_index)))
    head_albedo.load()
    size = body_albedo.size[0]
    weights = face_weights(positions, triangles, kept, cut, height, args.feather)
    sheet = grow(rasterize_weights(uvs, triangles, weights, size), 2)

    replacements = {albedo_index: png_bytes(blend(body_albedo, head_albedo, sheet))}
    metal_rough_blended = False
    if metal_rough_index is not None and head_mr_index is not None:
        body_mr = Image.open(io.BytesIO(image_bytes(document, binary, metal_rough_index)))
        head_mr = Image.open(io.BytesIO(image_bytes(head_document, head_binary, head_mr_index)))
        body_mr.load()
        head_mr.load()
        replacements[metal_rough_index] = png_bytes(blend(body_mr, head_mr, sheet))
        metal_rough_blended = True

    document, rebuilt = swap_images(document, binary, replacements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(write_glb(document, rebuilt))

    # The sheet the decision was made on, kept beside the paint as evidence.
    Image.fromarray((sheet * 255).astype(np.uint8), "L").save(attempt / "head-weights.png")

    report = {
        "schema": "reference-asset-compiler.head-detail-paint.v1",
        "source": str(args.source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output": str(args.output),
        "output_sha256": sha256(args.output),
        "reference": str(args.reference),
        "reference_sha256": sha256(args.reference),
        "head": {
            "from_height_fraction": args.head_from,
            "cut_height_m": round(cut, 4),
            "model_height_m": round(height, 4),
            "faces": head_triangles,
            "of_faces": int(len(triangles)),
            "share": round(share, 4),
            "vertices": head_vertices,
            "feather_fraction": args.feather,
        },
        "reference_crop": crop,
        "head_paint": {
            "attempt": str(attempt),
            "views": args.views,
            "resolution": args.resolution,
            "atlas": args.atlas,
            "gate": {key: gate.get(key) for key in ("faces_equal", "geometry_delta", "uv_delta", "atlas")},
            "launcher_exit_code": painted.returncode,
            "head_map_size": list(head_albedo.size),
            "resized_to_body": head_albedo.size != body_albedo.size,
        },
        "composite": {
            "atlas_size": size,
            "head_texels": int((sheet > 0).sum()),
            "band_texels": int(((sheet > 0) & (sheet < 1)).sum()),
            "atlas_fraction": round(float((sheet > 0).mean()), 4),
            "base_colour_replaced": True,
            "metallic_roughness_replaced": metal_rough_blended,
            "body_texels": "byte for byte from the body paint outside the head",
        },
        "geometry_unchanged": True,
        "uvs_unchanged": True,
        "seconds": round(time.monotonic() - started, 1),
        "requires_fixed_view_review": True,
        "production_grade": False,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("{0} laid a {1}-view head paint over {2:.1%} of the atlas in {3:.0f} s".format(
        TAG, args.views, report["composite"]["atlas_fraction"], report["seconds"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
