"""Before/after review sheets for a change to Ennix's outfit, painted and groomed.

Renders the same painted close-ups (``scripts/blender/render_outfit_review.py``)
from two rebuilds' assemblies and lays them out side by side, with a difference
column, under the full-body views beside the retained body guidance. A third
sheet draws each outfit's triangle edges over its paint, so the review can see
where the triangles went without a grey clay pass.

Every figure shown is painted and wears its groom: no bald or grey clay beside
the reference.

Usage:
  python scripts/build_outfit_review.py <before_build> <after_build> <out_dir> --blender <exe> \
      [--resolution 1024] [--samples 64] [--device GPU]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CLOSE_UPS = ("jacket-front", "jacket-back", "sash-and-belt", "sleeve-and-hand", "trousers-and-boots",
             "outline-back-three-quarter")
WIRE = ("jacket-front", "jacket-back", "sash-and-belt", "sleeve-and-hand")
FULL = (("front", "body-front.png", "front: body guidance"),
        ("three-quarter", "original.png", "the painting (front; no three-quarter reference)"),
        ("back", "body-back.png", "back: body guidance"))
CELL = 560
WIDE = (720, 480)
DIFFERENCE_GAIN = 4


def font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def render(a, build, out, wire):
    cmd = [a.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
           ROOT / "scripts/blender/render_outfit_review.py", "--",
           build / "assembly/Ennix_Character_Review.blend", out, "--resolution", a.resolution,
           "--samples", a.samples, "--device", a.device, "--views", *(WIRE if wire else CLOSE_UPS)]
    cmd = [str(c) for c in cmd + (["--wire"] if wire else [])]
    out.mkdir(parents=True, exist_ok=True)
    with (out / ("render-wire.log" if wire else "render.log")).open("w", encoding="utf-8") as log:
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
    return cmd


def counts(build):
    """Triangles by region, measured the same way for any build."""
    gate = json.loads((build / "export/gate-rig.json").read_text())
    body = np.load(build / "body/body.npz")
    centres = body["verts"][body["tris"]].mean(axis=1)
    hands = int((np.abs(centres[:, 0]) > 0.80).sum())
    outfit = next(m["tris"] for m in gate["meshes"] if m["name"] == "Ennix_Outfit_And_Hands")
    return {"total": gate["total_tris"], "outfit_and_hands": outfit, "head_parts": gate["total_tris"] - outfit,
            "hands": hands, "garment": len(body["tris"]) - hands, "gate_ok": gate["ok"],
            "tri_budget": gate.get("tri_budget")}


def label(build, c):
    return "{0}\n{1:,} triangles\noutfit {2:,} / hands {3:,}\nhead {4:,}".format(
        build.name, c["total"], c["garment"], c["hands"], c["head_parts"])


def cell(path, size):
    return Image.open(path).convert("RGB").resize(size, Image.LANCZOS)


def difference(before, after, size):
    """Amplified per-pixel difference, and how much the two renders differ."""
    x = np.asarray(Image.open(before).convert("RGB"), dtype=np.float32)
    y = np.asarray(Image.open(after).convert("RGB"), dtype=np.float32)
    d = np.abs(x - y).mean(axis=2)
    stats = {"mean_abs_8bit": round(float(d.mean()), 2),
             "share_over_16": round(float((d > 16).mean()), 4)}
    heat = np.clip(d * DIFFERENCE_GAIN, 0, 255).astype(np.uint8)
    return Image.fromarray(heat, "L").convert("RGB").resize(size, Image.LANCZOS), stats


def caption(im, text):
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, im.width, 30), fill=(20, 20, 22))
    d.text((8, 5), text, fill=(235, 235, 235), font=font(18))
    return im


def sheet(rows, labels, columns, size, title, subtitle, path):
    pad, head, side = 16, 118, 250
    width = side + len(columns) * (size[0] + pad) + pad
    height = head + len(rows) * (size[1] + pad) + pad
    out = Image.new("RGB", (width, height), (34, 34, 36))
    d = ImageDraw.Draw(out)
    d.text((pad, 14), title, fill=(240, 240, 240), font=font(30))
    d.text((pad, 54), subtitle, fill=(180, 180, 180), font=font(18))
    for c, name in enumerate(columns):
        d.text((side + pad + c * (size[0] + pad), head - 26), name, fill=(220, 220, 220), font=font(20))
    for r, (cells, text) in enumerate(zip(rows, labels)):
        y = head + r * (size[1] + pad)
        for line, words in enumerate(text.split("\n")):
            d.text((pad, y + 10 + 26 * line), words, fill=(235, 235, 235) if line == 0 else (170, 170, 170),
                   font=font(22 if line == 0 else 16))
        for c, im in enumerate(cells):
            out.paste(im, (side + pad + c * (size[0] + pad), y))
    out.save(path)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("before", help="a rebuild_ennix.py output")
    p.add_argument("after", help="a rebuild_ennix.py output")
    p.add_argument("out")
    p.add_argument("--blender", required=True)
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--device", choices=("GPU", "CPU"), default="GPU")
    a = p.parse_args()
    before, after, out = Path(a.before).resolve(), Path(a.after).resolve(), Path(a.out).resolve()
    if out.exists():
        p.error("Choose a fresh output directory.")
    commands = {}
    for tag, build in (("before", before), ("after", after)):
        commands[tag] = [render(a, build, out / tag, False), render(a, build, out / tag, True)]
    c_before, c_after = counts(before), counts(after)
    subtitle = ("same cameras, lights, exposure and groom; painted outfit, head and hair | "
                "difference = |after - before| x{0}".format(DIFFERENCE_GAIN))

    # Full figure, from the assemblies' own fixed views, under the retained guidance.
    reference = before / "inputs"
    rows = [[caption(cell(reference / picture, WIDE), what) for _, picture, what in FULL],
            [cell(before / "assembly" / f"{view}.png", WIDE) for view, _, _ in FULL],
            [cell(after / "assembly" / f"{view}.png", WIDE) for view, _, _ in FULL]]
    sheet(rows, ["Reference\nretained guidance\nand the painting", "Before\n" + label(before, c_before),
                 "After\n" + label(after, c_after)],
          [view for view, _, _ in FULL], WIDE, "Ennix outfit: before / after",
          f"{before.name} -> {after.name} | " + subtitle, out / "outfit-sheet.png")

    # Close-ups: before, after, and where they differ.
    measured = {}
    rows, labels = [], []
    for view in CLOSE_UPS:
        b, f = out / "before" / f"{view}.png", out / "after" / f"{view}.png"
        heat, measured[view] = difference(b, f, (CELL, CELL))
        rows.append([cell(b, (CELL, CELL)), cell(f, (CELL, CELL)), heat])
        labels.append("{0}\nmean difference {1}/255\n{2:.1%} of pixels over 16".format(
            view, measured[view]["mean_abs_8bit"], measured[view]["share_over_16"]))
    sheet(rows, labels, [f"before: {c_before['total']:,}", f"after: {c_after['total']:,}", "difference x4"],
          (CELL, CELL), "Ennix outfit: close-ups", subtitle, out / "outfit-details.png")

    # Where the triangles went, drawn over the paint.
    rows = [[cell(out / tag / f"{view}-wire.png", (CELL, CELL)) for view in WIRE]
            for tag in ("before", "after")]
    sheet(rows, ["Before\n" + label(before, c_before), "After\n" + label(after, c_after)], list(WIRE),
          (CELL, CELL), "Ennix outfit: triangle edges over the paint",
          "one-pixel edges of the outfit-and-hands mesh only; head and groom drawn normally",
          out / "outfit-wire.png")

    record = {"before": str(before), "after": str(after), "counts": {"before": c_before, "after": c_after},
              "difference": measured, "commands": commands,
              "sheets": ["outfit-sheet.png", "outfit-details.png", "outfit-wire.png"]}
    (out / "review.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({name: str(out / name) for name in record["sheets"]}))


if __name__ == "__main__":
    sys.exit(main())
