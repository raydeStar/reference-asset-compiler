"""Re-bake a reduced painted mesh from its dense original, then judge it by eye.

The ``rebake-maps`` stage, chained after ``reduce-mesh``:

1. **Bake.** ``scripts/blender/rebake_dense_maps.py`` puts the dense original's
   paint, roughness, metallic and relief onto the reduced mesh with short rays
   and exports a glTF-ready GLB.
2. **Look.** ``scripts/blender/render_appearance_views.py`` renders the original
   and the candidate in the four fixed views, through the same cameras.
3. **Judge.** ``reference_asset_compiler.appearance`` compares them view by
   view. Surface deviation already passed in the reduction; this is the gate
   that can see paint.
4. **Climb.** When the reduction's receipt is given and the candidate fails, the
   next rung of the same budget ladder is reduced (same gates, role and mode)
   and re-baked, until one passes or the ladder runs out. Every rung tried stays
   in the attempt directory and in the receipt.

Nothing is overwritten: each run claims a fresh attempt directory, and the
accepted GLB is copied out of it. Everything runs on the CPU with a capped
thread count.

Usage:
  python scripts/rebake_maps.py -- <reduced.blend|.glb> <output.glb> <report.json> \
      --dense <dense.blend|.glb> [--blender <exe>] [--attempt-directory <dir>] \
      [--reduction-report <reduction-report.json>] [--appearance-reference <original.glb>] \
      [--reference-views <dir>] [--uv-layout auto|keep|fresh] [--normal-resolution 2048] \
      [--samples 4] [--resolution 512] [--view-samples 32] [--threads 8] [--no-climb]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.appearance import (  # noqa: E402
    THRESHOLDS,
    AppearanceError,
    compare_views,
    comparison_sheet,
)
from reference_asset_compiler.rebake import (  # noqa: E402
    SCHEMA,
    RebakeError,
    check_binding,
    read_reduction,
    reduction_options,
    remaining_rungs,
    reusable_views,
    sha256_file,
    triangle_savings,
)
from reference_asset_compiler.stages import run_stage  # noqa: E402

BAKE = ROOT / "scripts" / "blender" / "rebake_dense_maps.py"
VIEWS = ROOT / "scripts" / "blender" / "render_appearance_views.py"


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    if argv and argv[0] == "--":
        argv = argv[1:]
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="The reduced candidate")
    parser.add_argument("output", type=Path, help="Where the accepted GLB goes")
    parser.add_argument("report", type=Path, help="Where the receipt goes")
    parser.add_argument("--dense", type=Path, required=True,
                        help="The dense, painted original the reduction was made from")
    parser.add_argument("--blender", default=os.environ.get("RAC_BLENDER"))
    parser.add_argument("--attempt-directory", type=Path)
    parser.add_argument("--reduction-report", type=Path,
                        help="The reduction's receipt: binds the pair and offers the ladder")
    parser.add_argument("--appearance-reference", type=Path,
                        help="What the candidate must look like; defaults to the dense mesh")
    parser.add_argument("--reference-views", type=Path,
                        help="Views of the reference rendered earlier, reused when they match")
    parser.add_argument("--uv-layout", choices=("auto", "keep", "fresh"), default="auto")
    parser.add_argument("--normal-resolution", type=int, default=2048)
    parser.add_argument("--samples", type=int, default=4, help="Normal bake samples")
    parser.add_argument("--resolution", type=int, default=512, help="Fixed-view render size")
    parser.add_argument("--view-samples", type=int, default=32)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--no-climb", action="store_true",
                        help="Judge this one candidate; do not reduce and re-bake higher rungs")
    parser.add_argument("--timeout", type=int, default=3600,
                        help="Seconds any one Blender run may take")
    return parser.parse_args(argv)


def claim_attempt(output: Path) -> Path:
    for number in range(1, 1000):
        attempt = output.parent / "{0}-rebake-attempt{1:03d}".format(output.stem, number)
        if not attempt.exists():
            return attempt
    raise RebakeError("There are already 999 re-bake attempts beside {0}".format(output))


def run_blender(blender: str, script: Path, arguments: list[str], log: Path, threads: int,
                timeout: int) -> tuple[int, list[str]]:
    """One background Blender, CPU only, its whole output kept beside its work."""
    command = [blender, "-b", "--factory-startup", "-t", str(threads), "--python", str(script),
               "--", *[str(item) for item in arguments]]
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        finished = subprocess.run(command, capture_output=True, text=True, errors="replace",
                                  timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        log.write_text("timed out after {0} s\n".format(timeout), encoding="utf-8")
        return 124, ["{0} did not finish within {1} seconds".format(script.name, timeout)]
    text = (finished.stdout or "") + (finished.stderr or "")
    log.write_text(text, encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    reason = [line.split("FAILED:", 1)[1].strip() for line in lines if "FAILED:" in line]
    return finished.returncode, (reason[-1:] or lines[-5:])


def render_views(blender, asset, directory, args, framing=None) -> tuple[Path | None, str | None]:
    arguments = [asset, directory, "--resolution", args.resolution, "--samples", args.view_samples,
                 "--threads", args.threads]
    if framing is not None:
        arguments += ["--framing", framing]
    code, said = run_blender(blender, VIEWS, arguments, directory.parent / (directory.name + ".log"),
                             args.threads, args.timeout)
    manifest = directory / "views.json"
    if code != 0 or not manifest.is_file():
        return None, "; ".join(said) or "rendering exited with code {0}".format(code)
    return manifest, None


def finish(receipt: dict, args: argparse.Namespace, attempt: Path, started: float) -> int:
    receipt["seconds"] = round(time.monotonic() - started, 1)
    text = json.dumps(receipt, indent=2) + "\n"
    (attempt / "rebake-report.json").write_text(text, encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(text, encoding="utf-8")
    if receipt["status"] == "accepted":
        print("RAC_REBAKE_MAPS_OK report={0} rung={1} triangles={2}".format(
            args.report, receipt["accepted"]["rung"], receipt["accepted"]["triangles"]), flush=True)
        return 0
    print("[REBAKE] FAILED: {0}".format(receipt["failures"][-1]), flush=True)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    started = time.monotonic()
    source, dense = args.source.resolve(), args.dense.resolve()
    args.output, args.report = args.output.resolve(), args.report.resolve()
    if not args.blender or not Path(args.blender).is_file():
        print("[REBAKE] FAILED: this stage needs Blender: pass --blender or set RAC_BLENDER")
        return 1
    for path, role in ((source, "reduced"), (dense, "dense")):
        if not path.is_file():
            print("[REBAKE] FAILED: the {0} mesh does not exist: {1}".format(role, path))
            return 1
    attempt = (args.attempt_directory or claim_attempt(args.output)).resolve()
    if attempt.exists():
        print("[REBAKE] FAILED: refusing to reuse attempt directory {0}".format(attempt))
        return 1
    attempt.mkdir(parents=True)
    reference = (args.appearance_reference or dense).resolve()

    receipt = {
        "schema": SCHEMA,
        "status": "failed",
        "attempt_directory": str(attempt),
        "dense": {"path": str(dense), "sha256": sha256_file(dense)},
        "reduced": {"path": str(source), "sha256": sha256_file(source)},
        "reduction_binding": None,
        "appearance_reference": {"path": str(reference), "sha256": sha256_file(reference)},
        "thresholds": THRESHOLDS,
        "settings": {"uv_layout": args.uv_layout, "normal_resolution": args.normal_resolution,
                     "normal_samples": args.samples, "view_resolution": args.resolution,
                     "view_samples": args.view_samples, "threads": args.threads,
                     "climb": not args.no_climb, "device": "CPU"},
        "attempts": [],
        "accepted": None,
        "failures": [],
        "requires_human_review": True,
        "production_grade": False,
    }

    reduction = None
    rungs: list[int] = []
    if args.reduction_report is not None:
        try:
            reduction = read_reduction(args.reduction_report)
            receipt["reduction_binding"] = {"report": str(args.reduction_report.resolve()),
                                            **check_binding(reduction, dense, source)}
        except RebakeError as problem:
            receipt["failures"].append(str(problem))
            return finish(receipt, args, attempt, started)
        if not args.no_climb:
            rungs = remaining_rungs(reduction)

    # The original is rendered once per run -- or not at all, when views of
    # exactly this file, taken the same way, already exist.
    if args.reference_views is not None and reusable_views(
            args.reference_views / "views.json", reference, args.resolution, args.view_samples):
        reference_manifest = (args.reference_views / "views.json").resolve()
        receipt["appearance_reference"]["views"] = {"manifest": str(reference_manifest),
                                                   "reused": True}
    else:
        reference_manifest, problem = render_views(args.blender, reference,
                                                   attempt / "reference-views", args)
        if reference_manifest is None:
            receipt["failures"].append("The original could not be rendered: " + problem)
            return finish(receipt, args, attempt, started)
        receipt["appearance_reference"]["views"] = {"manifest": str(reference_manifest),
                                                    "reused": False}

    first_rung = ((reduction or {}).get("settings") or {}).get("triangle_budget")
    candidates = [(first_rung, source, args.reduction_report)]
    while candidates:
        rung, reduced, reduction_report = candidates.pop(0)
        label = "rung-{0}".format(rung if rung is not None else "given")
        work = attempt / label
        entry = {"rung": rung, "reduced": str(reduced), "reduction_report":
                 str(reduction_report) if reduction_report else None}
        receipt["attempts"].append(entry)

        bake_dir = work / "bake"
        code, said = run_blender(args.blender, BAKE, [
            dense, reduced, bake_dir, bake_dir / "bake-report.json",
            "--uv-layout", args.uv_layout, "--normal-resolution", args.normal_resolution,
            "--samples", args.samples, "--threads", args.threads,
            "--asset-label", dense.stem.replace("-", "_")],
            work / "bake.log", args.threads, args.timeout)
        bake_report = bake_dir / "bake-report.json"
        if code != 0 or not bake_report.is_file():
            entry["failure"] = "The bake failed: " + ("; ".join(said) or "exit {0}".format(code))
            receipt["failures"].append(entry["failure"])
            break
        baked = json.loads(bake_report.read_text(encoding="utf-8"))
        entry.update({
            "bake_report": str(bake_report),
            "triangles": baked["reduced"]["topology"]["triangles"],
            "vertices": baked["reduced"]["topology"]["vertices"],
            "uv_layout": baked["uv_layout"]["used"],
            "painted_surface_reached_share":
                baked["bakes"]["coverage"].get("painted_surface_reached_share"),
            "glb": baked["output"]["glb"],
            "glb_sha256": baked["output"]["glb_sha256"],
        })
        receipt.setdefault("device", baked.get("device"))
        receipt["dense"]["triangles"] = baked["dense"]["topology"]["triangles"]

        candidate_manifest, problem = render_views(args.blender, Path(baked["output"]["glb"]),
                                                   work / "views", args, reference_manifest)
        if candidate_manifest is None:
            entry["failure"] = "The candidate could not be rendered: " + problem
            receipt["failures"].append(entry["failure"])
            break
        try:
            verdict = compare_views(reference_manifest, candidate_manifest)
        except AppearanceError as problem:
            entry["failure"] = "The views could not be compared: {0}".format(problem)
            receipt["failures"].append(entry["failure"])
            break
        (work / "appearance.json").write_text(json.dumps(verdict, indent=2) + "\n",
                                              encoding="utf-8")
        # The numbers decide what is offered; a person decides what is kept,
        # and this is the picture they decide from.
        sheet = comparison_sheet([
            ("Original", "{0:,} triangles".format(receipt["dense"]["triangles"]),
             reference_manifest.parent),
            ("Re-baked", "{0:,} triangles | lit SSIM {1:.3f}, unlit {2:.3f} (worst view) | {3}"
             .format(entry["triangles"], verdict["summary"]["beauty"]["minimum_ssim"],
                     verdict["summary"]["albedo"]["minimum_ssim"],
                     "passed" if verdict["passed"] else "refused"),
             candidate_manifest.parent)], "beauty", work / "comparison-beauty.png")
        entry["appearance"] = {"passed": verdict["passed"], "failures": verdict["failures"],
                               "summary": verdict["summary"],
                               "report": str(work / "appearance.json"),
                               "views": str(work / "views"),
                               "sheet": str(sheet)}
        print("[REBAKE] {0}: {1} triangles, appearance {2} {3}".format(
            label, entry["triangles"], "passed" if verdict["passed"] else "failed",
            verdict["summary"]), flush=True)
        if verdict["passed"]:
            receipt["status"] = "accepted"
            receipt["accepted"] = {k: entry[k] for k in ("rung", "triangles", "vertices", "glb",
                                                         "glb_sha256", "uv_layout")}
            receipt["accepted"]["comparison_sheet"] = entry["appearance"]["sheet"]
            receipt["savings"] = triangle_savings(receipt["dense"]["triangles"], entry["triangles"])
            deliverable = Path(baked["output"]["glb"])
            # Blender writes PNGs with light compression; the maps are the
            # same pixels at any compression, so they are re-encoded losslessly
            # by the stage that exists for exactly this, at full size. It never
            # makes a file bigger, and when it declines the bake ships as is.
            packed = work / "rebaked-lossless.glb"
            squeezed = run_stage("compress-textures", deliverable, packed,
                                 work / "lossless-textures.json", repo_root=ROOT,
                                 timeout=args.timeout,
                                 options={"colour_size": 0, "data_size": 0,
                                          "texture_format": "png"})
            receipt["accepted"]["lossless_reencode"] = {
                "ok": bool(squeezed.get("ok")) and packed.is_file(),
                "baked_bytes": deliverable.stat().st_size,
                "delivered_bytes": packed.stat().st_size if packed.is_file() else None,
                "error": squeezed.get("error"),
            }
            if receipt["accepted"]["lossless_reencode"]["ok"]:
                deliverable = packed
            args.output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(deliverable, args.output)
            receipt["accepted"].update(delivered_to=str(args.output),
                                       delivered_sha256=sha256_file(args.output),
                                       delivered_bytes=args.output.stat().st_size)
            return finish(receipt, args, attempt, started)
        receipt["failures"].append("{0}: {1}".format(label, "; ".join(verdict["failures"])))

        # Climb: the next rung is reduced afresh from the dense source, with the
        # gates, role and mode the first reduction used.
        while rungs and not candidates:
            next_rung = rungs.pop(0)
            rung_dir = attempt / "rung-{0}".format(next_rung)
            payload = run_stage("reduce-mesh", dense, rung_dir / "reduced.glb",
                                rung_dir / "reduction-report.json", repo_root=ROOT,
                                blender=args.blender, timeout=args.timeout,
                                options=reduction_options(reduction, next_rung))
            if not payload.get("ok"):
                receipt["attempts"].append({"rung": next_rung, "failure": "reduction refused: {0}"
                                            .format(payload.get("error"))})
                continue
            native = Path(payload["receipt"]["output"]["path"])
            candidates.append((next_rung, native, rung_dir / "reduction-report.json"))

    if receipt["status"] != "accepted" and not receipt["failures"]:
        receipt["failures"].append("no candidate was judged")
    if receipt["status"] != "accepted":
        receipt["status"] = "rejected" if any("appearance" in item for item in receipt["attempts"]) \
            else "failed"
        receipt["failures"].append(
            "No rung kept the original's appearance; keep the source rather than ship a smear."
            if receipt["status"] == "rejected" else receipt["failures"][-1])
    return finish(receipt, args, attempt, started)


if __name__ == "__main__":
    raise SystemExit(main())
