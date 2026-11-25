"""Turn one reference picture into a levelled pair of meshes with Pixal3D: the game mesh and the dense one.

The route the owner chose for hard-surface props on 24 November ("Pixal3D wins
by a landslide"): Pixal3D keeps rivets, straps and plank seams as real geometry
where Hunyuan3D rounds them off. This stage does, in one call, what the
playbook's first two steps did by hand:

1. **Cutout.** Pixal3D wants the picture with its background removed. A picture
   that already has a transparent background is used as it is; otherwise the
   painter's environment removes it (`crop_reference_region.py --cutout-only`).
2. **Geometry.** The hash-pinned runner (`workflows/geometry/pixal3d/run_pixal3d.py`)
   runs in Pixal3D's own Linux environment (WSL on Windows). From one generation
   it writes the dense mesh (about a million triangles) and the game mesh,
   simplified by Pixal's own exporter to `--vertex-target` vertices: neither of
   the compiler's reductions keeps Pixal's hard edges.
3. **Levelling.** Pixal3D keeps the picture's camera tilt. `level_pair.py` stands
   both meshes up with one transform, at their real size, so a normal bake from
   the dense one onto the game one lines up.

Out come <output> (the game mesh, .blend, for `uv-unwrap`) and beside it
<output stem>-dense.blend (for `bake-shape --dense`), and a report naming the
seed, the hashes and the levelling.

A seed picks a design, not exact triangles: two runs of one seed give slightly
different meshes. The result is a candidate for fixed-view review.

  python scripts/run_pixal_geometry.py -- <picture> <output.blend> <report.json> --size-m <metres>
      [--size-is height|longest] [--seed 42] [--resolution 1024] [--vertex-target 100000]
      [--up shortest|middle|longest] [--flip] [--blender <exe>] [--legacy-root <studio tree>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler.pixal import linux_path, pixal_command, pixal_paths  # noqa: E402
from reference_asset_compiler.processes import run_bounded  # noqa: E402
from reference_asset_compiler.prop_quality import game_mesh_check  # noqa: E402
from reference_asset_compiler.stages import StageError, run_stage  # noqa: E402

TAG = "[PIXAL]"
SCHEMA = "reference-asset-compiler.pixal-geometry.v1"
RUNNER = ROOT / "workflows" / "geometry" / "pixal3d" / "run_pixal3d.py"
CATALOG_ID = "pixal3d_candidate"


def failed(reason: str) -> int:
    print("{0} FAILED: {1}".format(TAG, reason))
    return 1


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_runner_hash() -> str:
    catalog = json.loads((ROOT / "workflows" / "catalog.json").read_text(encoding="utf-8"))
    for entry in catalog.get("workflows", []):
        if isinstance(entry, dict) and entry.get("id") == CATALOG_ID:
            return str(entry["sha256"]).lower()
    raise RuntimeError("workflows/catalog.json has no {0} entry".format(CATALOG_ID))


def has_transparency(path: Path) -> bool:
    image = Image.open(path)
    if image.mode != "RGBA":
        return False
    alpha = np.asarray(image.getchannel("A"))
    return bool((alpha < 250).mean() > 0.001 and (alpha > 127).mean() > 0.001)


def next_attempt(output: Path) -> Path:
    for number in range(1, 1000):
        attempt = output.parent / "{0}-pixal-attempt{1:03d}".format(output.stem, number)
        try:
            attempt.mkdir(parents=True)
            return attempt
        except FileExistsError:
            continue
    raise RuntimeError("there are already 999 attempts beside {0}".format(output))


def parse_arguments(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("picture", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--size-m", type=float, required=True, help="the real size, in metres")
    parser.add_argument("--topology", choices=("closed", "open"), default="closed")
    parser.add_argument("--size-is", choices=("height", "width", "longest"), default="height",
                        help="whether --size-m is the height (as a landmark on a person gives it) or the longest side")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resolution", type=int, default=1024, choices=(512, 1024, 1536))
    parser.add_argument("--vertex-target", type=int, default=100000,
                        help="the game mesh, in vertices; Pixal's own simplifier gives about as many triangles")
    parser.add_argument("--up", choices=("shortest", "middle", "longest"), default="shortest")
    parser.add_argument("--flip", action="store_true")
    parser.add_argument("--blender", required=True)
    parser.add_argument("--legacy-root", type=Path)
    parser.add_argument("--timeout", type=int, default=3600)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    args = parse_arguments(argv)
    started = time.monotonic()
    if not args.picture.is_file():
        return failed("the picture does not exist: {0}".format(args.picture))
    if args.output.exists():
        return failed("refusing to overwrite {0}".format(args.output))
    if args.output.suffix.lower() != ".blend":
        return failed("the game mesh is written as a .blend; name the output <name>.blend")
    if not 0.01 <= args.size_m <= 50.0:
        return failed("a real size of {0} m is not plausible".format(args.size_m))
    if not 1000 <= args.vertex_target <= 2000000:
        return failed("--vertex-target runs from 1,000 to 2,000,000 vertices")
    if not Path(args.blender).is_file():
        return failed("Blender is needed to level the meshes: {0}".format(args.blender))
    try:
        expected = pinned_runner_hash()
    except (OSError, ValueError, RuntimeError) as problem:
        return failed(str(problem))
    if sha256(RUNNER) != expected:
        return failed("the Pixal3D runner does not match its pinned hash; verify it and update "
                      "workflows/catalog.json before generating")

    attempt = next_attempt(args.output)
    report = {"schema": SCHEMA, "picture": str(args.picture), "picture_sha256": sha256(args.picture),
              "runner": str(RUNNER), "runner_sha256": expected, "seed": args.seed,
              "resolution": args.resolution, "vertex_target": args.vertex_target,
              "size_m": args.size_m, "size_is": args.size_is, "up": args.up, "flip": args.flip,
              "attempt": str(attempt), "deterministic": False,
              "requires_fixed_view_review": True, "production_grade": False}

    def finish(note: str, code: int) -> int:
        report["seconds"] = round(time.monotonic() - started, 1)
        report["note"] = note
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("{0} {1}".format(TAG, note) if code == 0 else "{0} FAILED: {1}".format(TAG, note))
        return code

    # 1. The cutout.
    cutout = attempt / "cutout.png"
    if has_transparency(args.picture):
        shutil.copyfile(args.picture, cutout)
        report["cutout"] = "the picture's own transparency"
    else:
        venv = (args.legacy_root / ".venv-hy3d21" / "Scripts" / "python.exe") if args.legacy_root else None
        if venv is None or not venv.is_file():
            return finish("the picture has an opaque background, and without the painter's environment "
                          "(--legacy-root) there is nothing to remove it with", 1)
        done = run_bounded([str(venv), str(ROOT / "scripts" / "crop_reference_region.py"), str(args.picture),
                            str(cutout), str(attempt / "cutout.json"), "--cutout-only"],
                           capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL,
                           gpu_mib=0, timeout=600)
        if done.returncode != 0 or not cutout.is_file():
            return finish("the picture's background could not be removed: {0}".format(
                " | ".join((done.stdout + done.stderr).strip().splitlines()[-3:])), 1)
        report["cutout"] = "removed by the painter's environment"
    if not has_transparency(cutout):
        return finish("the cutout has no transparent background; Pixal3D needs the object alone", 1)
    report["cutout_sha256"] = sha256(cutout)

    # 2. The geometry, in Pixal3D's own environment.
    paths = pixal_paths()
    generated = attempt / "pixal.glb"
    simplified = attempt / "pixal-v{0}.glb".format(args.vertex_target)
    command = pixal_command([linux_path(RUNNER), "--image", linux_path(cutout), "--output", linux_path(generated),
                             "--resolution", str(args.resolution), "--seed", str(args.seed),
                             "--extra-targets", str(args.vertex_target)], paths)
    report["pixal"] = {"root": paths["root"], "python": paths["python"], "distro": paths["distro"]}
    begun = time.monotonic()
    try:
        done = run_bounded(command, capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL,
                           timeout=args.timeout)
    except subprocess.TimeoutExpired:
        return finish("Pixal3D did not finish within {0} seconds, and everything it started was stopped".format(
            args.timeout), 1)
    (attempt / "pixal.log").write_text(done.stdout + "\n" + done.stderr, encoding="utf-8")
    report["pixal"]["seconds"] = round(time.monotonic() - begun, 1)
    report["pixal"]["exit_code"] = done.returncode
    if done.returncode != 0 or not generated.is_file() or not simplified.is_file():
        tail = [line for line in (done.stdout + "\n" + done.stderr).splitlines() if line.strip()][-4:]
        return finish("Pixal3D produced no meshes (exit {0}): {1}".format(done.returncode, " | ".join(tail)), 1)
    report["pixal"]["dense_sha256"] = sha256(generated)
    report["pixal"]["game_sha256"] = sha256(simplified)

    # 3. Both meshes levelled by one transform, at their real size.
    dense = args.output.with_name(args.output.stem + "-dense.blend")
    if dense.exists():
        return finish("refusing to overwrite {0}".format(dense), 1)
    level = attempt / "level.json"
    game_candidate = attempt / "game.blend"
    dense_candidate = attempt / "dense.blend"
    command = [args.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
               str(ROOT / "scripts" / "blender" / "level_pair.py"), "--", repr(args.size_m), str(level),
               str(generated), str(dense_candidate), str(simplified), str(game_candidate), "--up", args.up,
               "--topology", args.topology]
    if args.flip:
        command.append("--flip")
    if args.size_is in ("height", "width"):
        command.append("--" + args.size_is)
    done = run_bounded(command, capture_output=True, text=True, errors="replace", stdin=subprocess.DEVNULL,
                       timeout=1800)
    if not game_candidate.is_file() or not dense_candidate.is_file() or not level.is_file():
        tail = [line for line in (done.stdout + "\n" + done.stderr).splitlines() if line.strip()][-4:]
        return finish("levelling failed (exit {0}): {1}".format(done.returncode, " | ".join(tail)), 1)
    report["level"] = json.loads(level.read_text(encoding="utf-8"))
    files = report["level"]["files"]
    check = game_mesh_check(files[1], args.size_m, args.size_is, args.topology)
    report["game_mesh_check"] = check
    if not check["ok"]:
        reason = f'seed {args.seed}: ' + "; ".join(check["reasons"])
        # The artist can inspect a rejected seed without a publishable output.
        views = attempt / "review-views"
        try:
            result = run_stage("review-views", game_candidate, views, attempt / "views.json",
                               repo_root=ROOT, blender=args.blender)
            if result.get("ok"):
                report["rejected_views"] = str(views)
            else:
                report["review_error"] = result.get("error", "Review views failed")
        except (StageError, OSError) as problem:
            report["review_error"] = str(problem)
        return finish(reason, 1)
    if done.returncode != 0:
        return finish(f"levelling exited {done.returncode} after writing its measurements", 1)
    # The game output is the completion marker. Keep the candidates for replay.
    try:
        os.link(dense_candidate, dense)
        try:
            os.link(game_candidate, args.output)
        except OSError:
            dense.unlink()
            raise
    except OSError as problem:
        return finish(f"Could not publish the levelled pair: {problem}", 1)
    report["output"] = str(args.output)
    report["output_sha256"] = sha256(args.output)
    report["dense"] = str(dense)
    report["dense_sha256"] = sha256(dense)
    return finish("seed {0}: a {1:,}-triangle game mesh and a {2:,}-triangle dense one, levelled at {3} m ({4})".format(
        args.seed, files[1]["triangles"], files[0]["triangles"], args.size_m, args.size_is), 0)


if __name__ == "__main__":
    sys.exit(main())
