"""Paint a large model again in sections, each at the scale a small one is painted at.

The painter looks at a whole model through twelve pictures of 768 pixels, whatever
its size. A 45 cm fitting fills those pictures and comes out with about 0.6 mm of
surface to a painted pixel. A 2.2 m skiff gets about 3 mm, and the 4096 sheet and
the upscaler after the painter can only stretch that: up close it reads as smeared
and grainy, and no atlas size puts back what the painter never saw.

So the model is cut into sections about half a metre across. Each section is
painted again on its own, with the reference cropped to the same part of the
picture, and laid back over the first paint on the same UVs. It is the head pass
(paint_head_detail.py) run across the whole model, and it reuses that pass's mesh
reading, OBJ transport and compositing.

Three things keep a model painted in pieces from looking like pieces:

- Every face is painted at section scale. None is left with the first paint
  beside a section's, because that boundary is a seam: the hero route's head
  pass leaves exactly one on a prop, crisp and the reference's colour above
  it, flat and the wrong colour below.
- Neighbouring sections overlap, and their weights fall across the overlap so
  that every face's weights sum to one. Each section is painted with some of
  its neighbours around it, so the painter sees what continues past its edge.
- The design comes from the first paint. A section's painter sees too little
  of the model to know what is iron, canvas or paint: on a 2.2 m skiff cut into
  45 sections, the red fins, iron straps and teal paint all came back as wood.
  So by default (`--keep-colour 0.03`) every colour coarser than a few
  centimetres is the first paint's, and the sections add only their fine light
  and dark: the grain, nail holes and wear, at a small prop's scale.
- `--keep-colour 0` takes the sections' own colour instead, with neighbours
  matched to each other where they overlap. That is for a single-material model
  whose first paint is wrong: on a 2.2 m mast the whole-model paint came out
  light putty where the close paint was the picture's dark iron. `--keep-tone`
  keeps the first paint's coarse colour and the sections' fine colour too.

The crop follows the section. The model's outline is matched against the
figure's outline in the picture to learn which way the model faces in it, and
each section's crop is where that section's own faces fall in the picture.

Nothing moves a vertex or a UV. A model too small to need this is passed through
byte for byte, and its receipt says so. `--plan-only` writes the sections, their
crops and the receipt without painting, so the plan can be looked at before any
GPU time is spent on it.

Every section is painted by one painter run that loads the models once
(`--separate-runs` starts one per section, as before), and each fills only the
texels near its own faces that no view saw (`--inpaint-reach`): on an 8192
sheet a section is a few percent of it, and filling the rest took most of each
section's time for texels nothing here reads.

Usage:
  python scripts/paint_sections.py -- <painted.glb> <output.glb> <report.json> \\
      --reference <image> --legacy-root <studio tree> \\
      [--section 0.6] [--overlap 0.25] [--keep-colour 0.03] [--min-length 1.2] \\
      [--max-sections 12] [--views 12] [--resolution 768] [--atlas 4096] [--plan-only]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import itertools
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(1, str(Path(__file__).resolve().parents[1] / "src"))
from compress_textures import read_glb, write_glb  # noqa: E402
from paint_head_detail import (  # noqa: E402
    image_bytes,
    mesh_from_glb,
    next_attempt,
    png_bytes,
    sha256,
    swap_images,
    tail,
    texture_image,
    write_obj,
)
from reference_asset_compiler.processes import kill_tree, run_bounded  # noqa: E402

TAG = "[SECTIONS]"
POWERSHELL = "powershell.exe"
SCHEMA = "reference-asset-compiler.section-detail-paint.v1"


def failed(reason: str) -> int:
    print("{0} FAILED: {1}".format(TAG, reason))
    return 1


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--reference", type=Path, required=True,
                        help="The picture the model was painted from; each section is cropped out of it")
    parser.add_argument("--legacy-root", type=Path,
                        help="The studio tree holding the painter's environment and weights")
    parser.add_argument("--section", type=float, default=0.6,
                        help="How far across a section may be, in metres. About what a small prop "
                             "measures, which is the scale the painter does best at.")
    parser.add_argument("--overlap", type=float, default=0.25,
                        help="How far neighbouring sections overlap, as a fraction of a section; "
                             "their paint is blended across it")
    parser.add_argument("--context", type=float, default=0.1,
                        help="How much more of the model each section's painter sees past the "
                             "overlap, as a fraction of a section; painted but not used")
    parser.add_argument("--keep-colour", type=float, default=0.01,
                        help="Keep the first paint's colour as painted, and add only the sections' "
                             "light and dark finer than this many metres. 0 takes the sections' "
                             "own colour, matched to each other.")
    parser.add_argument("--keep-tone", type=float, default=0.0,
                        help="With --keep-colour 0: tone coarser than this many metres comes from "
                             "the first paint and finer colour from the sections.")
    parser.add_argument("--no-harmonize", action="store_true",
                        help="Do not match neighbouring sections' colour where they overlap")
    parser.add_argument("--min-length", type=float, default=1.2,
                        help="A model shorter than this on every side is passed through unchanged")
    parser.add_argument("--max-sections", type=int, default=12,
                        help="The most sections a model is cut into; the sections grow to fit")
    parser.add_argument("--views", type=int, default=12)
    parser.add_argument("--resolution", type=int, default=768)
    parser.add_argument("--atlas", type=int, default=4096, choices=(2048, 4096, 8192))
    parser.add_argument("--bake-scale", type=float, default=1.0,
                        help="Each section's views are shrunk to about this many pixels a texel before "
                             "they are baked; 0 bakes them as upstream does")
    parser.add_argument("--crop-margin", type=float, default=0.12,
                        help="Extra around a section's place in the picture, as a fraction of it")
    parser.add_argument("--min-free-vram", type=int, default=0,
                        help="MiB the painter must find free before it starts; 0 leaves it to the launcher")
    parser.add_argument("--inpaint-reach", type=int, default=8,
                        help="Fill the texels no view saw only within this many texels of each section's "
                             "faces, the rest of its sheet from the nearest paint; 0 fills the whole sheet")
    parser.add_argument("--separate-runs", action="store_true",
                        help="Start the painter once for each section instead of once for them all")
    parser.add_argument("--plan-only", action="store_true",
                        help="Plan the sections and their crops and write the receipt; paint nothing")
    parser.add_argument("--cutout", type=Path,
                        help="The reference with its background already removed (RGBA). Without "
                             "it the painter's environment removes the background.")
    parser.add_argument("--launcher", type=Path,
                        default=Path(__file__).resolve().parent / "run_hy3d21_texture.ps1")
    parser.add_argument("--reuse-sections", type=Path,
                        help="An earlier attempt directory of this pass. A section it already painted "
                             "from the same mesh and the same crop is taken from it, not painted again.")
    return parser.parse_args(argv)


# --- which way the model faces in the picture ---------------------------------

# A single-view generator lays the picture's width along +X and its height along
# +Y, with the camera looking down -Z (paint_head_detail.HEAD_ENDS). That is the
# first orientation tried and the one kept unless another fits clearly better.
GENERATOR_FRAME = (0, 1, 1, 1)


def orientations():
    """Every axis-aligned way a model can face a picture.

    (h_axis, h_sign, v_axis, v_sign): the model axis that runs to the picture's
    right and the one that runs up it. Twenty-four in all, generator frame first.
    """
    frames = [GENERATOR_FRAME]
    for h_axis, v_axis in itertools.permutations(range(3), 2):
        for h_sign, v_sign in itertools.product((1, -1), (1, -1)):
            frame = (h_axis, h_sign, v_axis, v_sign)
            if frame != GENERATOR_FRAME:
                frames.append(frame)
    return frames


def describe(frame):
    """A frame in words: which model axis runs right in the picture, and which runs up."""
    h_axis, h_sign, v_axis, v_sign = frame
    return "{0}{1} right, {2}{3} up".format("+" if h_sign > 0 else "-", "XYZ"[h_axis],
                                           "+" if v_sign > 0 else "-", "XYZ"[v_axis])


def project(positions, frame):
    """Picture-plane coordinates of each vertex: x to the right, y up."""
    h_axis, h_sign, v_axis, v_sign = frame
    return np.stack([positions[:, h_axis] * h_sign, positions[:, v_axis] * v_sign], axis=1)


def fit_square(low, high, size):
    """Scale and offset that fit a box into a square, keeping its proportions."""
    span = np.maximum(high - low, 1e-9)
    scale = (size - 2) / float(span.max())
    offset = (size - span * scale) / 2.0
    return scale, offset


def mesh_silhouette(points, triangles, size=192):
    """The model's outline in the picture plane, fitted to a square."""
    low, high = points.min(axis=0), points.max(axis=0)
    scale, offset = fit_square(low, high, size)
    if len(triangles) > 20000:
        triangles = triangles[::math.ceil(len(triangles) / 20000)]
    pixels = (points - low) * scale + offset
    pixels[:, 1] = size - pixels[:, 1]          # picture rows run down
    sheet = Image.new("1", (size, size), 0)
    draw = ImageDraw.Draw(sheet)
    for face in pixels[triangles]:
        draw.polygon([tuple(point) for point in face], fill=1)
    return np.asarray(sheet, dtype=bool)


def figure_box(alpha):
    """(left, top, right, bottom) of the figure in the picture, or None."""
    rows = np.where(alpha.max(axis=1) > 16)[0]
    columns = np.where(alpha.max(axis=0) > 16)[0]
    if rows.size == 0 or columns.size == 0:
        return None
    return int(columns[0]), int(rows[0]), int(columns[-1]) + 1, int(rows[-1]) + 1


def figure_silhouette(alpha, size=192):
    """The figure's outline, fitted to a square the same way the model's is."""
    box = figure_box(alpha)
    if box is None:
        return None
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    scale = (size - 2) / float(max(width, height))
    fitted = Image.fromarray((np.asarray(alpha)[top:bottom, left:right] > 16).astype(np.uint8) * 255)
    fitted = fitted.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.BILINEAR)
    sheet = Image.new("L", (size, size), 0)
    sheet.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return np.asarray(sheet) > 127


def match_orientation(positions, triangles, alpha, margin=0.06, size=192):
    """The frame whose outline best matches the figure's, and every frame's score.

    Scored by intersection over union of the two outlines, each fitted to a square
    keeping its proportions. The generator's own frame is kept unless another
    beats it by `margin`: a symmetric model matches its mirror image as well, and
    there the generator's frame is the one that is right.
    """
    figure = figure_silhouette(alpha, size)
    if figure is None:
        raise ValueError("no figure was found in the reference")
    scores = {}
    for frame in orientations():
        outline = mesh_silhouette(project(positions, frame), triangles, size)
        union = np.logical_or(outline, figure).sum()
        scores[frame] = float(np.logical_and(outline, figure).sum() / max(union, 1))
    best = max(scores, key=scores.get)
    chosen = GENERATOR_FRAME if scores[GENERATOR_FRAME] >= scores[best] - margin else best
    return chosen, scores


# --- cutting the model into sections ------------------------------------------

def section_counts(extent, section, max_sections):
    """How many sections along each axis, and the section size, for a grid of at most `max_sections` cells."""
    size = float(section)
    while True:
        counts = [max(1, math.ceil(float(e) / size - 1e-3)) for e in extent]
        if int(np.prod(counts)) <= max_sections:
            return counts, size
        size *= 1.1


def ramp(x, start, end, first, last, band):
    """1 inside [start, end], falling to 0 across a band centred on each inner edge."""
    weight = np.ones_like(x, dtype=np.float64)
    if not first:
        weight *= np.clip((x - (start - band / 2.0)) / band, 0.0, 1.0)
    if not last:
        weight *= np.clip(((end + band / 2.0) - x) / band, 0.0, 1.0)
    return weight


def plan_sections(positions, triangles, section, overlap, context, max_sections, min_faces=200):
    """Cut the model into sections no wider than `section`, as few as the cap needs.

    The cap counts sections that are painted: a grid cell the model does not
    reach (the empty corners of a boat's bounding box) costs nothing. The grid
    starts at `section` and its cells grow a tenth at a time until the painted
    ones fit `max_sections`. See plan_grid for how a grid is cut and weighed.
    """
    extent = (positions.max(axis=0) - positions.min(axis=0)).astype(np.float64)
    size = float(section)
    while True:
        counts = [max(1, math.ceil(float(e) / size - 1e-3)) for e in extent]
        plan = plan_grid(positions, triangles, counts, size, overlap, context, min_faces)
        if len(plan["cells"]) <= max_sections:
            return plan
        size *= 1.1


def plan_grid(positions, triangles, counts, size, overlap, context, min_faces=200):
    """The sections of a model, each with the faces it paints and their weights.

    The model's bounding box is cut into `counts` equal cells along each axis.
    A face belongs to a cell by its centroid.
    Each cell's weight is 1 in its core and falls to 0 across a band of
    `overlap` sections centred on each inner edge, so every face's weights over
    all cells sum to exactly one. A cell paints the faces it weighs, plus
    `context` of a section more on each side so its edge is not its painter's.
    A cell weighing fewer than `min_faces` faces -- a corner of the box the
    model barely reaches -- is not painted on its own: its faces go to the
    nearest cell that is, so every face is still painted at section scale and
    none is left with the first paint beside a section's (that boundary is the
    seam the head pass leaves on a prop).
    """
    centroids = positions[triangles].mean(axis=1).astype(np.float64)
    corners = positions.astype(np.float64)
    low, high = positions.min(axis=0).astype(np.float64), positions.max(axis=0).astype(np.float64)
    extent = high - low
    cells, skipped = [], []
    for index in itertools.product(*(range(count) for count in counts)):
        weight = np.ones(len(triangles), dtype=np.float64)
        corner_weight = np.ones(len(corners), dtype=np.float64)
        painted = np.ones(len(triangles), dtype=bool)
        core = []
        for axis, (k, count) in enumerate(zip(index, counts)):
            step = extent[axis] / count
            start, end = low[axis] + k * step, low[axis] + (k + 1) * step
            band = overlap * step
            first, last = k == 0, k == count - 1
            weight *= ramp(centroids[:, axis], start, end, first, last, band)
            corner_weight *= ramp(corners[:, axis], start, end, first, last, band)
            reach = band / 2.0 + context * step
            near = np.ones(len(triangles), dtype=bool)
            if not first:
                near &= centroids[:, axis] >= start - reach
            if not last:
                near &= centroids[:, axis] <= end + reach
            painted &= near
            core.append([round(float(start), 4), round(float(end), 4)])
        if (weight > 0).sum() < min_faces:
            skipped.append({"index": list(index), "faces_weighted": int((weight > 0).sum())})
            continue
        cells.append({"index": list(index), "core_m": core, "faces": painted,
                      "weights": weight.astype(np.float32),
                      "vertex_weights": corner_weight.astype(np.float32)})
    if cells and skipped:
        # What the skipped cells weighed goes to the nearest painted cell.
        deficit = 1.0 - sum(cell["weights"].astype(np.float64) for cell in cells)
        orphans = np.where(deficit > 1e-6)[0]
        if orphans.size:
            distance = np.empty((len(cells), orphans.size))
            for number, cell in enumerate(cells):
                core = np.array(cell["core_m"], dtype=np.float64)
                outside = np.maximum(core[:, 0] - centroids[orphans], centroids[orphans] - core[:, 1])
                distance[number] = (np.maximum(outside, 0.0) ** 2).sum(axis=1)
            nearest = distance.argmin(axis=0)
            for number, cell in enumerate(cells):
                taken = orphans[nearest == number]
                cell["weights"][taken] += deficit[taken].astype(np.float32)
                cell["faces"][taken] = True
        # The same for each corner, so the smooth weights also sum to one.
        deficit = 1.0 - sum(cell["vertex_weights"].astype(np.float64) for cell in cells)
        orphans = np.where(deficit > 1e-6)[0]
        if orphans.size:
            distance = np.empty((len(cells), orphans.size))
            for number, cell in enumerate(cells):
                core = np.array(cell["core_m"], dtype=np.float64)
                outside = np.maximum(core[:, 0] - corners[orphans], corners[orphans] - core[:, 1])
                distance[number] = (np.maximum(outside, 0.0) ** 2).sum(axis=1)
            nearest = distance.argmin(axis=0)
            for number, cell in enumerate(cells):
                taken = orphans[nearest == number]
                cell["vertex_weights"][taken] += deficit[taken].astype(np.float32)
    return {"counts": counts, "section_m": size, "extent_m": extent, "cells": cells, "skipped": skipped}


def crop_box(points, figure, model_low, model_high, margin):
    """Where a section's faces fall in the picture, as a square crop box.

    `points` are the section's vertices in the picture plane, `model_low/high`
    the whole model's picture-plane bounds, and `figure` the figure's box in the
    picture, both fitted the same way. Returns (left, top, right, bottom).
    """
    left, top, right, bottom = figure
    width, height = right - left, bottom - top
    span = np.maximum(model_high - model_low, 1e-9)
    # Each axis on its own: the model's extremes land on the figure's. A
    # picture taken at an angle is not the model's flat outline, and fitting
    # both axes with one scale put a mast's base plate below its bottom crop.
    xs = left + (points[:, 0] - model_low[0]) * (width / span[0])
    ys = top + (model_high[1] - points[:, 1]) * (height / span[1])
    centre = ((xs.min() + xs.max()) / 2.0, (ys.min() + ys.max()) / 2.0)
    # Never smaller than a fifth of the figure: a section at a fin's tip
    # otherwise gets a crop of a few dozen pixels with nothing in it, and the
    # painter is handed an empty picture to paint from.
    side = max(xs.max() - xs.min(), ys.max() - ys.min(), 0.2 * max(width, height), 32.0) * (1.0 + margin)
    box = [int(round(centre[0] - side / 2.0)), int(round(centre[1] - side / 2.0))]
    return box[0], box[1], box[0] + int(round(side)), box[1] + int(round(side))


def cut_crop(cutout: Image.Image, box) -> Image.Image:
    """The crop with its alpha, padded rather than shrunk where it runs off the picture."""
    left, top, right, bottom = box
    canvas = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    canvas.paste(cutout, (-left, -top))
    return canvas


# --- laying the sections over the first paint ---------------------------------

def texel_density(positions, uvs, triangles, size):
    """Texture pixels per metre across the surface: the area-weighted median."""
    p = positions[triangles].astype(np.float64)
    t = uvs[triangles].astype(np.float64) * size
    world = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    texels = 0.5 * np.abs((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
                          - (t[:, 2, 0] - t[:, 0, 0]) * (t[:, 1, 1] - t[:, 0, 1]))
    keep = world > 1e-12
    if not keep.any():
        return 0.0
    density = np.sqrt(texels[keep] / world[keep])
    order = np.argsort(density)
    cumulative = np.cumsum(world[keep][order]) / world[keep].sum()
    return float(density[order][np.searchsorted(cumulative, 0.5)])


def face_sheet(uvs, triangles, size, grow_texels=2):
    """Which face each texel belongs to, and where in it: a face index and barycentrics.

    Drawn once and shared by every section. Texels just outside an island take
    their nearest face, as `grow` does for a mask, so a bilinear sample at an
    island's edge reads a weight.
    """
    sheet = Image.new("I", (size, size), 0)
    draw = ImageDraw.Draw(sheet)
    for face in range(len(triangles)):
        points = [(float(u) * size, float(v) * size) for u, v in uvs[triangles[face]]]
        draw.polygon(points, fill=face + 1, outline=face + 1)
    ids = np.asarray(sheet, dtype=np.int64)
    for _ in range(int(grow_texels)):
        empty = ids == 0
        if not empty.any():
            break
        for axis in (0, 1):
            for shift in (1, -1):
                ids = np.where(empty & (ids == 0), np.roll(ids, shift, axis=axis), ids)
    rows, columns = np.nonzero(ids)
    faces = ids[rows, columns] - 1
    corner = uvs[triangles[faces]].astype(np.float64) * size          # (n, 3, 2)
    point = np.stack([columns + 0.5, rows + 0.5], axis=1)
    v0, v1 = corner[:, 1] - corner[:, 0], corner[:, 2] - corner[:, 0]
    v2 = point - corner[:, 0]
    d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
    d20, d21 = (v2 * v0).sum(1), (v2 * v1).sum(1)
    denominator = d00 * d11 - d01 * d01
    safe = np.abs(denominator) > 1e-12
    b1 = np.where(safe, (d11 * d20 - d01 * d21) / np.where(safe, denominator, 1.0), 1.0 / 3.0)
    b2 = np.where(safe, (d00 * d21 - d01 * d20) / np.where(safe, denominator, 1.0), 1.0 / 3.0)
    bary = np.clip(np.stack([1.0 - b1 - b2, b1, b2], axis=1), 0.0, 1.0)
    bary /= np.maximum(bary.sum(axis=1, keepdims=True), 1e-9)
    return {"size": size, "rows": rows, "columns": columns, "faces": faces, "bary": bary.astype(np.float32)}


def smooth_weights(sheet, triangles, vertex_weights, painted_faces):
    """A section's weight across the sheet, varying smoothly across each face.

    Weights read per face jump at every edge, and Pixal's simplified meshes have
    faces several centimetres across: where two sections met, the skiff showed
    hard-edged triangles of one section's paint beside the other's. Interpolated
    from the corners, the two cross-fade instead. A face the section did not
    paint weighs nothing, whatever its corners say.
    """
    size = sheet["size"]
    # Only the texels of the section's own faces: on an 8192 sheet the rest are
    # most of it, and their weight is nothing whatever their corners say.
    painted = np.asarray(painted_faces)[sheet["faces"]]
    if painted.dtype != bool:
        painted = painted != 0
    faces = sheet["faces"][painted]
    corners = triangles[faces]
    values = (vertex_weights[corners] * sheet["bary"][painted]).sum(axis=1)
    rows, columns = sheet["rows"][painted], sheet["columns"][painted]
    weights = np.zeros((size, size), dtype=np.float32)
    weights[rows, columns] = values
    mask = np.zeros((size, size), dtype=bool)
    mask[rows, columns] = True
    return weights, mask


def bake_size_for(span, density, scale):
    """How many pixels a section's views are baked from: about `scale` a texel.

    The painter frames a section with a tenth to spare, as `painted_mm_per_pixel`
    assumes. 0 when `scale` is 0, which leaves the painter's own sizes.
    """
    if scale <= 0 or density <= 0:
        return 0
    return int(min(4096, max(256, round(span * 1.1 * density * scale))))


def masked_blur(image, mask, sigma):
    """A blur that only averages texels the mask holds, so empty atlas does not darken it.

    Computed on a sheet shrunk by about a third of the blur's width, which still
    holds it: the tone scale is tens of texels wide, and a full-size Gaussian on
    a 4096 sheet for each of forty-five sections took most of an hour.
    """
    from scipy.ndimage import gaussian_filter, zoom  # noqa: PLC0415 -- dependencies of the package

    factor = max(1, int(sigma // 3))
    height, width = mask.shape
    rows, columns = max(1, height // factor), max(1, width // factor)
    held = mask[: rows * factor, : columns * factor].astype(np.float32)
    weight = held.reshape(rows, factor, columns, factor).mean(axis=(1, 3))
    summed = (image[: rows * factor, : columns * factor] * held[..., None]).reshape(
        rows, factor, columns, factor, image.shape[2]).mean(axis=(1, 3))
    small_sigma = sigma / factor
    weight = gaussian_filter(weight, small_sigma)
    blurred = np.stack([gaussian_filter(summed[..., c], small_sigma) for c in range(image.shape[2])], axis=2)
    low = blurred / np.maximum(weight, 1e-6)[..., None]
    if factor == 1 and low.shape[:2] == (height, width):
        return low.astype(np.float32)
    up = zoom(low, (height / rows, width / columns, 1), order=1)
    out = np.empty((height, width, image.shape[2]), dtype=np.float32)
    out[: up.shape[0], : up.shape[1]] = up[:height, :width]
    if up.shape[0] < height:
        out[up.shape[0]:] = out[up.shape[0] - 1]
    if up.shape[1] < width:
        out[:, up.shape[1]:] = out[:, up.shape[1] - 1: up.shape[1]]
    return out


def _block_mean(array, factor, rows, columns):
    """The mean of every factor x factor block of the first rows*factor x columns*factor texels, as float32.

    Summed along one axis and then the other, which reads the sheet in order:
    a mean over both block axes at once strides across it and took seconds.
    """
    array = array[: rows * factor, : columns * factor]
    channels = array.shape[2]
    down = np.ascontiguousarray(array).reshape(rows, factor, columns * factor * channels).sum(axis=1, dtype=np.float32)
    down = down.reshape(rows, columns, factor, channels).sum(axis=2, dtype=np.float32)
    return down / np.float32(factor * factor)


def _shrunk_blur(image, mask, sigma, factor):
    """masked_blur's shrunk sheet, blurred, before it is grown back: (rows, columns, channels) float32."""
    from scipy.ndimage import gaussian_filter  # noqa: PLC0415

    height, width = mask.shape
    rows, columns = max(1, height // factor), max(1, width // factor)
    weight = _block_mean(mask[..., None], factor, rows, columns)[..., 0]
    held = image * mask[..., None].astype(image.dtype if image.dtype.kind == "f" else np.uint8)
    summed = _block_mean(held, factor, rows, columns)
    small_sigma = sigma / factor
    weight = gaussian_filter(weight, small_sigma)
    blurred = np.stack([gaussian_filter(summed[..., c], small_sigma) for c in range(image.shape[2])], axis=2)
    return blurred / np.maximum(weight, 1e-6)[..., None]


def masked_blur_at(image, mask, sigma, index, tile=256):
    """masked_blur(image, mask, sigma) at the flat texel indices `index` only: (n, channels) float32.

    A section uses a few percent of an 8192 sheet, and blurring all of it for
    every section took most of the composite: 25-30 s a section a map. Where
    the blur is taken at full size, it is taken here tile by tile, only round
    the tiles that hold a texel asked for, each with a border as wide as the
    Gaussian reaches, so every texel asked for reads exactly the texels the
    whole-sheet blur would. Where it is taken on a shrunk sheet, that sheet is
    small and is blurred whole, and only the texels asked for are read back
    from it, by the same linear interpolation that grows it to full size; its
    block means are summed in another order, so they agree to float rounding.
    `image` may be uint8 or float.
    """
    from scipy.ndimage import gaussian_filter  # noqa: PLC0415

    height, width = mask.shape
    channels = image.shape[2]
    index = np.asarray(index, dtype=np.int64)
    rows, columns = np.divmod(index, width)
    factor = max(1, int(sigma // 3))
    out = np.empty((len(index), channels), dtype=np.float32)
    if len(index) == 0:
        return out
    if factor > 1:
        low = _shrunk_blur(image, mask, sigma, factor).astype(np.float32)
        low_rows, low_columns = low.shape[:2]
        # scipy.ndimage.zoom(order=1) to (height, width): output texel o reads
        # the shrunk sheet at o * (in - 1) / (out - 1), linearly between its two
        # neighbours on each axis. Rows past what it grows are the last row's.
        grown_rows = int(round(low_rows * (height / low_rows)))
        grown_columns = int(round(low_columns * (width / low_columns)))
        y = np.minimum(rows, grown_rows - 1).astype(np.float64) * (
            (low_rows - 1) / (grown_rows - 1) if grown_rows > 1 else 0.0)
        x = np.minimum(columns, grown_columns - 1).astype(np.float64) * (
            (low_columns - 1) / (grown_columns - 1) if grown_columns > 1 else 0.0)
        y0 = np.floor(y).astype(np.int64)
        x0 = np.floor(x).astype(np.int64)
        fy, fx = (y - y0)[:, None], (x - x0)[:, None]
        y1, x1 = np.minimum(y0 + 1, low_rows - 1), np.minimum(x0 + 1, low_columns - 1)
        low64 = low.astype(np.float64)
        out[:] = ((1 - fy) * (1 - fx) * low64[y0, x0] + (1 - fy) * fx * low64[y0, x1]
                  + fy * (1 - fx) * low64[y1, x0] + fy * fx * low64[y1, x1])
        return out
    reach = int(4.0 * sigma + 0.5)          # gaussian_filter's own reach, truncate=4
    tiles = (rows // tile) * ((width + tile - 1) // tile) + columns // tile
    order = np.argsort(tiles, kind="stable")
    starts = np.flatnonzero(np.r_[True, np.diff(tiles[order]) != 0])
    ends = np.r_[starts[1:], len(order)]
    for start, end in zip(starts, ends):
        members = order[start:end]
        top, left = (rows[members[0]] // tile) * tile, (columns[members[0]] // tile) * tile
        r0, r1 = max(0, top - reach), min(height, top + tile + reach)
        c0, c1 = max(0, left - reach), min(width, left + tile + reach)
        held = mask[r0:r1, c0:c1].astype(np.float32)
        weight = gaussian_filter(held, sigma)
        window = image[r0:r1, c0:c1] * held[..., None]
        for channel in range(channels):
            blurred = gaussian_filter(window[..., channel], sigma)
            out[members, channel] = (blurred / np.maximum(weight, 1e-6))[rows[members] - r0, columns[members] - c0]
    return out


def harmonize(sections, limits=(0.7, 1.4), least=64):
    """Per-section, per-channel gains that make neighbours agree where both painted.

    For every pair of sections that painted the same texels, the means of the
    two paints there should match once each is scaled by its gain. Solved in
    log space by least squares over every such pair, weighted by how much they
    share, with the gains' geometric mean held at one so the model keeps the
    sections' own overall colour. Returns (gains (n, 3), pairs used).
    """
    count = len(sections)
    rows, targets, weights, pairs = [], [], [], []
    for i in range(count):
        for j in range(i + 1, count):
            shared = sections[i][2] & sections[j][2]
            texels = int(shared.sum())
            if texels < least:
                continue
            mean_i = sections[i][0][shared].astype(np.float64).mean(axis=0) + 1.0
            mean_j = sections[j][0][shared].astype(np.float64).mean(axis=0) + 1.0
            row = np.zeros(count)
            row[i], row[j] = 1.0, -1.0
            rows.append(row)
            targets.append(np.log(mean_j) - np.log(mean_i))
            weights.append(np.sqrt(texels))
            pairs.append({"sections": [i, j], "shared_texels": texels,
                          "difference": [round(float(v), 2) for v in (mean_j - mean_i)]})
    if not rows:
        return np.ones((count, 3)), pairs
    weights = np.array(weights)
    anchor = np.ones(count) * weights.max() * 10.0
    matrix = np.vstack([np.array(rows) * weights[:, None], anchor])
    gains = np.ones((count, 3))
    for channel in range(3):
        target = np.concatenate([np.array(targets)[:, channel] * weights, [0.0]])
        solution = np.linalg.lstsq(matrix, target, rcond=None)[0]
        gains[:, channel] = np.clip(np.exp(solution), *limits)
    return gains, pairs


def repad(image, covered):
    """Fill the atlas outside every island from its nearest painted texel.

    The padding round an island is what a mip level or a bilinear sample at its
    edge reads. Left as the first paint's, a section painted a different colour
    would show its islands' outlines from a distance.
    """
    from scipy.ndimage import distance_transform_edt  # noqa: PLC0415

    if covered.all() or not covered.any():
        return image
    _, (rows, columns) = distance_transform_edt(~covered, return_indices=True)
    return image[rows, columns]


LUMINANCE = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def composite(base, sections, sigma, gains=None, mode="colour"):
    """Every section laid over the model, on the first paint's islands.

    `base` is (H, W, C) float32; `sections` is a list of (paint, weights, mask)
    with paint at the base's size (uint8 or float), weights the section's face
    weights painted into UV space, and mask (bool) where the section painted at
    all. `gains` scales each section's paint first. With `sigma` texels of blur,
    tone coarser than the blur comes from the base and only finer detail from
    each section: in `mode` "colour", the section's fine colour; in "light",
    only its fine light and dark, multiplying the base as it was painted, so a
    section that painted an iron strap as wood leaves the strap iron.

    In "light" the base is not blurred. The blur is taken on the flat sheet,
    and near a UV island's edge it reaches into whatever unrelated island sits
    beside it: blurring the base's colour 3 cm smeared the skiff's teal chips,
    greyed its iron, and left hard wedges of the wrong colour on its many small
    stern islands. A ratio of the section's own light to its blurred light can
    only change brightness, so what the same reach picks up near an edge moves
    brightness a little and never colour. With 0, the
    sections' paint is used as it is. Texels no
    section reached keep the base, and the atlas padding is refilled from the
    nearest laid texel so mip levels read what the islands hold.
    """
    # Every sum is taken only where a section weighs anything, and every blur
    # only there (masked_blur_at): the same numbers as the whole-sheet arithmetic
    # this replaced, a few percent of the work on a large sheet.
    height, width, channels = base.shape
    base_flat = base.reshape(-1, channels)
    total = np.zeros(height * width, dtype=np.float32)
    laid = np.zeros((height * width, channels), dtype=np.float32)
    base_tone = None
    if sigma > 0 and mode != "light":
        everywhere = np.zeros(base.shape[:2], dtype=bool)
        weighed = np.zeros(height * width, dtype=bool)
        for _, weights, mask in sections:
            everywhere |= mask
            weighed |= np.asarray(weights).reshape(-1) != 0
        tone_at = np.flatnonzero(weighed)
        base_tone = np.zeros((height * width, channels), dtype=np.float32)
        base_tone[tone_at] = masked_blur_at(base, everywhere, sigma, tone_at)
    for number, (paint, weights, mask) in enumerate(sections):
        at = np.flatnonzero(np.asarray(weights).reshape(-1) != 0)
        if len(at) == 0:
            continue
        if gains is not None:
            paint = paint.astype(np.float32) * np.asarray(gains[number], dtype=np.float32)
        here = np.asarray(paint).reshape(-1, channels)[at].astype(np.float32)
        if sigma > 0 and mode == "light":
            own = masked_blur_at(paint, mask, sigma, at)
            ratio = np.clip((here @ LUMINANCE + 4.0) / (own @ LUMINANCE + 4.0), 0.55, 1.6)
            here = base_flat[at] * ratio[:, None]
        elif sigma > 0:
            own = masked_blur_at(paint, mask, sigma, at)
            here = base_tone[at] + (here - own)
        weight = np.asarray(weights).reshape(-1)[at].astype(np.float32)
        laid[at] += here * weight[:, None]
        total[at] += weight
    # Where weights sum away from one -- grown masks overlapping at an island's
    # edge, or a face one neighbour did not paint -- the sections share.
    covered = total > 0
    out = base.copy() if base.dtype == np.float32 else base.astype(np.float32)
    out_flat = out.reshape(-1, channels)
    out_flat[covered] = laid[covered] / total[covered][:, None]
    return repad(out, covered.reshape(height, width))


def as_pixels(image: Image.Image, size):
    """An RGB sheet at the base's size, as bytes; converted to floats only when laid."""
    if image.size != (size, size):
        image = image.resize((size, size), Image.LANCZOS)
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def to_image(pixels) -> Image.Image:
    return Image.fromarray(np.clip(pixels + 0.5, 0, 255).astype(np.uint8), "RGB")


# --- the run -------------------------------------------------------------------

def load_cutout(args, attempt):
    """The reference with its background removed, and where that came from."""
    if args.cutout:
        cutout = Image.open(args.cutout)
        cutout.load()
        return cutout.convert("RGBA"), {"cutout": str(args.cutout), "cutout_sha256": sha256(args.cutout)}
    image = Image.open(args.reference)
    image.load()
    if image.mode == "RGBA" and (np.asarray(image.getchannel("A")) < 250).mean() > 0.001:
        return image, {"cutout": "the reference's own alpha"}
    if args.legacy_root is None:
        raise RuntimeError("the reference has no alpha, and without --legacy-root there is nothing "
                           "to remove its background with; pass --cutout")
    venv = args.legacy_root / ".venv-hy3d21" / "Scripts" / "python.exe"
    cutout_png = attempt / "reference-cutout.png"
    cutout_json = attempt / "reference-cutout.json"
    cropper = Path(__file__).resolve().parent / "crop_reference_region.py"
    done = run_bounded([str(venv), str(cropper), str(args.reference), str(cutout_png), str(cutout_json),
                           "--cutout-only"], capture_output=True, text=True, errors="replace",
                          stdin=subprocess.DEVNULL, timeout=600)
    if done.returncode != 0 or not cutout_png.is_file():
        raise RuntimeError("the reference's background could not be removed: {0}".format(
            " ".join(tail(done.stdout + "\n" + done.stderr, 4))))
    cutout = Image.open(cutout_png)
    cutout.load()
    return cutout.convert("RGBA"), json.loads(cutout_json.read_text(encoding="utf-8"))


def paint_section(args, mesh_obj, crop_png, paint_dir, bake_size=0):
    """One section through the painter; returns its GLB and the painter's gate."""
    command = [
        POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(args.launcher),
        "-Mesh", str(mesh_obj), "-Reference", str(crop_png),
        "-OutputObj", str(paint_dir / "section.obj"), "-LegacyRoot", str(args.legacy_root),
        "-Views", str(args.views), "-Resolution", str(args.resolution),
        "-RunnerKind", "studio", "-Atlas", str(args.atlas),
    ]
    if args.min_free_vram > 0:
        command += ["-MinimumFreeVramMiB", str(args.min_free_vram)]
    if bake_size > 0:
        command += ["-BakeSize", str(int(bake_size))]
    if getattr(args, "inpaint_reach", 0) > 0:
        command += ["-InpaintReach", str(int(args.inpaint_reach))]
    painted = run_bounded(command, capture_output=True, text=True, errors="replace",
                             stdin=subprocess.DEVNULL, timeout=3000,
                             env={key: value for key, value in os.environ.items()
                                  if key.upper() != "PSMODULEPATH"})
    glb, gate = read_paint(paint_dir, " ".join(tail(painted.stderr, 6)) or " ".join(tail(painted.stdout, 6)))
    return glb, gate, painted.returncode


def paint_batch(args, jobs, attempt, minutes_each=10.0):
    """Every section through one painter run, its models loaded once; returns the launcher's exit code.

    `jobs` is a list of (mesh_obj, crop_png, paint_dir, bake_size). The painter
    writes each section's maps and gate into its paint folder as it finishes it,
    so the progress printed here is what is on disk. Its output goes to
    painter.log in the attempt. A section that failed has no gate and is found
    so by read_paint; the others are kept for --reuse-sections.
    """
    jobs_file = attempt / "paint-jobs.json"
    jobs_file.write_text(json.dumps([
        {"mesh": str(mesh_obj), "reference": str(crop_png), "output_obj": str(paint_dir / "section.obj"),
         "bake_size": int(bake_size)} for mesh_obj, crop_png, paint_dir, bake_size in jobs], indent=2) + "\n",
        encoding="utf-8")
    command = [
        POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(args.launcher), "-Jobs", str(jobs_file), "-LegacyRoot", str(args.legacy_root),
        "-Views", str(args.views), "-Resolution", str(args.resolution),
        "-RunnerKind", "studio", "-Atlas", str(args.atlas),
    ]
    if args.min_free_vram > 0:
        command += ["-MinimumFreeVramMiB", str(args.min_free_vram)]
    if args.inpaint_reach > 0:
        command += ["-InpaintReach", str(int(args.inpaint_reach))]
    limit = 600.0 + minutes_each * 60.0 * len(jobs)
    started = time.monotonic()
    reported = set()
    with open(attempt / "painter.log", "w", encoding="utf-8", errors="replace") as log:
        with subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                              env={key: value for key, value in os.environ.items()
                                   if key.upper() != "PSMODULEPATH"}) as process:
            try:
                while True:
                    try:
                        process.wait(timeout=5)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    for number, (_, _, paint_dir, _) in enumerate(jobs):
                        if number not in reported and (paint_dir / "section.validation.json").is_file():
                            reported.add(number)
                            print("{0} painted {1} of {2} ({3:.0f} s so far)".format(
                                TAG, len(reported), len(jobs), time.monotonic() - started), flush=True)
                    if time.monotonic() - started > limit:
                        kill_tree(process.pid)
                        process.kill()
                        process.wait()
                        raise subprocess.TimeoutExpired(command, limit)
            except BaseException:
                if process.poll() is None:
                    kill_tree(process.pid)
                    process.kill()
                raise
    return process.returncode


def why_unpainted(paint_dir, attempt):
    """What the painter recorded about a section it did not finish, or the end of its log."""
    failure = paint_dir / "section.failure.json"
    if failure.is_file():
        try:
            return json.loads(failure.read_text(encoding="utf-8-sig")).get("error", "")
        except ValueError:
            pass
    log = attempt / "painter.log"
    if log.is_file():
        return " ".join(tail(log.read_text(encoding="utf-8", errors="replace"), 6))
    return ""


def read_paint(paint_dir, why_missing=""):
    """A painted section and the painter's own gate, refused if it moved anything."""
    glb = paint_dir / "section.glb"
    validation = paint_dir / "section.validation.json"
    if not glb.is_file() or not validation.is_file():
        raise RuntimeError("the painter produced nothing: {0}".format(why_missing))
    gate = json.loads(validation.read_text(encoding="utf-8-sig"))
    if not gate.get("faces_equal") or gate.get("geometry_delta", 1) > 1e-6 or gate.get("uv_delta", 1) > 1e-6:
        raise RuntimeError("the painter moved the section: {0}".format(json.dumps(gate, sort_keys=True)))
    return glb, gate


def reusable_paint(previous, folder, args, bake_size=0):
    """The paint an earlier attempt made of exactly this section, or None.

    A long pass can be stopped part way: the skiff's 32 sections outlasted a
    one-hour stage limit at section 20, and the twenty were good. This finds a
    finished section by what the painter itself recorded it was given: the hash
    of the mesh and of the crop, and the views, resolution and atlas. A section
    planned differently, cut from a different crop or painted at other settings
    has other hashes or other numbers and is painted again. The painter's exit
    code is not consulted; its known teardown fault comes after it has written
    everything, which is why the gate, not the exit code, decides here too.
    """
    if previous is None:
        return None
    paint = Path(previous) / folder.name / "paint"
    try:
        record = json.loads((paint / "section.execution.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    same_inputs = (str(record.get("input_mesh_sha256", "")).lower() == sha256(folder / "section.obj")
                   and str(record.get("reference_sha256", "")).lower() == sha256(folder / "reference.png"))
    same_settings = (record.get("views"), record.get("resolution"), record.get("atlas"),
                     int(record.get("bake_size") or 0)) == (args.views, args.resolution, args.atlas, int(bake_size))
    if not (same_inputs and same_settings):
        return None
    try:
        read_paint(paint)
    except (RuntimeError, OSError, ValueError):
        return None
    return paint


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
    if not 0.2 <= args.section <= 5.0:
        return failed("a section is 0.2 to 5 metres across. Got {0}".format(args.section))
    if not 0.0 < args.overlap <= 0.8:
        return failed("overlap is a fraction of a section above 0 and up to 0.8. Got {0}".format(args.overlap))
    if not 0.0 <= args.context <= 0.5:
        return failed("context is a fraction of a section from 0 to 0.5. Got {0}".format(args.context))
    if not 0.0 <= args.keep_tone <= 0.5:
        return failed("keep-tone runs from 0 to 0.5 metres. Got {0}".format(args.keep_tone))
    if not 0.0 <= args.keep_colour <= 0.5:
        return failed("keep-colour runs from 0 to 0.5 metres. Got {0}".format(args.keep_colour))
    if not 2 <= args.max_sections <= 64:
        return failed("max-sections runs from 2 to 64. Got {0}".format(args.max_sections))
    if not 0 <= args.inpaint_reach <= 256:
        return failed("inpaint-reach runs from 0 to 256 texels. Got {0}".format(args.inpaint_reach))

    raw = args.source.read_bytes()
    try:
        document, binary = read_glb(raw)
        positions, uvs, triangles = mesh_from_glb(document, binary)
    except (ValueError, KeyError, IndexError) as problem:
        return failed("the source could not be read as a painted model: {0}".format(problem))
    materials = document.get("materials", [])
    if len(materials) != 1:
        return failed("the source carries {0} materials. Sections are painted onto one painted "
                      "atlas, before surfaces are changed".format(len(materials)))
    pbr = materials[0].get("pbrMetallicRoughness", {})
    albedo_index = texture_image(document, pbr.get("baseColorTexture"))
    metal_rough_index = texture_image(document, pbr.get("metallicRoughnessTexture"))
    if albedo_index is None:
        return failed("the source's material has no base colour texture to paint over")

    extent = positions.max(axis=0) - positions.min(axis=0)
    report = {
        "schema": SCHEMA,
        "source": str(args.source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "output": str(args.output),
        "reference": str(args.reference),
        "reference_sha256": sha256(args.reference),
        "extent_m": [round(float(e), 4) for e in extent],
        "settings": {"section_m": args.section, "overlap": args.overlap, "context": args.context,
                     "keep_colour_m": args.keep_colour, "keep_tone_m": args.keep_tone,
                     "min_length_m": args.min_length,
                     "max_sections": args.max_sections, "views": args.views,
                     "resolution": args.resolution, "atlas": args.atlas,
                     "inpaint_reach": args.inpaint_reach,
                     "painter_runs": "one per section" if args.separate_runs else "one for every section"},
        "geometry_unchanged": True,
        "uvs_unchanged": True,
        "requires_fixed_view_review": True,
        "production_grade": False,
    }

    # What the whole-model paint gave each pixel, about: the longest side, with
    # the painter's framing margin, over one view. In every receipt, painted or
    # not, so a consumer can say what passing a model through means.
    report["whole_model_mm_per_pixel"] = round(float(extent.max()) * 1.1 / args.resolution * 1000.0, 2)

    def finish(painted: bool, note: str, reason: str | None = None) -> int:
        report["painted"] = painted
        # A word a program can act on; the note says it in a sentence.
        report["reason"] = reason
        report["note"] = note
        report["seconds"] = round(time.monotonic() - started, 1)
        if args.output.is_file():
            report["output_sha256"] = sha256(args.output)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("{0} {1}".format(TAG, note))
        return 0

    if float(extent.max()) < args.min_length:
        if not args.plan_only:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(raw)
        return finish(False, "the model is {0:.2f} m at its longest, under {1} m: the whole-model "
                             "paint already sees it at section scale, so it is passed through "
                             "unchanged".format(float(extent.max()), args.min_length), "shorter_than_min_length")

    if not args.plan_only:
        if not args.launcher.is_file():
            return failed("the paint launcher is missing: {0}".format(args.launcher))
        if args.legacy_root is None or not (args.legacy_root / ".venv-hy3d21" / "Scripts" / "python.exe").is_file():
            return failed("the painter's environment is missing under {0}".format(args.legacy_root))
    elif args.cutout is None and args.legacy_root is None:
        image = Image.open(args.reference)
        if image.mode != "RGBA":
            return failed("planning without the painter needs --cutout or a reference with its own alpha")

    attempt = next_attempt(args.output, "sections")
    attempt.mkdir(parents=True)
    try:
        cutout, cutout_record = load_cutout(args, attempt)
    except RuntimeError as problem:
        return failed(str(problem))
    alpha = np.asarray(cutout.getchannel("A"))
    figure = figure_box(alpha)
    if figure is None:
        return failed("no figure was found in the reference")
    try:
        frame, scores = match_orientation(positions, triangles, alpha)
    except ValueError as problem:
        return failed(str(problem))
    ranked = sorted(scores.items(), key=lambda item: -item[1])[:3]
    report["reference_cutout"] = cutout_record
    report["figure_box"] = list(figure)
    report["orientation"] = {"chosen": describe(frame), "chosen_score": round(scores[frame], 4),
                             "generator_frame_score": round(scores[GENERATOR_FRAME], 4),
                             "best": [[describe(f), round(s, 4)] for f, s in ranked]}

    # A cell with almost none of the model in it is not worth a painter run; on
    # a model of a few hundred faces (a test, a stand-in) that is any at all.
    min_faces = max(1, min(200, len(triangles) // 50))
    plan = plan_sections(positions, triangles, args.section, args.overlap, args.context,
                         args.max_sections, min_faces)
    if len(plan["cells"]) < 2:
        if not args.plan_only:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(raw)
        return finish(False, "the model fits one section, so it is passed through unchanged", "fits_one_section")
    points = project(positions, frame)
    model_low, model_high = points.min(axis=0), points.max(axis=0)
    whole_mm = float(extent.max()) * 1.1 / args.resolution * 1000.0
    # The texels a metre the sheet will hold, to size each section's bake to.
    sheet_density = texel_density(positions, uvs, triangles, args.atlas)
    sections = []
    for number, cell in enumerate(plan["cells"]):
        folder = attempt / "section-{0:02d}".format(number)
        folder.mkdir()
        used = np.unique(triangles[cell["faces"]])
        box = crop_box(points[used], figure, model_low, model_high, args.crop_margin)
        crop_png = folder / "reference.png"
        cut_crop(cutout, box).save(crop_png, format="PNG")
        mesh_obj = folder / "section.obj"
        vertices, faces = write_obj(mesh_obj, positions, uvs, triangles, cell["faces"])
        span = positions[used].max(axis=0) - positions[used].min(axis=0)
        sections.append({
            "number": number,
            "grid_index": cell["index"],
            "core_m": cell["core_m"],
            "faces_painted": faces,
            "faces_weighted": int((cell["weights"] > 0).sum()),
            "vertices": vertices,
            "span_m": [round(float(s), 4) for s in span],
            "painted_mm_per_pixel": round(float(span.max()) * 1.1 / args.resolution * 1000.0, 2),
            "bake_size": bake_size_for(float(span.max()), sheet_density, args.bake_scale),
            "crop_box": list(box),
            "crop_sha256": sha256(crop_png),
            "folder": str(folder),
        })
    report["plan"] = {"grid": plan["counts"], "section_m": round(plan["section_m"], 4),
                      "skipped_cells": plan["skipped"],
                      "whole_model_mm_per_pixel": round(whole_mm, 2), "sections": sections,
                      "attempt": str(attempt)}

    if args.plan_only:
        return finish(False, "planned {0} sections ({1}) at about {2:.1f} mm a painted pixel, down "
                             "from {3:.1f}; nothing painted".format(
                                 len(sections), " x ".join(map(str, plan["counts"])),
                                 max(s["painted_mm_per_pixel"] for s in sections), whole_mm), "plan_only")

    # The sheet the sections are laid on: the atlas asked for, even when the
    # first paint is smaller. Its colour is only ever used blurred, so it is
    # brought up to size rather than the sections brought down to it.
    size = max(Image.open(io.BytesIO(image_bytes(document, binary, albedo_index))).size[0], args.atlas)
    base_albedo = as_pixels(Image.open(io.BytesIO(image_bytes(document, binary, albedo_index))),
                            size).astype(np.float32)
    base_mr = None
    if metal_rough_index is not None:
        base_mr = as_pixels(Image.open(io.BytesIO(image_bytes(document, binary, metal_rough_index))),
                            size).astype(np.float32)
    density = texel_density(positions, uvs, triangles, size)
    keep = args.keep_colour if args.keep_colour > 0 else args.keep_tone
    sigma = keep * density if keep > 0 else 0.0
    # Keeping the design: the base's colour, the sections' light and dark. Their
    # tone is the base's, so there is nothing between them to match.
    mode = "light" if args.keep_colour > 0 else "colour"
    harmonize_sections = not args.no_harmonize and args.keep_colour == 0
    albedo_layers, mr_layers = [], []
    sheet = face_sheet(uvs, triangles, size)
    timings = {}
    clock = time.monotonic()
    pending = []
    for record in sections:
        folder = Path(record["folder"])
        earlier = reusable_paint(args.reuse_sections, folder, args, record["bake_size"])
        if earlier is not None:
            shutil.copytree(earlier, folder / "paint")
            record["reused_from"] = str(earlier)
            print("{0} section {1} reused from {2}".format(TAG, record["number"] + 1, earlier), flush=True)
        else:
            pending.append(record)
    exit_codes = {}
    if pending and args.separate_runs:
        for record in pending:
            folder = Path(record["folder"])
            print("{0} painting section {1} of {2}: {3} faces, {4:.2f} m across".format(
                TAG, record["number"] + 1, len(sections), record["faces_painted"], max(record["span_m"])),
                flush=True)
            try:
                _, _, exit_codes[record["number"]] = paint_section(
                    args, folder / "section.obj", folder / "reference.png", folder / "paint", record["bake_size"])
            except (RuntimeError, subprocess.TimeoutExpired) as problem:
                return failed("section {0} could not be painted, and no half-painted model is delivered: "
                              "{1}".format(record["number"], problem))
    elif pending:
        print("{0} painting {1} sections in one painter run{2}".format(
            TAG, len(pending), "" if len(pending) == len(sections) else
            " ({0} reused)".format(len(sections) - len(pending))), flush=True)
        try:
            exit_code = paint_batch(args, [(Path(r["folder"]) / "section.obj", Path(r["folder"]) / "reference.png",
                                            Path(r["folder"]) / "paint", r["bake_size"]) for r in pending], attempt)
        except subprocess.TimeoutExpired as problem:
            return failed("the painter ran past {0:.0f} minutes and was stopped; no half-painted model is "
                          "delivered. The sections it finished are kept: pass --reuse-sections {1} to paint "
                          "only the rest".format(problem.timeout / 60.0, attempt))
        exit_codes = {record["number"]: exit_code for record in pending}
    timings["painting"] = round(time.monotonic() - clock, 1)
    clock = time.monotonic()

    for record, cell in zip(sections, plan["cells"]):
        folder = Path(record["folder"])
        try:
            glb, gate = read_paint(folder / "paint", why_unpainted(folder / "paint", attempt))
        except RuntimeError as problem:
            return failed("section {0} could not be painted, and no half-painted model is delivered: "
                          "{1}. The sections that were painted are kept: pass --reuse-sections {2} to "
                          "paint only the rest".format(record["number"], problem, attempt))
        record["gate"] = {key: gate.get(key) for key in ("faces_equal", "geometry_delta", "uv_delta", "atlas")}
        record["launcher_exit_code"] = exit_codes.get(record["number"])
        if "seconds" in gate:
            record["painter_seconds"] = gate["seconds"]
        section_document, section_binary = read_glb(glb.read_bytes())
        section_pbr = section_document["materials"][0].get("pbrMetallicRoughness", {})
        weights, mask = smooth_weights(sheet, triangles, cell["vertex_weights"], cell["faces"])
        section_albedo = texture_image(section_document, section_pbr.get("baseColorTexture"))
        albedo_layers.append((as_pixels(Image.open(io.BytesIO(
            image_bytes(section_document, section_binary, section_albedo))), size), weights, mask))
        section_mr = texture_image(section_document, section_pbr.get("metallicRoughnessTexture"))
        if base_mr is not None and section_mr is not None:
            mr_layers.append((as_pixels(Image.open(io.BytesIO(
                image_bytes(section_document, section_binary, section_mr))), size), weights, mask))

    timings["reading_sections"] = round(time.monotonic() - clock, 1)
    clock = time.monotonic()
    albedo_gains, albedo_pairs = (None, [])
    if harmonize_sections:
        albedo_gains, albedo_pairs = harmonize(albedo_layers)
    replacements = {albedo_index: png_bytes(to_image(
        composite(base_albedo, albedo_layers, sigma, albedo_gains, mode)))}
    mr_gains = None
    if base_mr is not None and len(mr_layers) == len(albedo_layers):
        if harmonize_sections:
            mr_gains, _ = harmonize(mr_layers)
        # Roughness and metal keep the base's layout as well, with the sections'
        # fine variation in them: what is iron stays iron.
        replacements[metal_rough_index] = png_bytes(to_image(composite(base_mr, mr_layers, sigma, mr_gains)))
    for number, record in enumerate(sections):
        if albedo_gains is not None:
            record["colour_gain"] = [round(float(g), 4) for g in albedo_gains[number]]
        if mr_gains is not None:
            record["metal_rough_gain"] = [round(float(g), 4) for g in mr_gains[number]]
    timings["composite"] = round(time.monotonic() - clock, 1)
    clock = time.monotonic()
    document, rebuilt = swap_images(document, binary, replacements)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(write_glb(document, rebuilt))
    timings["writing"] = round(time.monotonic() - clock, 1)
    report["seconds_by_step"] = timings
    report["reused_sections"] = sum(1 for record in sections if "reused_from" in record)
    report["composite"] = {
        "atlas_size": size,
        "texels_per_metre": round(density, 1),
        "tone_blur_texels": round(sigma, 1),
        "tone_from": ("the first paint's colour as painted; the sections' light and dark finer than {0} m".format(
                          args.keep_colour) if mode == "light"
                      else "the first paint, coarser than {0} m".format(args.keep_tone) if sigma > 0
                      else "the sections, matched to each other" if harmonize_sections else "the sections"),
        "neighbour_pairs": albedo_pairs,
        "base_colour_replaced": True,
        "metallic_roughness_replaced": metal_rough_index in replacements,
        "padding": "refilled from the nearest painted texel",
    }
    return finish(True, "laid {0} sections over the first paint: about {1:.1f} mm a painted pixel, "
                        "down from {2:.1f}".format(len(sections),
                                                   max(s["painted_mm_per_pixel"] for s in sections),
                                                   whole_mm))


if __name__ == "__main__":
    sys.exit(main())
