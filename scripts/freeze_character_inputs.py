"""Freeze a character's front-end outputs into an input bundle and write its recipe.

rebuild_character.py builds from a frozen bundle (--inputs) whose every file's
SHA-256 the recipe lists; it refuses a missing or changed file. Freezing used
to be done by hand: copy some twenty files under the names the runner reads,
hash each, and copy the newest recipe's shape around the hashes. This does it.

Each input is NAME=PATH: the bundle name the runner reads and the file it comes
from (a directory, such as the CC0 oral assets for `makehuman`, is copied file
by file, as NAME/<relative path>). The bundle directory must be new or empty;
files are copied with their timestamps, never moved or edited. The recipe is a
copy of --recipe-from with `inputs` replaced (sha256, bytes, and the source path
as provenance, which nothing reads), `character` set to the profile, and the
template's `*_note` texts dropped, since they describe the other character's
revisions. Everything else (groom, face paint, body counts, tier, samples) is
the template recipe's starting point: review it before building.

Inputs the runner reads (refused if missing): template.npz, head.npz,
head.json, hair.npz, head-basecolor.png, hair-basecolor.png, head-front.png,
front-landmarks.json, original.png, original-head-crop.png,
original-landmarks.json, placement.json, body-acquisition.blend,
body-front.png, body-back.png, body-left.png, makehuman/... and, unless the
build derives it from its own proxy, rig-landmarks.json. head-left.png is used
by the face-paint and groom reviews. Mesh hair (--hair-mode mesh, or a template
recipe whose hair block says so) adds hair-mesh.npz, hair-mesh-basecolor.png
and hair-mesh-normal.png (build_mesh_hair.py's outputs, see
docs/CHARACTER_MESH_HAIR.md) and sets the new recipe's hair mode.

Usage:
  python scripts/freeze_character_inputs.py --bundle work/<id>/rebuild-inputs \
      --recipe-from recipes/ennix-open-review-20261011.json \
      --recipe-out recipes/<id>-open-review-<date>.json \
      --character profiles/characters/<id>.json \
      template.npz=work/<id>/template.npz head.npz=work/<id>/finish/head.npz ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ("template.npz", "head.npz", "head.json", "hair.npz", "head-basecolor.png", "hair-basecolor.png",
            "head-front.png", "front-landmarks.json", "original.png", "original-head-crop.png",
            "original-landmarks.json", "placement.json", "body-acquisition.blend", "body-front.png",
            "body-back.png", "body-left.png")
REQUIRED_DIRECTORIES = ("makehuman",)
HAIR_MODES = ("strands", "mesh")
MESH_HAIR = ("hair-mesh.npz", "hair-mesh-basecolor.png", "hair-mesh-normal.png")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def expand(pairs):
    """NAME=PATH pairs to {bundle name: source file}, directories file by file."""
    files = {}
    for pair in pairs:
        name, sep, source = pair.partition("=")
        if not sep or not name or not source:
            raise SystemExit(f"Expected NAME=PATH, got {pair!r}")
        source = Path(source)
        if source.is_dir():
            for path in sorted(p for p in source.rglob("*") if p.is_file()):
                files[f"{name}/{path.relative_to(source).as_posix()}"] = path
        elif source.is_file():
            files[name] = source
        else:
            raise SystemExit(f"{name}: no such file or directory: {source}")
    return files


def missing_inputs(names, rig_landmarks_optional, hair_mode="strands"):
    required = REQUIRED + (() if rig_landmarks_optional else ("rig-landmarks.json",))
    required += MESH_HAIR if hair_mode == "mesh" else ()
    gaps = [name for name in required if name not in names]
    gaps += [d + "/" for d in REQUIRED_DIRECTORIES if not any(n.startswith(d + "/") for n in names)]
    return gaps


def recipe_for(template, character, inputs, hair_mode=None):
    recipe = {k: v for k, v in template.items() if not k.endswith("_note")}
    recipe["character"] = character
    recipe["inputs"] = inputs
    if hair_mode:
        recipe["hair"] = {**template.get("hair", {}), "mode": hair_mode}
    return recipe


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", metavar="NAME=PATH")
    p.add_argument("--bundle", required=True, type=Path, help="new or empty directory for the frozen inputs")
    p.add_argument("--recipe-from", required=True, type=Path, help="recipe whose settings start the new one")
    p.add_argument("--recipe-out", required=True, type=Path)
    p.add_argument("--character", required=True,
                   help="the character profile, as the recipe names it (relative to the repository)")
    p.add_argument("--rig-landmarks-optional", action="store_true",
                   help="allow a bundle without rig-landmarks.json (the build derives them from its proxy)")
    p.add_argument("--hair-mode", choices=HAIR_MODES,
                   help="the new recipe's hair: strands (a groom grown in the build) or mesh (frozen mesh hair); "
                        "default: the template recipe's")
    a = p.parse_args(argv)
    template = json.loads(a.recipe_from.read_text(encoding="utf-8"))
    hair_mode = a.hair_mode or template.get("hair", {}).get("mode", "strands")
    files = expand(a.inputs)
    gaps = missing_inputs(files, a.rig_landmarks_optional, hair_mode)
    if gaps:
        p.error("missing bundle inputs: " + ", ".join(gaps))
    if not (ROOT / a.character).is_file() and not Path(a.character).is_file():
        p.error(f"no character profile at {a.character}")
    if a.bundle.exists() and any(a.bundle.iterdir()):
        p.error(f"{a.bundle} is not empty; freeze into a new directory")
    if a.recipe_out.exists():
        p.error(f"{a.recipe_out} exists; recipes are evidence, write a new one")
    inputs = {}
    for name, source in sorted(files.items()):
        dest = a.bundle / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        digest = sha(dest)
        if digest != sha(source):
            raise SystemExit(f"{name}: the copy does not match its source")
        inputs[name] = {"sha256": digest, "bytes": dest.stat().st_size, "source": str(source.resolve())}
    recipe = recipe_for(template, a.character.replace("\\", "/"), inputs, a.hair_mode)
    a.recipe_out.parent.mkdir(parents=True, exist_ok=True)
    a.recipe_out.write_text(json.dumps(recipe, indent=2) + "\n", encoding="utf-8")
    total = sum(item["bytes"] for item in inputs.values())
    print(f"Froze {len(inputs)} files ({total / 2**20:.2f} MiB) into {a.bundle}; recipe {a.recipe_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
