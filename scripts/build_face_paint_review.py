"""Before/after review sheet for the Ennix face-paint stage, beside the guidance.

Renders the groomed head twice with identical settings -- once with the surface
stage's paint (before), once with the face-paint stage's (after) -- from the
front, three-quarter and side, and lays them out under the reference at each
angle: the front guidance, the original painting (no three-quarter guidance
exists; the painting is the nearest view), and the left guidance. A second
sheet puts close-ups of the cheeks, the hairline and the jaw side by side.

Every head shown wears its groom: no bald or grey clay beside the painting.

Usage:
  python scripts/build_face_paint_review.py <rebuild_dir> <out_dir> --blender <exe> \
      --left-guidance ennix-head-left-v1.png [--resolution 1024] [--samples 64]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ("front", "three-quarter", "side")
CELL = 560
# Close-ups as fractions of a render (left, top, right, bottom), with what each is for.
DETAILS = (("front", (0.27, 0.36, 0.73, 0.66), "cheeks: blush calmed"),
           ("front", (0.30, 0.16, 0.70, 0.46), "forehead hairline and parting"),
           ("three-quarter", (0.36, 0.20, 0.76, 0.56), "temple hairline"),
           ("three-quarter", (0.38, 0.42, 0.80, 0.80), "jaw, sideburn and neck"),
           ("front", (0.30, 0.52, 0.70, 0.82), "moustache, soul patch and chin"),
           ("side", (0.20, 0.40, 0.62, 0.80), "side of the jaw and under-jaw"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render(a, build, texture, out):
    inputs = build / "inputs"
    cmd = [a.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
           str(ROOT / "scripts/blender/render_painted_head.py"), "--",
           inputs / "template.npz", build / "head.npz", inputs / "head.json", inputs / "hair.npz", texture,
           inputs / "hair-basecolor.png", inputs / "head-front.png", out, "--strands", build / "strands.npz",
           "--resolution", a.resolution, "--samples", a.samples, "--views", *VIEWS, "--subdivision", 1,
           "--oral-helpers", "--skin-emission", .4, "--hair-tint", .85, .95, 1.05, "--hair-roughness", .45]
    cmd = [str(c) for c in cmd]
    out.mkdir(parents=True, exist_ok=True)
    with (out / "render.log").open("w", encoding="utf-8") as log:
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
    return cmd


def framed(path, square=0.78):
    """A render's central square (the head with its hair), scaled to the cell."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = int(min(w, h) * square)
    box = ((w - s) // 2, (h - s) // 2 - int(0.02 * h), (w + s) // 2, (h + s) // 2 - int(0.02 * h))
    return im.crop(box).resize((CELL, CELL), Image.LANCZOS)


def close_up(path, frac, caption):
    """A square close-up around a fraction box of a render, captioned."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    cx, cy = (frac[0] + frac[2]) / 2 * w, (frac[1] + frac[3]) / 2 * h
    half = max((frac[2] - frac[0]) * w, (frac[3] - frac[1]) * h) / 2
    cell = im.crop((int(cx - half), int(cy - half), int(cx + half), int(cy + half))).resize((CELL, CELL), Image.LANCZOS)
    d = ImageDraw.Draw(cell)
    d.rectangle((0, 0, CELL, 30), fill=(20, 20, 22))
    d.text((8, 5), caption, fill=(235, 235, 235), font=font(18))
    return cell


def reference(path, crop=None):
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
    return im.resize((CELL, CELL), Image.LANCZOS)


def sheet(rows, labels, columns, title, subtitle, path):
    pad, head, side = 16, 118, 210
    width = side + len(columns) * (CELL + pad) + pad
    height = head + len(rows) * (CELL + pad) + pad + 40
    out = Image.new("RGB", (width, height), (34, 34, 36))
    d = ImageDraw.Draw(out)
    d.text((pad, 14), title, fill=(240, 240, 240), font=font(30))
    d.text((pad, 54), subtitle, fill=(180, 180, 180), font=font(18))
    for c, name in enumerate(columns):
        d.text((side + pad + c * (CELL + pad), head - 26), name, fill=(220, 220, 220), font=font(20))
    for r, (cells, label) in enumerate(zip(rows, labels)):
        y = head + r * (CELL + pad)
        for line, text in enumerate(label.split("\n")):
            d.text((pad, y + 10 + 26 * line), text, fill=(235, 235, 235) if line == 0 else (170, 170, 170),
                   font=font(22 if line == 0 else 16))
        for c, cell in enumerate(cells):
            if cell is not None:
                out.paste(cell, (side + pad + c * (CELL + pad), y))
    out.save(path)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("build", help="a rebuild_ennix.py output with face-paint/")
    p.add_argument("out")
    p.add_argument("--blender", required=True)
    p.add_argument("--left-guidance", required=True, help="the left-profile head guidance picture")
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--samples", type=int, default=64)
    a = p.parse_args()
    build, out = Path(a.build).resolve(), Path(a.out).resolve()
    before_tex, after_tex = build / "paint/head_basecolor.png", build / "face-paint/head_basecolor.png"
    if not after_tex.is_file():
        p.error("No face-paint/head_basecolor.png in the build: run it with a recipe that has face_paint.")
    commands = {"before": render(a, build, before_tex, out / "before"),
                "after": render(a, build, after_tex, out / "after")}
    inputs = build / "inputs"
    refs = [reference(inputs / "head-front.png"), reference(inputs / "original-head-crop.png", (110, 20, 990, 900)),
            reference(a.left_guidance)]
    rows = [refs, [framed(out / "before" / f"neutral-{v}.png") for v in VIEWS],
            [framed(out / "after" / f"neutral-{v}.png") for v in VIEWS]]
    labels = ["Reference\nfront & left: head guidance\n3/4: the painting\n(no 3/4 guidance exists)",
              "Before\nsurface stage paint\n(paint/)", "After\nface-paint stage\n(face-paint/)"]
    recipe = json.loads((build / "build-receipt.json").read_text()).get("recipe_sha256", "")
    sheet(rows, labels, ["front", "three-quarter", "side"], "Ennix face paint: before / after",
          f"{build.name} | same groom, geometry, lights and camera; only the head texture differs | recipe sha {recipe[:12]}",
          out / "face-paint-sheet.png")
    detail_rows, detail_labels = [], []
    for i in range(0, len(DETAILS), 3):
        for tag in ("before", "after"):
            detail_rows.append([close_up(out / tag / f"neutral-{view}.png", frac, f"{i + k + 1}. {what}")
                                for k, (view, frac, what) in enumerate(DETAILS[i:i + 3])])
            detail_labels.append(f"{tag.capitalize()}\n{'surface stage' if tag == 'before' else 'face-paint stage'}")
    sheet(detail_rows, detail_labels, ["", "", ""], "Ennix face paint: close-ups",
          "each pair of rows: before above, after below; the same renders as the main sheet",
          out / "face-paint-details.png")
    # Where each change applies, drawn on the front guidance by the stage itself.
    shutil.copy2(build / "face-paint/regions-front.png", out / "face-paint-regions.png")
    record = {"build": str(build), "before_texture_sha256": sha(before_tex), "after_texture_sha256": sha(after_tex),
              "left_guidance": str(a.left_guidance), "left_guidance_sha256": sha(a.left_guidance),
              "commands": commands,
              "sheets": ["face-paint-sheet.png", "face-paint-details.png", "face-paint-regions.png"]}
    (out / "review.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"sheet": str(out / "face-paint-sheet.png"), "details": str(out / "face-paint-details.png")}))


if __name__ == "__main__":
    sys.exit(main())
