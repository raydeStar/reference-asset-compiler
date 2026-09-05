"""Pin inputs and run the head-paint composite in Blender.

Wrapper for ``scripts/blender/composite_head_paint.py``: writes the hash-bound
config the Blender script demands, then runs it. Keeps the head-detail paint
pass a two-command affair:

  1. paint the head transport (``run_hy3d21_texture.ps1`` on the output of
     ``scripts/blender/extract_head_transport.py``), recover full-size maps;
  2. ``python scripts/composite_head_paint.py <asset> --body-authority ...``.

Usage:
  python scripts/composite_head_paint.py sunset-ayric-v2 \
      --body-authority work/sunset-ayric-v2/texture/repacked-face-v006/uv-authority.blend \
      --body-maps work/sunset-ayric-v2/texture/collar-pbr-v001 \
      --paint-authority work/sunset-ayric-v2/texture/uv-v001/uv-authority.blend \
      --head-maps work/sunset-ayric-v2/texture/head-fullsize-v002 \
      --z-cut 0.775 --output work/sunset-ayric-v2/texture/head-composite-v001
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rac_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHANNELS = ("BaseColor", "Metallic", "Roughness")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def maps_in(directory: Path) -> dict[str, str]:
    found = {}
    for channel in CHANNELS:
        path = directory / (channel + ".png")
        if not path.is_file():
            raise SystemExit("missing {0} map: {1}".format(channel, path))
        found[channel] = str(path.resolve())
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("asset")
    parser.add_argument("--body-authority", type=Path, required=True,
                        help="UV authority (.blend) whose layout the body maps use")
    parser.add_argument("--body-maps", type=Path, required=True, help="directory with BaseColor/Metallic/Roughness.png")
    parser.add_argument("--paint-authority", type=Path, required=True,
                        help="UV authority (.blend) the head transport was cut from")
    parser.add_argument("--paint-uv-layer", default="UV_RAC_AI_Paint")
    parser.add_argument("--head-maps", type=Path, required=True, help="recovered full-size head paint maps")
    parser.add_argument("--z-cut", type=float, required=True, help="same cut height given to extract_head_transport.py")
    parser.add_argument("--feather", type=float, default=0.035)
    parser.add_argument("--resolution", type=int, default=4096)
    parser.add_argument("--bake-margin-pixels", type=int, default=8)
    parser.add_argument("--mask-dilate-px", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blender", type=Path, default=None)
    args = parser.parse_args()

    if not (ROOT / "work" / args.asset / "state.json").is_file():
        raise SystemExit("no workspace ledger for {0}".format(args.asset))
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("composite output must be a fresh directory: {0}".format(output))
    body_maps = maps_in(args.body_maps)
    head_maps = maps_in(args.head_maps)
    config = {
        "asset_id": args.asset,
        "body_authority": str(args.body_authority.resolve()),
        "paint_authority": str(args.paint_authority.resolve()),
        "paint_uv_layer": args.paint_uv_layer,
        "body_maps": body_maps,
        "head_maps": head_maps,
        "z_cut": args.z_cut,
        "feather": args.feather,
        "resolution": args.resolution,
        "bake_margin_pixels": args.bake_margin_pixels,
        "mask_dilate_px": args.mask_dilate_px,
    }
    config["hashes"] = {
        "body_authority": sha256(Path(config["body_authority"])),
        "paint_authority": sha256(Path(config["paint_authority"])),
        **{"body_" + k: sha256(Path(v)) for k, v in body_maps.items()},
        **{"head_" + k: sha256(Path(v)) for k, v in head_maps.items()},
    }
    config_path = output.parent / (output.name + "-config.json")
    if config_path.exists():
        raise SystemExit("config already exists; choose a fresh output name: {0}".format(config_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    blender = Path(args.blender) if args.blender else Path(rac_env.find_blender())
    command = [str(blender), "-b", "--factory-startup", "--python-exit-code", "1", "--python",
               str(ROOT / "scripts" / "blender" / "composite_head_paint.py"), "--", str(config_path), str(output)]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    for line in completed.stdout.splitlines():
        if line.startswith("HEAD_COMPOSITE_OK") or "Error" in line:
            print(line)
    if completed.returncode:
        print(completed.stderr[-3000:], file=sys.stderr)
        raise SystemExit("head composite failed with exit code {0}".format(completed.returncode))
    print("HEAD_COMPOSITE_READY {0} -- new face, same seams, nothing else touched.".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
