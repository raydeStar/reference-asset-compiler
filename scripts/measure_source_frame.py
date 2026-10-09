"""Measure the source pictures' orthographic frame for a character profile.

A character profile's `source_camera` block says how the guidance pictures sit
around the acquired body: the picture size, how many pixels a metre is, and
which pixel the body's origin lands on in the front (and back) and the side
pictures. paint_body_from_views.py projects the pictures onto the body with it,
and assemble_character.py frames the review camera with it. Until now those
numbers were measured by hand. This measures them from the alpha-cut pictures
and the figure's height in metres.

The acquired body is centred on z=0 (and on x=0, y=0), so its origin is the
middle of its bounding box. The figure's box in a picture is that bounding box
seen orthographically, and:

  image_px         the front picture's [width, height]; the side picture must
                   be the same size (the back picture shares the front's frame)
  px_per_m         the front figure's height in pixels / --height-m, to 2 decimals
  front_origin_px  the front figure's box centre (x, y)
  side_origin_px   the side figure's box centre x, and the front's y, so both
                   pictures share one height frame

Pixel convention (the one view_projection.sample uses): pixel column c covers
x in [c, c+1), so its centre is c + 0.5. A figure covering columns c0..c1 and
rows r0..r1 has the box [c0, r0, c1 + 1, r1 + 1], is r1 - r0 + 1 pixels tall,
and is centred on ((c0 + c1 + 1) / 2, (r0 + r1 + 1) / 2). Box edges are whole
pixels, so the origins come out on exact half pixels; no other rounding.

A pixel is figure when its alpha / 255 exceeds --alpha-threshold (0.5, the
painter's own mask rule). Pieces (8-connected) smaller than --speck-fraction of
the largest piece are dropped first, so a stray speck of alpha cannot stretch
the box; 0 keeps every piece.

The JSON printed to stdout holds the block under `source_camera` and, apart
from it, what was measured (each figure's box, the side picture's own figure
height and scale) under `measurement`, so a scale mismatch between the front
and side pictures is visible. A side figure more than --scale-tolerance (2%)
taller or shorter than the front's is a warning (stderr), not a refusal.

With --profile the profile's current block is shown beside the measurement.
With --write as well, the block is merged into that profile in place: other
keys, their order and every `_` comment key (including one inside
source_camera) are kept. Without --write no file is touched.

Usage:
  python scripts/measure_source_frame.py --front body-front.png --side body-left.png \
      --height-m 1.8 [--back body-back.png] [--alpha-threshold 0.5] [--speck-fraction 0.001] \
      [--profile profiles/characters/<id>.json [--write]]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

BLOCK = "source_camera"


class FrameError(ValueError):
    """The pictures cannot give a frame (wrong size, no alpha cut, no figure)."""


def load_alpha(path):
    """The picture's alpha as an (H, W) float array in 0..1."""
    with Image.open(path) as im:
        rgba = np.asarray(im.convert("RGBA"))
    return rgba[..., 3].astype(np.float64) / 255.0


def figure_mask(alpha, threshold=0.5, speck_fraction=0.001, name="picture"):
    """Figure pixels (alpha above threshold) without specks; returns (mask, pieces dropped)."""
    mask = alpha > threshold
    if not mask.any():
        raise FrameError("{}: no pixel has alpha above {}; is it alpha-cut?".format(name, threshold))
    if mask.all():
        raise FrameError("{}: every pixel has alpha above {}; it needs an alpha-cut figure".format(name, threshold))
    if speck_fraction <= 0:
        return mask, 0
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), bool))
    sizes = np.bincount(labels.ravel())[1:]
    keep = sizes >= speck_fraction * sizes.max()
    return np.concatenate([[False], keep])[labels], int(count - keep.sum())


def figure_box(mask):
    """[x0, y0, x1, y1] in pixel edges: x1 and y1 are one past the last column and row."""
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    return [int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1]


def _describe(alpha, threshold, speck_fraction, name, warnings):
    mask, dropped = figure_mask(alpha, threshold, speck_fraction, name)
    box = figure_box(mask)
    h, w = mask.shape
    if box[0] == 0 or box[1] == 0 or box[2] == w or box[3] == h:
        warnings.append("{}: the figure touches the picture's edge, so its box may be cut off".format(name))
    return {
        "box_px": box,
        "size_px": [box[2] - box[0], box[3] - box[1]],
        "centre_px": [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2],
        "specks_dropped": dropped,
    }


def measure_frame(front_alpha, side_alpha, height_m, threshold=0.5, speck_fraction=0.001,
                  back_alpha=None, scale_tolerance=0.02):
    """The source_camera block plus what was measured; returns (block, measurement, warnings)."""
    if not height_m > 0:
        raise FrameError("the figure height must be positive, got {}".format(height_m))
    if not 0 <= threshold < 1:
        raise FrameError("the alpha threshold is a fraction in [0, 1), got {}".format(threshold))
    fh, fw = front_alpha.shape
    pictures = [("side", side_alpha)] + ([("back", back_alpha)] if back_alpha is not None else [])
    for name, alpha in pictures:
        if alpha.shape != front_alpha.shape:
            raise FrameError("the {} picture is {} x {} px but the front is {} x {} px; the pictures must "
                             "share one frame".format(name, alpha.shape[1], alpha.shape[0], fw, fh))
    warnings = []
    front = _describe(front_alpha, threshold, speck_fraction, "front", warnings)
    px_per_m = front["size_px"][1] / height_m
    block = {
        "image_px": [fw, fh],
        "px_per_m": round(px_per_m, 2),
        "front_origin_px": list(front["centre_px"]),
        "side_origin_px": None,
    }
    measurement = {
        "height_m": height_m,
        "alpha_threshold": threshold,
        "speck_fraction": speck_fraction,
        "front": front,
    }
    for name, alpha in pictures:
        info = _describe(alpha, threshold, speck_fraction, name, warnings)
        ratio = info["size_px"][1] / front["size_px"][1]
        info["px_per_m"] = round(info["size_px"][1] / height_m, 2)
        info["height_vs_front"] = round(ratio, 4)
        if abs(ratio - 1) > scale_tolerance:
            warnings.append("the {} figure is {} px tall but the front's is {} px ({:+.1f}%): the pictures "
                            "disagree on scale by more than {:g}%".format(
                                name, info["size_px"][1], front["size_px"][1], (ratio - 1) * 100,
                                scale_tolerance * 100))
        measurement[name] = info
    block["side_origin_px"] = [measurement["side"]["centre_px"][0], front["centre_px"][1]]
    return block, measurement, warnings


def merge_block(profile, block):
    """The profile with its source_camera values replaced; every other key, its order and `_` comments kept."""
    merged = dict(profile)
    current = merged.get(BLOCK)
    current = dict(current) if isinstance(current, dict) else {}
    current.update(block)
    merged[BLOCK] = current
    return merged


def format_json(value, indent=0):
    """JSON with two-space indents and short lists of numbers or strings on one line, as profiles are written."""
    pad = "  " * indent
    if isinstance(value, dict) and value:
        items = ["{}  {}: {}".format(pad, json.dumps(k, ensure_ascii=False), format_json(v, indent + 1))
                 for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list) and any(isinstance(v, (dict, list)) for v in value):
        items = [pad + "  " + format_json(v, indent + 1) for v in value]
        return "[\n" + ",\n".join(items) + "\n" + pad + "]"
    if isinstance(value, list):
        return "[" + ", ".join(json.dumps(v, ensure_ascii=False) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def write_profile(path, block):
    """Merge the block into the profile file in place (UTF-8, trailing newline, its own line endings)."""
    path = Path(path)
    raw = path.read_bytes()
    profile = json.loads(raw.decode("utf-8"))
    newline = "\r\n" if b"\r\n" in raw else "\n"
    path.write_text(format_json(merge_block(profile, block)) + "\n", encoding="utf-8", newline=newline)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--front", required=True, help="alpha-cut front picture (RGBA PNG)")
    p.add_argument("--side", required=True, help="alpha-cut side (left) picture, same size as the front")
    p.add_argument("--back", help="optional alpha-cut back picture: checked against the front's frame")
    p.add_argument("--height-m", type=float, required=True, help="the figure's height in metres")
    p.add_argument("--alpha-threshold", type=float, default=0.5,
                   help="figure pixels have alpha / 255 above this (default 0.5)")
    p.add_argument("--speck-fraction", type=float, default=0.001,
                   help="drop pieces smaller than this fraction of the largest piece (default 0.001; 0 keeps all)")
    p.add_argument("--scale-tolerance", type=float, default=0.02,
                   help="warn when the side or back figure's height differs from the front's by more (default 0.02)")
    p.add_argument("--profile", help="character profile to compare with (and, with --write, to update)")
    p.add_argument("--write", action="store_true", help="merge the block into --profile in place")
    a = p.parse_args(argv)
    if a.write and not a.profile:
        p.error("--write needs --profile")
    try:
        block, measurement, warnings = measure_frame(
            load_alpha(a.front), load_alpha(a.side), a.height_m, a.alpha_threshold, a.speck_fraction,
            load_alpha(a.back) if a.back else None, a.scale_tolerance)
    except FrameError as e:
        print("measure_source_frame: " + str(e), file=sys.stderr)
        return 2
    for name in ("front", "side", "back"):
        if name in measurement:
            measurement[name] = dict({"path": str(getattr(a, name))}, **measurement[name])
    report = {BLOCK: block, "measurement": measurement}
    if a.profile:
        profile = json.loads(Path(a.profile).read_text(encoding="utf-8"))
        report["profile_" + BLOCK] = profile.get(BLOCK)
    if warnings:
        report["warnings"] = warnings
    for w in warnings:
        print("warning: " + w, file=sys.stderr)
    print(format_json(report))
    if a.write:
        write_profile(a.profile, block)
        print("wrote {} into {}".format(BLOCK, a.profile), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
