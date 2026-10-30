"""Skin-integrity sweep: count where a moving character opens up.

`scripts/blender/render_skin_sweep.py` renders an exported clip set on a
transparent background with back faces in flat magenta. A tear then shows as
either background enclosed by the figure or the inside of the mesh. This module
measures those renders; it does not render, pose or judge appearance.

The sweep follows img2threejs's gate G10 (Apache-2.0), with back-face exposure
added because RAC characters are closed scans and shells rather than primitives.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from .io import read_json, sha256_file, write_retained_json

RENDER_SCHEMA = "reference-asset-compiler.skin-sweep-renders.v1"
REPORT_SCHEMA = "reference-asset-compiler.skin-sweep.v1"
METRICS = ("split_px", "opening_px", "backface_px")
# A see-through blob is a split when its widest point is at most this wide.
SPLIT_WIDTH_M = 0.02
COMPARED_SETTINGS = ("resolution", "pixels_per_metre", "views", "backface_rgb")
LIMITATIONS = ("Counts pixels in fixed views at sampled times; unsampled frames and hidden sides are not covered.",
               "An opening is any background enclosed by the figure, including legitimate gaps such as a hand on a hip.",
               "A split is only a narrow opening: a sleeve close to a coat or a hanging strap counts just as a tear does.",
               "Back faces include legitimate garment interiors and single-sided cards; compare against a baseline.",
               "Creases, stretching, intersections that stay closed and texture swimming are not measured.",
               "Numbers do not establish natural motion or artistic acceptance.")


def _blobs(mask, kind, distance=None, limit=8):
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), bool))
    found = []
    for index, box in enumerate(ndimage.find_objects(labels), 1):
        region = labels[box] == index
        rows, cols = np.nonzero(region)
        blob = {"kind": kind, "px": int(region.sum()),
                "bbox_xywh": [box[1].start, box[0].start, box[1].stop - box[1].start, box[0].stop - box[0].start],
                "centroid_xy": [round(float(cols.mean()) + box[1].start, 1), round(float(rows.mean()) + box[0].start, 1)]}
        if distance is not None:
            blob["max_width_px"] = round(2 * float(distance[box][region].max()), 2)
        found.append(blob)
    found.sort(key=lambda b: -b["px"])
    return found[:limit], count


def classify_pixels(rgba, split_width_px, backface_rgb=(1.0, 0.0, 1.0)):
    """Return masks for thin see-through splits, wider openings and exposed back faces.

    `rgba` is float in [0, 1]. Background is alpha below one half. Background
    connected to the image border is outside the figure; anything else is seen
    through it. Its width is twice the distance to the nearest figure pixel.
    """
    rgba = np.asarray(rgba, dtype=np.float32)
    if rgba.ndim != 3 or rgba.shape[2] != 4 or not np.isfinite(rgba).all():
        raise ValueError("skin sweep needs a finite RGBA image")
    if not split_width_px > 0:
        raise ValueError("split width must be positive")
    figure = rgba[..., 3] >= 0.5
    labels, _ = ndimage.label(~figure)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    enclosed = (labels > 0) & ~np.isin(labels, border)
    distance = ndimage.distance_transform_edt(enclosed)
    split = np.zeros_like(enclosed)
    enclosed_labels, _ = ndimage.label(enclosed)
    for index, box in enumerate(ndimage.find_objects(enclosed_labels), 1):
        region = enclosed_labels[box] == index
        if 2 * distance[box][region].max() <= split_width_px:
            split[box] |= region
    colour = np.asarray(backface_rgb, dtype=np.float32)
    backface = figure & (np.abs(rgba[..., :3] - colour).max(axis=-1) < 0.3)
    return {"split": split, "opening": enclosed & ~split, "backface": backface, "figure": figure,
            "distance": distance}


def measure_frame(rgba, split_width_px, backface_rgb=(1.0, 0.0, 1.0)):
    masks = classify_pixels(rgba, split_width_px, backface_rgb)
    blobs = []
    counts = {}
    for kind in ("split", "opening", "backface"):
        found, count = _blobs(masks[kind], kind, masks["distance"] if kind != "backface" else None)
        blobs += found
        counts[kind + "_blobs"] = count
    return {"split_px": int(masks["split"].sum()), "opening_px": int(masks["opening"].sum()),
            "backface_px": int(masks["backface"].sum()), "figure_px": int(masks["figure"].sum()),
            **counts, "blobs": sorted(blobs, key=lambda b: -b["px"])[:12]}, masks


def overlay(rgba, masks):
    """Grey render on dark grey with splits red, openings yellow and back faces magenta."""
    rgba = np.asarray(rgba, dtype=np.float32)
    grey = rgba[..., :3].mean(axis=-1, keepdims=True) * rgba[..., 3:] + 0.12 * (1 - rgba[..., 3:])
    image = np.repeat(grey, 3, axis=-1)
    for kind, colour in (("opening", (1, .85, 0)), ("split", (1, 0, 0)), ("backface", (1, 0, 1))):
        # Thin features are dilated so a one-pixel tear is visible on a contact sheet.
        mask = ndimage.binary_dilation(masks[kind], iterations=2) if kind == "split" else masks[kind]
        image[mask] = colour
    return Image.fromarray((np.clip(image, 0, 1) * 255).round().astype(np.uint8), "RGB")


def _key(frame):
    return "{0}|{1}|{2}".format(frame["clip"], frame["sample"], frame["view"])


def compare(frames, baseline, tolerance_px, tolerance_ratio):
    """Regressions against a baseline sweep of the same clips, times and views."""
    previous = {_key(f): f for f in baseline["frames"]}
    regressions, unmatched = [], []
    for frame in frames:
        old = previous.get(_key(frame))
        if old is None:
            unmatched.append(_key(frame))
            continue
        if abs(old["time_s"] - frame["time_s"]) > 1e-4:
            raise ValueError("baseline sample times differ for {0}".format(_key(frame)))
        for metric in METRICS:
            allowed = old[metric] + max(tolerance_px, tolerance_ratio * old[metric])
            if frame[metric] > allowed:
                regressions.append({"frame": _key(frame), "metric": metric, "baseline": old[metric],
                                    "candidate": frame[metric], "allowed": math.floor(allowed)})
    return regressions, unmatched


def analyse(render_dir, output, baseline=None, split_width_m=SPLIT_WIDTH_M, tolerance_px=16,
            tolerance_ratio=0.1):
    render_dir, output = Path(render_dir), Path(output)
    manifest = read_json(render_dir / "sweep.json")
    if manifest.get("schema") != RENDER_SCHEMA:
        raise ValueError("not a skin-sweep render manifest")
    if output.exists():
        raise ValueError("Choose a fresh output directory; earlier sweeps are evidence.")
    split_width_px = split_width_m * manifest["pixels_per_metre"]
    backface_rgb = manifest["backface_rgb"]
    frames = []
    (output / "overlays").mkdir(parents=True)
    for frame in manifest["frames"]:
        path = render_dir / frame["image"]
        rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.float32) / 255
        if rgba.shape[:2] != (manifest["resolution"], manifest["resolution"]):
            raise ValueError("render size differs from the manifest: {0}".format(path))
        measured, masks = measure_frame(rgba, split_width_px, backface_rgb)
        target = output / "overlays" / frame["image"]
        target.parent.mkdir(parents=True, exist_ok=True)
        overlay(rgba, masks).save(target)
        frames.append({**{k: frame[k] for k in ("clip", "sample", "time_s", "view")},
                       "image": frame["image"], "image_sha256": sha256_file(path),
                       "overlay": str(target.relative_to(output)).replace("\\", "/"), **measured})
    clips = {}
    for frame in frames:
        row = clips.setdefault(frame["clip"], {m: 0 for m in METRICS} | {"frames": 0})
        row["frames"] += 1
        for metric in METRICS:
            row[metric] = max(row[metric], frame[metric])
    worst = sorted(frames, key=lambda f: -(f["split_px"] + f["backface_px"]))[:10]
    report = {"schema": REPORT_SCHEMA, "render_manifest_sha256": sha256_file(render_dir / "sweep.json"),
              "render_dir": str(render_dir.resolve()), "asset": manifest["asset"],
              "asset_sha256": manifest["asset_sha256"],
              "settings": {k: manifest[k] for k in COMPARED_SETTINGS} | {
                  "split_width_m": split_width_m, "split_width_px": round(split_width_px, 3)},
              "clip_peaks": clips, "worst_frames": [_key(f) for f in worst], "frames": frames,
              "baseline": None, "regressions": [], "unmatched": [], "checks_passed": None,
              "human_approved": False, "limitations": list(LIMITATIONS)}
    if baseline is not None:
        old = read_json(Path(baseline))
        if old.get("schema") != REPORT_SCHEMA:
            raise ValueError("baseline is not a skin-sweep report")
        if old["settings"] != report["settings"]:
            raise ValueError("baseline was rendered or measured with different settings")
        regressions, unmatched = compare(frames, old, tolerance_px, tolerance_ratio)
        report.update({"baseline": {"path": str(Path(baseline).resolve()), "sha256": sha256_file(Path(baseline)),
                                    "asset_sha256": old["asset_sha256"], "tolerance_px": tolerance_px,
                                    "tolerance_ratio": tolerance_ratio},
                       "regressions": regressions, "unmatched": unmatched,
                       "checks_passed": not regressions and not unmatched})
    write_retained_json(output / "report.json", report)
    return {"report": str((output / "report.json").resolve()), "frames": len(frames), "clip_peaks": clips,
            "worst_frames": report["worst_frames"], "regressions": len(report["regressions"]),
            "unmatched": len(report["unmatched"]), "checks_passed": report["checks_passed"]}
