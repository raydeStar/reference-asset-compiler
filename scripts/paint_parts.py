"""Paint a model part by part, each from the reference with the other parts masked out.

Painted whole, a model's parts bleed into each other: the painter sees them
overlap in its views and carries one part's colour onto another. On the
skiff the fin's red landed on the strut that holds it. Cutting the model into
grid sections does not help, because a section cuts across parts as readily
as a whole paint does.

This takes a part labelling from `label_parts.py` and paints each piece
alone with the model's own UVs: the base part (a boat's hull) as one piece,
and every other part as one piece per cluster of it. Runs of a part within
--join metres of each other are one piece (the seat's separate shells); runs
further apart are painted apart, unless the part is painted together (see
below). Each piece is painted from the reference with every pixel of the
other parts made transparent, cropped to that piece's own region, and laid
back onto exactly its own faces' texels. Where two parts meet the colour
changes at the edge: no blend, nothing projected across.

What the skiff taught, each rule measured on it (docs/DECISIONS.md):

- The base part's picture keeps the whole figure. Where another part covered
  it (the seat standing on the floor, a fin across the side) the hole is
  filled from the colours round it; left transparent, the painter is shown a
  cut-out shape and may paint it onto the floor.
- A part's mask is closed over its holes with the picture's own pixels. The
  detector gave the strut crossing a fin to the hull, and the painter copied
  that hole onto the fin as white marks.
- A thin part whose pieces repeat (the two fins) is painted together, one
  piece, from a picture of all of them (`"together": true` in the
  vocabulary, or --together). Painted one at a time, one fin came back pale
  and the other marked; together both came back red, cream and red.
- Roughness and metal are kept from the first paint by default (--surface
  first). Isolated, the fins came back glossy (roughness 0.45 to 0.6 against
  the first paint's 0.7 to 0.76) and the sun washed them out.

The result is a new base for `paint_sections.py`: the sections' fine light
and dark go over it as over a first paint, and they need not be painted
again (`--reuse-sections` finds them by mesh and crop, which a base does not
change).

The pieces are painted as the sections are: one painter run for them all, its
models loaded once, each piece's maps written while the next one paints
(`--separate-runs` starts one per piece, as before), and each piece fills only
the texels near its own faces that no view saw (`--inpaint-reach`). A piece
is laid on its own faces' texels only, so the rest of its sheet was never read.

Usage:
  python scripts/paint_parts.py -- <painted.glb> <output.glb> <report.json> \\
      --parts <labels.npz> --reference <image> --legacy-root <studio tree> \\
      [--atlas 8192] [--views 12] [--resolution 768] [--together fin] \\
      [--surface first] [--reuse-parts <earlier attempt>] [--plan-only] \\
      [--inpaint-reach 32] [--separate-runs] [--no-upscale]
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paint_sections as ps  # noqa: E402
from label_parts import face_neighbours, mesh_sha256  # noqa: E402

TAG = "[PAINT-PARTS]"
SCHEMA = "reference-asset-compiler.part-paint.v1"
LEAST_REGION_PIXELS = 300


def failed(reason: str) -> int:
    print("{0} FAILED: {1}".format(TAG, reason))
    return 1


def parse_arguments(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--parts", type=Path, required=True, help="the labelling label_parts.py wrote (.npz)")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--legacy-root", type=Path)
    parser.add_argument("--cutout", type=Path, help="the reference with its background removed (RGBA)")
    parser.add_argument("--launcher", type=Path, default=Path(__file__).resolve().parent / "run_hy3d21_texture.ps1")
    parser.add_argument("--atlas", type=int, default=8192, choices=(2048, 4096, 8192))
    parser.add_argument("--views", type=int, default=12)
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--min-free-vram", type=int, default=0)
    parser.add_argument("--crop-margin", type=float, default=0.12)
    parser.add_argument("--min-piece", type=int, default=60,
                        help="faces; a smaller run of a part takes the label most of its neighbours have")
    parser.add_argument("--join", type=float, default=0.05,
                        help="metres; runs of a part closer than this are one piece")
    parser.add_argument("--together", nargs="*",
                        help="parts painted as one piece however far apart their runs (default: the "
                             "vocabulary's own 'together' parts)")
    parser.add_argument("--surface", choices=("first", "parts"), default="first",
                        help="roughness and metal from the first paint (default) or from the part paints")
    parser.add_argument("--reuse-parts", type=Path,
                        help="an earlier attempt; a piece it painted from the same mesh and crop is reused")
    parser.add_argument("--inpaint-reach", type=int, default=32,
                        help="fill the texels no view saw only within at least this many texels of each "
                             "piece's faces (wider where the views left deeper gaps); 0 fills the whole sheet")
    parser.add_argument("--separate-runs", action="store_true",
                        help="start the painter once for each piece instead of once for them all")
    parser.add_argument("--no-upscale", action="store_true",
                        help="skip the painter's 4x upscale of each view; every view is resized to the "
                             "piece's bake size anyway")
    parser.add_argument("--plan-only", action="store_true")
    return parser.parse_args(argv)


# --- the pieces ------------------------------------------------------------------

def absorb_small_runs(labels, a, b, least):
    """Runs of a label smaller than `least` faces take the label most of their neighbours have."""
    labels = labels.copy()
    for _ in range(3):
        same = labels[a] == labels[b]
        graph = coo_matrix((np.ones(same.sum()), (a[same], b[same])), shape=(len(labels),) * 2)
        _, run = connected_components(graph, directed=False)
        small = np.bincount(run)[run] < least
        border = (labels[a] != labels[b])
        votes = np.zeros((len(labels), int(labels.max()) + 1))
        into_a = border & small[a] & ~small[b]
        into_b = border & small[b] & ~small[a]
        np.add.at(votes, (a[into_a], labels[b[into_a]]), 1)
        np.add.at(votes, (b[into_b], labels[a[into_b]]), 1)
        change = small & (votes.sum(axis=1) > 0)
        if not change.any():
            break
        labels[change] = votes[change].argmax(axis=1)
    return labels


def plan_pieces(positions, triangles, labels, a, b, base, together, join, least):
    """The pieces to paint: the base part whole, other parts by run, joined when close or together."""
    same = labels[a] == labels[b]
    graph = coo_matrix((np.ones(same.sum()), (a[same], b[same])), shape=(len(labels),) * 2)
    _, run = connected_components(graph, directed=False)
    labels = labels.copy()
    pieces = []
    for index in sorted(set(int(v) for v in np.unique(labels)) - {base}):
        runs = [np.nonzero(run == r)[0] for r in np.unique(run[labels == index])]
        boxes = []
        for faces in runs:
            corners = positions[np.unique(triangles[faces])]
            boxes.append((corners.min(axis=0), corners.max(axis=0)))
        group = list(range(len(runs)))

        def root(i):
            while group[i] != i:
                i = group[i]
            return i
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                gap = np.maximum(0.0, np.maximum(boxes[i][0] - boxes[j][1], boxes[j][0] - boxes[i][1]))
                if index in together or float(np.linalg.norm(gap)) <= join:
                    group[root(j)] = root(i)
        for leader in sorted({root(i) for i in range(len(runs))}):
            faces = np.sort(np.concatenate([runs[i] for i in range(len(runs)) if root(i) == leader]))
            if len(faces) < least:
                labels[faces] = base
                continue
            pieces.append({"part": index, "faces": faces})
    pieces.insert(0, {"part": base, "faces": np.nonzero(labels == base)[0]})
    return pieces, labels


# --- the pictures ----------------------------------------------------------------

def fill_from_surroundings(rgb, hole):
    """Fill `hole` with the colours round it, widening the reach until every pixel is filled."""
    out = rgb.astype(np.float32).copy()
    known = (~hole).astype(np.float32)
    remaining = hole.copy()
    for sigma in (2, 4, 8, 16, 32, 64, 128, 256):
        if not remaining.any():
            break
        weight = ndimage.gaussian_filter(known, sigma)
        reach = remaining & (weight > 0.02)
        if not reach.any():
            continue
        for channel in range(3):
            summed = ndimage.gaussian_filter(out[..., channel] * known, sigma)
            out[..., channel][reach] = summed[reach] / weight[reach]
        known[reach] = 1.0
        remaining &= ~reach
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def base_picture(rgba, own):
    """The base part's picture: the whole figure, with what other parts covered filled from round it."""
    silhouette = ndimage.binary_fill_holes(ndimage.binary_closing(own, structure=np.ones((3, 3)), iterations=14))
    hole = silhouette & ~own
    out = rgba.copy()
    out[..., :3] = np.where(hole[..., None], fill_from_surroundings(rgba[..., :3], hole), rgba[..., :3])
    out[..., 3] = np.where(own | hole, 255, 0).astype(np.uint8)
    return out, own | hole, int(hole.sum())


def part_regions(own):
    """The connected regions of a part's mask, each closed over its holes."""
    regions, found = ndimage.label(own)
    closed = np.zeros_like(regions)
    for region in range(1, found + 1):
        closed[ndimage.binary_fill_holes(regions == region) & (closed == 0)] = region
    return closed, found


def piece_picture(rgba, own, centre, together):
    """A piece's picture: its own region of the part (the nearest to where it projects, or all of
    them when painted together), with any region touching it; everything else transparent."""
    regions, found = part_regions(own)
    sizes = np.bincount(regions.ravel(), minlength=found + 1)
    viable = [r for r in range(1, found + 1) if sizes[r] >= LEAST_REGION_PIXELS]
    if not viable:
        return None, None, None
    if together:
        chosen = np.isin(regions, viable)
        distance = 0.0
    else:
        def far(region):
            rows, columns = np.nonzero(regions == region)
            return float(np.hypot(columns.mean() - centre[0], rows.mean() - centre[1]))
        best = min(viable, key=far)
        distance = far(best)
        chosen = regions == best
        rows, columns = np.nonzero(chosen)
        x0, y0, x1, y1 = columns.min(), rows.min(), columns.max() + 1, rows.max() + 1
        for region in range(1, found + 1):
            if region == best:
                continue
            rows2, columns2 = np.nonzero(regions == region)
            if columns2.min() < x1 and columns2.max() >= x0 and rows2.min() < y1 and rows2.max() >= y0:
                chosen |= regions == region
    out = rgba.copy()
    out[..., 3] = np.where(chosen, np.maximum(rgba[..., 3], 255 * (chosen & ~own)), 0).astype(np.uint8)
    return out, chosen, distance


def square_box(mask, margin):
    rows, columns = np.nonzero(mask)
    x0, y0, x1, y1 = columns.min(), rows.min(), columns.max() + 1, rows.max() + 1
    side = max(x1 - x0, y1 - y0) * (1.0 + margin)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return (int(round(cx - side / 2)), int(round(cy - side / 2)), int(round(cx + side / 2)), int(round(cy + side / 2)))


def picture_point(point, figure, low, high):
    """Where a picture-plane model point falls in the reference, axis by axis as crop_box fits it."""
    left, top, right, bottom = figure
    span = np.maximum(high - low, 1e-9)
    return (left + (point[0] - low[0]) * (right - left) / span[0],
            top + (high[1] - point[1]) * (bottom - top) / span[1])


# --- laying them back -------------------------------------------------------------

def hard_weights(sheet, faces, count, size):
    """1 on the texels that belong to these faces, 0 elsewhere: parts meet at an edge, unblended."""
    own = np.zeros(count, dtype=bool)
    own[faces] = True
    weights = np.zeros((size, size), dtype=np.float32)
    weights[sheet["rows"], sheet["columns"]] = own[sheet["faces"]]
    return weights


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    args = parse_arguments(argv)
    started = time.monotonic()
    for path, what in ((args.source, "model"), (args.parts, "part labelling"), (args.reference, "reference")):
        if not path.is_file():
            return failed("the {0} does not exist: {1}".format(what, path))
    if args.output.exists():
        return failed("refusing to overwrite {0}".format(args.output))
    if not 0 <= args.inpaint_reach <= 256:
        return failed("inpaint-reach runs from 0 to 256 texels. Got {0}".format(args.inpaint_reach))

    raw = args.source.read_bytes()
    document, binary = ps.read_glb(raw)
    positions, uvs, triangles = ps.mesh_from_glb(document, binary)
    materials = document.get("materials", [])
    if len(materials) != 1:
        return failed("the model carries {0} materials; parts are painted onto one painted atlas".format(
            len(materials)))
    labelling = np.load(args.parts, allow_pickle=False)
    if str(labelling["mesh_sha256"]) != mesh_sha256(positions, uvs, triangles):
        return failed("the part labelling was made for a different mesh; label this model's parts again")
    if str(labelling["reference_sha256"]) != ps.sha256(args.reference):
        return failed("the part labelling was made from a different reference picture")
    labels = labelling["faces"].astype(np.int64)
    vocab = json.loads(str(labelling["vocab"]))
    parts = vocab["parts"]
    names = [part["name"] for part in parts]
    base = next(i for i, part in enumerate(parts) if part.get("base"))
    together_names = args.together if args.together is not None else [p["name"] for p in parts if p.get("together")]
    unknown = sorted(set(together_names) - set(names))
    if unknown:
        return failed("--together names parts the vocabulary does not have: {0}".format(", ".join(unknown)))
    together = {names.index(name) for name in together_names}
    if not args.plan_only:
        if not args.launcher.is_file():
            return failed("the paint launcher is missing: {0}".format(args.launcher))
        if args.legacy_root is None or not (args.legacy_root / ".venv-hy3d21" / "Scripts" / "python.exe").is_file():
            return failed("the painter's environment is missing under {0}".format(args.legacy_root))

    a, b = face_neighbours(positions, triangles)
    labels = absorb_small_runs(labels, a, b, args.min_piece)
    pieces, labels = plan_pieces(positions, triangles, labels, a, b, base, together, args.join, args.min_piece)

    attempt = ps.next_attempt(args.output, "parts")
    attempt.mkdir(parents=True)
    try:
        cutout, cutout_record = ps.load_cutout(args, attempt)
    except RuntimeError as problem:
        return failed(str(problem))
    rgba = np.asarray(cutout.convert("RGBA")).copy()
    alpha = rgba[..., 3]
    picture_labels = labelling["reference"]
    if picture_labels.shape != alpha.shape:
        picture_labels = np.asarray(Image.fromarray(picture_labels).resize(cutout.size, Image.NEAREST))
    solid = alpha > 127
    figure = ps.figure_box(alpha)
    if figure is None:
        return failed("no figure was found in the reference")
    frame, _ = ps.match_orientation(positions, triangles, alpha)
    points = ps.project(positions, frame)
    low, high = points.min(axis=0), points.max(axis=0)
    density = ps.texel_density(positions, uvs, triangles, args.atlas)

    report = {
        "schema": SCHEMA,
        "source": str(args.source), "source_sha256": ps.sha256(args.source),
        "parts": str(args.parts), "parts_sha256": ps.sha256(args.parts),
        "reference": str(args.reference), "reference_sha256": ps.sha256(args.reference),
        "reference_cutout": cutout_record, "orientation": ps.describe(frame),
        "output": str(args.output),
        "settings": {"atlas": args.atlas, "views": args.views, "resolution": args.resolution,
                     "crop_margin": args.crop_margin, "min_piece": args.min_piece, "join_m": args.join,
                     "together": sorted(together_names), "surface_from": args.surface,
                     "inpaint_reach": args.inpaint_reach,
                     "painter_runs": "one per piece" if args.separate_runs else "one for every piece",
                     "upscale": "none" if args.no_upscale else "4x RealESRGAN"},
        "geometry_unchanged": True, "uvs_unchanged": True,
        "requires_fixed_view_review": True, "production_grade": False,
        "attempt": str(attempt), "pieces": [],
    }
    for number, piece in enumerate(pieces):
        name = "{0:02d}-{1}".format(number, names[piece["part"]])
        folder = attempt / name
        folder.mkdir()
        used = np.unique(triangles[piece["faces"]])
        own = (picture_labels == piece["part"]) & solid
        if piece["part"] == base:
            picture, region, filled = base_picture(rgba, own)
            note = {"filled_pixels": filled}
        else:
            centre = picture_point(points[used].mean(axis=0), figure, low, high)
            picture, region, distance = piece_picture(rgba, own, centre, piece["part"] in together)
            if picture is None:
                return failed("the reference shows no {0}: the labelling found none of it there".format(
                    names[piece["part"]]))
            note = {"region_distance_px": round(float(distance), 1)}
        box = square_box(region, args.crop_margin)
        crop = ps.cut_crop(Image.fromarray(picture, "RGBA"), box)
        crop.save(folder / "reference.png", format="PNG")
        kept = np.zeros(len(triangles), dtype=bool)
        kept[piece["faces"]] = True
        _, face_count = ps.write_obj(folder / "section.obj", positions, uvs, triangles, kept)
        span = positions[used].max(axis=0) - positions[used].min(axis=0)
        record = {"piece": name, "part": names[piece["part"]], "faces": int(face_count),
                  "span_m": [round(float(s), 3) for s in span],
                  "painted_mm_per_pixel": round(float(span.max()) * 1.1 / args.resolution * 1000.0, 2),
                  "bake_size": ps.bake_size_for(float(span.max()), density, 1.0),
                  "crop_box": list(box), "reference_pixels": int((np.asarray(crop)[..., 3] > 127).sum()),
                  "folder": str(folder), **note}
        piece["record"] = record
        report["pieces"].append(record)
        print("{0} piece {1}: {2} faces, {3:.2f} m".format(TAG, name, record["faces"], max(record["span_m"])),
              flush=True)

    def finish(painted, note):
        report["painted"] = painted
        report["note"] = note
        report["seconds"] = round(time.monotonic() - started, 1)
        if args.output.is_file():
            report["output_sha256"] = ps.sha256(args.output)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("{0} {1}".format(TAG, note))
        return 0

    if args.plan_only:
        return finish(False, "planned {0} pieces; nothing painted".format(len(pieces)))

    pbr = materials[0].get("pbrMetallicRoughness", {})
    albedo_index = ps.texture_image(document, pbr.get("baseColorTexture"))
    mr_index = ps.texture_image(document, pbr.get("metallicRoughnessTexture"))
    if albedo_index is None:
        return failed("the model's material has no base colour texture to paint over")
    size = max(Image.open(io.BytesIO(ps.image_bytes(document, binary, albedo_index))).size[0], args.atlas)
    base_albedo = ps.as_pixels(Image.open(io.BytesIO(ps.image_bytes(document, binary, albedo_index))),
                               size).astype(np.float32)
    base_mr = None
    if mr_index is not None and args.surface == "parts":
        base_mr = ps.as_pixels(Image.open(io.BytesIO(ps.image_bytes(document, binary, mr_index))),
                               size).astype(np.float32)
    sheet = ps.face_sheet(uvs, triangles, size)
    pending = []
    for piece in pieces:
        record = piece["record"]
        folder = Path(record["folder"])
        earlier = ps.reusable_paint(args.reuse_parts, folder, args, record["bake_size"]) \
            if args.reuse_parts else None
        if earlier is not None:
            shutil.copytree(earlier, folder / "paint")
            record["reused_from"] = str(earlier)
            record["launcher_exit_code"] = None
        else:
            pending.append(record)
    if pending and args.separate_runs:
        for record in pending:
            folder = Path(record["folder"])
            print("{0} painting {1}".format(TAG, record["piece"]), flush=True)
            begun = time.monotonic()
            try:
                _, _, record["launcher_exit_code"] = ps.paint_section(
                    args, folder / "section.obj", folder / "reference.png", folder / "paint", record["bake_size"])
            except (RuntimeError, subprocess.TimeoutExpired) as problem:
                return failed("piece {0} could not be painted, and no half-painted model is delivered: {1}".format(
                    record["piece"], problem))
            record["paint_seconds"] = round(time.monotonic() - begun, 1)
    elif pending:
        print("{0} painting {1} pieces in one painter run".format(TAG, len(pending)), flush=True)
        try:
            exit_code = ps.paint_batch(args, [(Path(r["folder"]) / "section.obj", Path(r["folder"]) / "reference.png",
                                               Path(r["folder"]) / "paint", r["bake_size"]) for r in pending],
                                       Path(report["attempt"]))
        except subprocess.TimeoutExpired as problem:
            return failed("the painter ran past {0:.0f} minutes and was stopped; no half-painted model is "
                          "delivered. The pieces it finished are kept: pass --reuse-parts {1} to paint only "
                          "the rest".format(problem.timeout / 60.0, report["attempt"]))
        for record in pending:
            record["launcher_exit_code"] = exit_code

    albedo_layers, mr_layers = [], []
    for piece in pieces:
        record = piece["record"]
        paint_dir = Path(record["folder"]) / "paint"
        try:
            glb, gate = ps.read_paint(paint_dir, "" if "reused_from" in record else
                                      ps.why_unpainted(paint_dir, Path(report["attempt"])))
        except RuntimeError as problem:
            return failed("piece {0} could not be painted, and no half-painted model is delivered: {1}{2}".format(
                record["piece"], problem, "" if args.separate_runs else
                ". The pieces that were painted are kept: pass --reuse-parts {0} to paint only the rest".format(
                    report["attempt"])))
        if "paint_seconds" not in record and "reused_from" not in record:
            # The painter's own time on the card for this piece.
            record["paint_seconds"] = gate.get("seconds_painting", gate.get("seconds"))
        record["gate"] = {key: gate.get(key) for key in ("faces_equal", "geometry_delta", "uv_delta", "atlas")}
        albedo_image, mr_image = ps.section_maps(paint_dir, glb)
        weights = hard_weights(sheet, piece["faces"], len(triangles), size)
        mask = weights > 0
        albedo_layers.append((ps.as_pixels(albedo_image, size), weights, mask))
        if base_mr is not None and mr_image is not None:
            mr_layers.append((ps.as_pixels(mr_image, size), weights, mask))

    replacements = {albedo_index: ps.png_bytes(ps.to_image(ps.composite(base_albedo, albedo_layers, 0.0)))}
    if base_mr is not None and len(mr_layers) == len(albedo_layers):
        replacements[mr_index] = ps.png_bytes(ps.to_image(ps.composite(base_mr, mr_layers, 0.0)))
    document, rebuilt = ps.swap_images(document, binary, replacements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(ps.write_glb(document, rebuilt))
    report["atlas_size"] = size
    report["reused_pieces"] = sum(1 for piece in pieces if "reused_from" in piece["record"])
    report["composite"] = {
        "colour": "each piece's own paint on its own faces' texels, unblended where parts meet",
        "metallic_roughness": "the part paints'" if mr_index in replacements else "the first paint's, unchanged",
        "padding": "refilled from the nearest painted texel",
    }
    return finish(True, "painted {0} pieces ({1}) and laid them on their own faces".format(
        len(pieces), ", ".join(piece["record"]["piece"] for piece in pieces)))


if __name__ == "__main__":
    sys.exit(main())
