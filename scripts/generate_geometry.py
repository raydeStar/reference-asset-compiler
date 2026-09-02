"""Turn an approved image into a geometry candidate. The missing first stage.

Every routing plan this compiler produces names `generate_candidates` as its
third stage, and until now nothing performed it: the meshes were made by hand
elsewhere and dropped into `out/`. This runs it.

The only geometry route installed on this workstation is Pixal3D, and it lives
in WSL, so this is mostly the careful part of crossing that boundary -- path
translation, an isolated interpreter, and refusing to start a job that cannot
finish.

It refuses rather than fails:

  A candidate producer is not a gate. Nothing here judges the mesh, and calling
  a generated GLB an asset is exactly the error the rest of this repository
  exists to prevent. The output lands in `work/<asset>/candidates/` with a
  record of the seed, resolution, image hash and duration, and it stays a
  candidate until a person has looked at fixed views of it.

Usage:
  python scripts/generate_geometry.py <asset_id> <image.png> [--seed 42]
      [--resolution 1024] [--min-free-vram 20000] [--dry-run]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The value the office-chair recipe recorded for this route. Pixal3D at 1024
# with low_vram still wants most of a 24 GB card, and an out-of-memory kill
# half an hour in is indistinguishable from a crash in the log.
DEFAULT_MIN_FREE_VRAM_MIB = 20000

WSL_PYTHON = os.environ.get("RAC_WSL_PIXAL3D_PYTHON", "/path/to/envs/pixal3d/bin/python")
WSL_PIXAL_ROOT = os.environ.get("PIXAL3D_ROOT", "/path/to/Pixal3D")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_wsl(path: Path) -> str:
    """Windows path to the form WSL can open.

    Forward slashes, deliberately. wsl.exe consumes backslashes on the way
    through, so handing it a native path arrives as
    C:UsersyouSourceRepos... and wslpath rejects it. It accepts the same
    path spelled with forward slashes, which survives the trip intact.
    """
    done = subprocess.run(
        ["wsl.exe", "wslpath", "-a", str(path).replace("\\", "/")],
        capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit("could not translate {0} for WSL: {1}".format(
            path, done.stderr.strip()))
    return done.stdout.strip()


def free_vram_mib():
    """How much of the card is actually available, not how much it has.

    Returns None when nvidia-smi is absent, which is a different thing from
    zero and must not read as "no room".
    """
    done = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.total,memory.used",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True)
    if done.returncode != 0 or not done.stdout.strip():
        return None
    total, used = (int(v.strip()) for v in done.stdout.strip().splitlines()[0].split(","))
    return total - used


# Names that mean "a job", as opposed to a browser or a shell that merely has a
# graphics context. Listing every window on the desktop as a suspect is worse
# than saying nothing.
HEAVY = ("comfy", "python", "blender", "unreal", "ollama", "koboldcpp", "lmstudio")


def gpu_tenants():
    """Who is plausibly holding the card, so the message can name them.

    Per-process memory usually reads as [N/A] without elevation, so the size
    cannot be used to rank them. Filter by what the process IS instead, and say
    that the number is unavailable rather than implying it is zero.
    """
    done = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=process_name,used_memory",
         "--format=csv,noheader"], capture_output=True, text=True)
    if done.returncode != 0:
        return []
    tenants = []
    for line in done.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        name, _, memory = line.partition(",")
        if not any(token in name.lower() for token in HEAVY):
            continue
        memory = memory.strip()
        tenants.append("{0}  [{1}]".format(
            Path(name.strip()).name,
            memory if memory and "N/A" not in memory else "size needs elevation"))
    return tenants[:6]


def check_alpha(image: Path):
    """Pixal3D's wrapper requires a real cutout, and says so late.

    The runner raises after loading the environment, which is slow. Fail here
    instead, where the message can say what to do about it.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    with Image.open(image) as handle:
        if handle.mode != "RGBA":
            return ("{0} is {1}, not RGBA. This route needs a cutout with a real "
                    "alpha channel -- the background removal is deliberately not "
                    "part of it.".format(image.name, handle.mode))
        low, high = handle.getchannel("A").getextrema()
        if (low, high) == (255, 255):
            return ("{0} has an alpha channel but it is fully opaque, so there is "
                    "no cutout in it.".format(image.name))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_id")
    parser.add_argument("image", type=Path)
    parser.add_argument("--adapter", default="pixal3d", choices=("pixal3d",))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resolution", type=int, default=1024)
    parser.add_argument("--min-free-vram", type=int,
                        default=DEFAULT_MIN_FREE_VRAM_MIB)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the command and the preflight, run nothing")
    args = parser.parse_args()

    image = args.image.resolve()
    if not image.is_file():
        print("[GEN] FAILED: no image at {0}".format(image))
        return 1

    problem = check_alpha(image)
    if problem:
        print("[GEN] FAILED: " + problem)
        return 1

    out_dir = ROOT / "work" / args.asset_id / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = "{0}-{1}-{2}-seed{3}".format(
        args.asset_id, args.adapter, args.resolution, args.seed)
    mesh = out_dir / (stem + ".glb")
    report_path = out_dir / (stem + ".json")

    runner = ROOT / "workflows" / "geometry" / "pixal3d" / "run_pixal3d.py"
    command = [
        "wsl.exe", "-e", "env",
        "PIXAL3D_ROOT=" + WSL_PIXAL_ROOT,
        "PYTHONNOUSERSITE=1",
        WSL_PYTHON, to_wsl(runner),
        "--image", to_wsl(image),
        "--output", to_wsl(mesh),
        "--resolution", str(args.resolution),
        "--seed", str(args.seed),
    ]

    free = free_vram_mib()
    print("[GEN] {0} <- {1}".format(args.asset_id, image.name))
    print("[GEN] adapter {0}, resolution {1}, seed {2}".format(
        args.adapter, args.resolution, args.seed))
    print("[GEN] free VRAM {0} MiB, this route wants {1}".format(
        "unknown" if free is None else free, args.min_free_vram))

    if free is not None and free < args.min_free_vram:
        print("[GEN] REFUSED: not enough free VRAM. Held by:")
        for tenant in gpu_tenants() or ["  (nvidia-smi would not name them)"]:
            print("       " + tenant)
        print("       Close what you can spare, or pass --min-free-vram to")
        print("       override deliberately. An out-of-memory kill part way")
        print("       through reads exactly like a crash, and this project")
        print("       does not silently retry crashed inference.")
        return 2

    if args.dry_run:
        print("[GEN] dry run, would execute:")
        print("       " + " ".join(command))
        return 0

    started = time.time()
    done = subprocess.run(command, cwd=str(ROOT))
    elapsed = round(time.time() - started, 1)

    if done.returncode != 0 or not mesh.is_file():
        print("[GEN] FAILED after {0}s: exit {1}, mesh {2}".format(
            elapsed, done.returncode, "written" if mesh.is_file() else "missing"))
        report_path.write_text(json.dumps({
            "asset_id": args.asset_id, "adapter": args.adapter,
            "ok": False, "exit_code": done.returncode,
            "seconds": elapsed, "image_sha256": sha256(image),
        }, indent=2), encoding="utf-8")
        print("[GEN] failure recorded at {0}".format(report_path))
        return 1

    report = {
        "schema": "reference-asset-compiler.geometry-candidate.v1",
        "asset_id": args.asset_id,
        "adapter": args.adapter,
        "ok": True,
        "candidate": str(mesh),
        "candidate_sha256": sha256(mesh),
        "image": str(image),
        "image_sha256": sha256(image),
        "seed": args.seed,
        "resolution": args.resolution,
        "runner": str(runner),
        "runner_sha256": sha256(runner),
        "seconds": elapsed,
        "status": "candidate -- not approved, not an asset",
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[GEN] {0} in {1}s".format(mesh, elapsed))
    print("[GEN] this is a CANDIDATE. Nothing has judged it yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
