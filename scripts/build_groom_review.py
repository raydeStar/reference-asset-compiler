"""Before/after review of an Ennix groom, in the review look and in the game look.

Two rebuild_ennix.py builds whose grooms differ (their strands.npz) are rendered
on the same head, paint, lights and camera (the after build's), in two looks:

- The review look the rebuild itself renders (soft studio light, each strand's
  own radius and painted colour), under the references at each angle: the
  front guidance, the painting (no three-quarter guidance exists) and the left
  guidance.
- The game look: strands as the game draws them (Unreal's hair width with its
  root and tip scale, and the hair material's root-to-tip colour) under one
  hard sun with no light through the hair, so a gap between locks reads dark
  as it does in game. Cycles' hair BSDF lights the inside of the hair and hides
  those gaps; this look shows them. Close-ups at the in-game framing carry two
  numbers measured on the renders:
    crevice         share of hair pixels darker than half their
                    surroundings: dark gaps between locks;
    outline_ragged  how far the dense mass's outline in the top half of the
                    hair departs from a smooth one, as a share of the hair
                    there: lock tips gathered into spikes with the sky
                    between them. Fine flyaways are too sparse to count.

Every head shown wears its groom: no bald or grey clay beside the painting.

Usage:
  python scripts/build_groom_review.py <before_build> <after_build> <out_dir> --blender <exe> \
      [--device CPU] [--resolution 768] [--samples 32] [--reuse-renders]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_face_paint_review import close_up, framed, reference, sha, sheet  # noqa: E402

VIEWS = ("front", "three-quarter", "side", "back")
GAME_VIEWS = ("front", "three-quarter", "top")
# Close-ups of the game look as fractions of a render, framed as the in-game face close-up.
GAME_CLOSE = (("front", (0.18, 0.04, 0.82, 0.50), "crown and hairline"),
              ("three-quarter", (0.18, 0.04, 0.82, 0.50), "crown and temple"),
              ("top", (0.14, 0.08, 0.86, 0.80), "from above"))
# What the game draws (TheAetherWars Tools/EnnixPlayer.py: make_groom's strand width and
# M_Ennix_Hair's RootColor/TipColor, linear).
GAME_WIDTH = (0.022, 1.25, 0.35)
GAME_ROOT = (0.07, 0.016, 0.004)
GAME_TIP = (0.34, 0.085, 0.018)


def render(a, head_build, strands, out, look, views, resolution):
    inputs = head_build / "inputs"
    cmd = [a.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
           str(ROOT / "scripts/blender/render_painted_head.py"), "--",
           inputs / "template.npz", head_build / "head.npz", inputs / "head.json", inputs / "hair.npz",
           head_build / "face-paint/head_basecolor.png", inputs / "hair-basecolor.png", inputs / "head-front.png",
           out, "--strands", strands, "--resolution", resolution, "--samples", a.samples, "--views", *views,
           "--subdivision", 1, "--oral-helpers", "--skin-emission", .4, "--device", a.device]
    if look == "review":
        # The rebuild's own head review (rebuild_ennix.py).
        cmd += ["--hair-tint", .85, .95, 1.05, "--hair-roughness", .45]
    else:
        cmd += ["--hair-roughness", .55, "--strand-width", *a.game_width,
                "--strand-gradient", *a.game_root, *a.game_tip, "--cap-colour", *a.game_root,
                "--light", "sun", "--hair-shader", "diffuse", "--id-pass", "--tag", "game"]
    cmd = [str(c) for c in cmd]
    tag = "game" if look == "game" else "neutral"
    if a.reuse_renders and all((out / f"{tag}-{v}.png").is_file() for v in views):
        return cmd
    out.mkdir(parents=True, exist_ok=True)
    with (out / "render.log").open("w", encoding="utf-8") as log:
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
    return cmd


def gap_measures(beauty, ids):
    """Dark gaps between locks and a ragged crown outline, from a game-look render and its id pass."""
    rgb = np.asarray(Image.open(beauty).convert("RGB"), np.float32) / 255
    idp = np.asarray(Image.open(ids).convert("RGB"), np.float32) / 255
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    hair = idp[..., 0] > 0.5
    # Darker than half the hair around it (a gap), not a side turned from the sun.
    sigma = rgb.shape[0] / 170
    w = ndimage.gaussian_filter(hair.astype(np.float32), sigma) + 1e-6
    local = ndimage.gaussian_filter(np.where(hair, lum, 0.0), sigma) / w
    crevice = hair & (lum < 0.5 * local)
    # The dense mass (a lone flyaway is too sparse to count) against its own smoothed outline.
    scale = rgb.shape[0] / 1024
    dense = ndimage.binary_fill_holes(ndimage.gaussian_filter(idp.max(-1), 3 * scale) > 0.5)
    smooth = ndimage.gaussian_filter(dense.astype(np.float32), 16 * scale) > 0.5
    rows = np.flatnonzero(dense.any(1))
    top = np.zeros_like(dense)
    top[:(rows[0] + rows[-1]) // 2] = True
    ragged = (dense ^ smooth) & top
    return {"crevice": round(float(crevice.sum() / hair.sum()), 4),
            "outline_ragged": round(float(ragged.sum() / max(1, (dense & top).sum())), 4)}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("before", help="the rebuild_ennix.py build with the old groom")
    p.add_argument("after", help="the build with the new groom; its head, paint and inputs are used for both")
    p.add_argument("out")
    p.add_argument("--blender", required=True)
    p.add_argument("--device", choices=("GPU", "CPU"), default="CPU")
    p.add_argument("--resolution", type=int, default=768)
    p.add_argument("--game-resolution", type=int, default=1024)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--game-width", type=float, nargs=3, default=GAME_WIDTH, metavar=("CM", "ROOT", "TIP"))
    p.add_argument("--game-root", type=float, nargs=3, default=GAME_ROOT)
    p.add_argument("--game-tip", type=float, nargs=3, default=GAME_TIP)
    p.add_argument("--reuse-renders", action="store_true",
                   help="keep renders already in out_dir (redraw the sheets and measures only)")
    a = p.parse_args()
    before, after, out = Path(a.before).resolve(), Path(a.after).resolve(), Path(a.out).resolve()
    grooms = {"before": before / "strands.npz", "after": after / "strands.npz"}
    commands, measures = {}, {}
    for tag, strands in grooms.items():
        commands[tag] = {"review": render(a, after, strands, out / tag, "review", VIEWS, a.resolution),
                         "game": render(a, after, strands, out / tag / "game", "game", GAME_VIEWS, a.game_resolution)}
        measures[tag] = {v: gap_measures(out / tag / "game" / f"game-{v}.png", out / tag / "game" / f"game-{v}-id.png")
                         for v in GAME_VIEWS}
    inputs = after / "inputs"
    refs = [reference(inputs / "head-front.png"), reference(inputs / "original-head-crop.png", (110, 20, 990, 900)),
            reference(inputs / "head-left.png"), None]
    rows = [refs] + [[framed(out / tag / f"neutral-{v}.png") for v in VIEWS] for tag in grooms]
    counts = {tag: int(len(np.load(s)["counts"])) for tag, s in grooms.items()}
    labels = ["Reference\nfront & left: head guidance\n3/4: the painting\n(no 3/4 guidance exists)",
              f"Before\n{before.name}\n{counts['before']:,} strands", f"After\n{after.name}\n{counts['after']:,} strands"]
    sheet(rows, labels, list(VIEWS), "Ennix groom: before / after",
          f"review look | same head, paint, lights and camera ({after.name}); only the groom differs",
          out / "groom-sheet.png")

    def numbers(tag, view):
        m = measures[tag][view]
        return f"crevice {m['crevice']:.1%}, ragged outline {m['outline_ragged']:.1%}"

    game_rows, game_labels = [], []
    for tag in grooms:
        game_rows.append([close_up(out / tag / "game" / f"game-{view}.png", frac, f"{what}: {numbers(tag, view)}")
                          for view, frac, what in GAME_CLOSE])
        game_labels.append(f"{tag.capitalize()}\n{counts[tag]:,} strands\ngame width, hair\nmaterial colours")
    sheet(game_rows, game_labels, [view for view, _, _ in GAME_CLOSE], "Ennix groom in the game look",
          "strands at the game's width and root-to-tip colour, one hard sun, no light through the hair: "
          "gaps between locks read dark as in game", out / "groom-game-look.png")
    record = {"before": str(before), "after": str(after), "strands_sha256": {t: sha(s) for t, s in grooms.items()},
              "strands": counts, "game_look": {"width": a.game_width, "root": a.game_root, "tip": a.game_tip},
              "measures": measures, "commands": commands, "sheets": ["groom-sheet.png", "groom-game-look.png"]}
    (out / "review.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({"sheet": str(out / "groom-sheet.png"), "game_look": str(out / "groom-game-look.png"),
                      "measures": measures}))


if __name__ == "__main__":
    sys.exit(main())
