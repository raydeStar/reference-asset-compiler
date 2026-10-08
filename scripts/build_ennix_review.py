"""Historical head-only experiment from frozen v18 inputs.

For the selected full character, use rebuild_character.py instead.

No interactive edits or proprietary DCCs. Geometry acquisition is an explicit
input, so a future open model can replace Hunyuan without replacing this build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--blender", required=True)
    p.add_argument("--stage", choices=("all", "groom", "render"), default="all")
    p.add_argument("--views", nargs="+", default=["front", "three-quarter", "side", "back", "top"])
    p.add_argument("--resolution", type=int, default=768)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--guides", type=int, default=300)
    p.add_argument("--children", type=int, default=255)
    a = p.parse_args()
    source, out = Path(a.source).resolve(), Path(a.out).resolve()
    if source == out:
        p.error("source is immutable; choose another output directory")
    out.mkdir(parents=True, exist_ok=True)
    src = json.loads((source / "manifest.json").read_text())
    template = Path(src["inputs"]["template"]["path"])
    front = Path(src["inputs"]["front"]["path"])
    inherited = ["head.npz", "head.json", "hair.npz", "hair-smooth.npz",
                 "paint/head_basecolor.png", "paint/hair_basecolor.png"]
    if a.stage in ("all", "groom"):
        for name in inherited:
            dest = out / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                p.error(f"refusing to overwrite candidate input: {dest}")
            shutil.copy2(source / name, dest)
    commands = []

    def run(script, args):
        cmd = [a.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(ROOT / "scripts/blender" / script), "--"]
        cmd += [str(x) for x in args]
        commands.append(cmd)
        print("Ennix rebuild: the comb is procedural, sir.", script, flush=True)
        subprocess.run(cmd, check=True)

    if a.stage in ("all", "groom"):
        run("grow_hair_groom.py", [template, out / "head.npz", out / "hair-smooth.npz",
             out / "paint/hair_basecolor.png", out / "strands.npz",
             "--guides", a.guides, "--children", a.children, "--seed", 7,
             "--wave", 0.9, "--wave-length", 0.055, 0.095, "--curl", 1.15,
             "--clump", 0.68, "--strays", 0.045, "--length", 0.10, 0.18,
             "--volume", 1.4, "--tip-flick", 0.10, "--layer-wave", 0.22,
             "--part-min-sweep", 0.45, "--strand-radius", 0.00025])
    if a.stage in ("all", "render"):
        run("render_painted_head.py", [template, out / "head.npz", out / "head.json",
             out / "hair.npz", out / "paint/head_basecolor.png", out / "paint/hair_basecolor.png",
             front, out / "render", "--strands", out / "strands.npz", "--device", "GPU",
             "--subdivision", 1, "--oral-helpers", "--resolution", a.resolution,
             "--samples", a.samples, "--save-blend", out / "Ennix-likeness-candidate.blend",
             "--views", *a.views])
    manifest = {
        "schema": "ennix-repeatable-review.v1", "production_ready": False,
        "source_manifest": {"path": str(source / "manifest.json"), "sha256": sha(source / "manifest.json")},
        "source_assets": {name: sha(source / name) for name in inherited},
        "source_tools": {name: sha(ROOT / "scripts/blender" / name)
                         for name in ("grow_hair_groom.py", "render_painted_head.py")},
        "commands": commands,
        "outputs": {str(f.relative_to(out)): sha(f) for f in out.rglob("*")
                    if f.is_file() and f.suffix in (".npz", ".png", ".blend")},
        "provenance": "Frozen Hunyuan acquisition allowed by Mark; Blender GPL, Python PSF, NumPy/SciPy BSD.",
        "review": "Candidate only; compare all views against the original supplied illustration.",
    }
    (out / "build-receipt.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
