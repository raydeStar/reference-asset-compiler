"""Finish a conformed template head: continuous neck, trimmed hair, paint, review renders.

One repeatable command for everything after conform_head_template.py and
build_hair_shell.py. Every step is a script in this repository; every tool is
open source (Python with NumPy/SciPy/Pillow, Blender for the renders). CPU by
default. Deterministic: the same inputs give byte-identical meshes and
textures (renders are Cycles, denoised, so they match to the eye, not the bit).

Steps
  1. close_head_neck.py    one continuous head + neck on the template topology,
                           ending on a clean collar
  2. trim_hair_shell.py    drop shell pieces hugging the neck below the ears
  3. paint_head_from_views.py
                           skin and hair textures from front/side/back pictures,
                           crown painted from the back picture's strands
  4. trim_hair_by_paint.py drop low shell pieces the pictures painted as skin
  5. render_painted_head.py
                           five views and four expressions (Blender, Cycles)

With --groom the hair becomes its own piece: the shell is smoothed first
(smooth_hair_shell.py) and only bounds and colours a strand groom
(blender/grow_hair_groom.py: scalp roots, swept-back waves, clumped locks)
that the renders draw as Cycles hair over a dark scalp cap.

Usage:
  python scripts/finish_template_head.py --template T.npz --conform C.npz --conform-receipt C.json \
      --hair-shell H.npz --front F.png --side S.png --back B.png \
      --side-landmarks SL.json --template-landmarks TL.json --template-camera TC.json \
      --out OUT_DIR [--blender PATH] [--device CPU|GPU] [--resolution 1024] [--samples 48]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPRESSIONS = {
    "smile": ["mouth-corner-puller=0.8", "eye-left-slit=0.3", "eye-right-slit=0.3"],
    "angry": ["eyebrows-left-down=1", "eyebrows-right-down=1", "mouth-compression=0.5",
              "nose-left-elevation=0.3", "nose-right-elevation=0.3"],
    "shout": ["mouth-open=0.7", "eyebrows-left-up=0.6", "eyebrows-right-up=0.6"],
    "blink": ["eye-left-closure=1", "eye-right-closure=1"],
}


def run(cmd):
    print(">", " ".join(str(c) for c in cmd[:4]), "...", flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser()
    for name in ("template", "conform", "conform-receipt", "hair-shell", "front", "side", "back",
                 "side-landmarks", "template-landmarks", "template-camera", "out"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--blender", default=os.environ.get("RAC_BLENDER"))
    p.add_argument("--device", choices=("CPU", "GPU"), default="CPU")
    p.add_argument("--resolution", type=int, default=1024)
    p.add_argument("--samples", type=int, default=48)
    p.add_argument("--skip-render", action="store_true")
    p.add_argument("--groom", action="store_true", help="grow strand hair inside the shell (needs Blender)")
    a = p.parse_args(argv)
    out = Path(a.out).resolve()
    (out / "paint").mkdir(parents=True, exist_ok=True)
    py = sys.executable
    head, head_json = out / "head.npz", out / "head.json"
    hair_hug, hair_final = out / "hair-hug.npz", out / "hair.npz"
    shell = Path(a.hair_shell)
    if a.groom:
        if not a.blender:
            p.error("--groom needs --blender (or $RAC_BLENDER)")
        shell = out / "hair-smooth.npz"
        run([py, HERE / "smooth_hair_shell.py", a.hair_shell, shell, "--iterations", "30"])

    run([py, HERE / "close_head_neck.py", a.template, a.conform, a.conform_receipt, head, head_json])
    run([py, HERE / "trim_hair_shell.py", a.template, head, shell, hair_hug])
    run([py, HERE / "paint_head_from_views.py", a.template, head, head_json, hair_hug,
         a.front, a.side, a.back, out / "paint", "--side-landmarks", a.side_landmarks,
         "--template-landmarks", a.template_landmarks, "--template-camera", a.template_camera])
    run([py, HERE / "trim_hair_by_paint.py", a.template, head, hair_hug,
         out / "paint" / "head_basecolor.png", out / "paint" / "hair_basecolor.png", hair_final])

    strands = out / "strands.npz"
    if a.groom:
        run([a.blender, "-b", "--factory-startup", "--python", HERE / "blender" / "grow_hair_groom.py", "--",
             Path(a.template).resolve(), head, shell, out / "paint" / "hair_basecolor.png", strands])

    if not a.skip_render:
        if not a.blender:
            p.error("--blender (or $RAC_BLENDER) is needed for the renders; or pass --skip-render")
        base = [a.blender, "-b", "--factory-startup", "--python", HERE / "blender" / "render_painted_head.py",
                "--", Path(a.template).resolve(), head, head_json, hair_final,
                out / "paint" / "head_basecolor.png", out / "paint" / "hair_basecolor.png",
                Path(a.front).resolve(), out / "render", "--resolution", a.resolution,
                "--samples", a.samples, "--device", a.device] + (["--strands", strands] if a.groom else [])
        run(base + ["--views", "front", "three-quarter", "side", "three-quarter-left", "back"])
        for tag, mix in EXPRESSIONS.items():
            run(base + ["--views", "three-quarter-left", "--tag", tag, "--expression", *mix])

    manifest = {
        "schema": "reference-asset-compiler.finish-template-head.v1",
        "inputs": {k: {"path": str(getattr(a, k.replace("-", "_"))),
                       "sha256": sha(getattr(a, k.replace("-", "_")))}
                   for k in ("template", "conform", "conform-receipt", "hair-shell", "front", "side",
                             "back", "side-landmarks", "template-landmarks", "template-camera")},
        "outputs": {str(f.relative_to(out)): sha(f) for f in
                    (head, hair_final, out / "paint" / "head_basecolor.png",
                     out / "paint" / "hair_basecolor.png") + ((strands,) if a.groom else ())},
        "groom": a.groom,
        "render": None if a.skip_render else {"device": a.device, "resolution": a.resolution,
                                               "samples": a.samples},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["outputs"], indent=1))


if __name__ == "__main__":
    main()
