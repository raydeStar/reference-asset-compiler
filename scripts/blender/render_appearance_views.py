"""Fixed views for comparing two versions of one asset, rendered on the CPU.

The review rig of ``render_turnaround.py`` -- the same four cameras, the same
three-point light and the same calibrated display -- with three differences an
automated comparison needs and a person does not:

- **Cycles on the CPU**, with a capped thread count and a fixed seed. The
  turnaround renders with EEVEE, which needs the GPU, and the GPU on this
  machine usually belongs to somebody else.
- **Framing can be borrowed.** A candidate is rendered through the cameras of
  the original it is compared with, read from the original's manifest, so a
  pixel in one picture is the same place on the asset as the same pixel in the
  other. Framing each from its own bounds would shift both by the few
  millimetres a reduction moves the silhouette, and the comparison would
  measure the shift instead of the paint.
- **Transparent film**, so the silhouette of each is known exactly and the
  comparison is made over the asset, not over the background.

Two passes, each in the four views:
  beauty  lit, calibrated display: what a person sees
  albedo  unlit base colour: where the paint is, with lighting unable to hide
          a smear or invent one

Usage:
  blender -b --factory-startup -t 8 --python scripts/blender/render_appearance_views.py -- \
      <asset.blend|.glb|.gltf> <out_dir> [--resolution 512] [--samples 32] \
      [--threads 8] [--framing <reference views.json>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_turnaround import (  # noqa: E402
    DISPLAY_PROFILES,
    VIEWS,
    add_key_lights,
    apply_unlit_albedo,
    import_asset,
    mesh_bounds,
    normalize_pbr_inputs,
    place_camera,
    setup_world,
)

SCHEMA = "reference-asset-compiler.appearance-views.v1"
PASSES = ("beauty", "albedo")
SEED = 0


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("asset", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--resolution", type=int, default=512)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--framing", type=Path,
                        help="A reference manifest whose cameras this render must reuse")
    return parser.parse_args(values)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def use_cpu(scene, threads: int, samples: int) -> dict:
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    preferences = bpy.context.preferences.addons.get("cycles")
    if preferences is not None:
        preferences.preferences.compute_device_type = "NONE"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = int(threads)
    scene.cycles.samples = int(samples)
    scene.cycles.seed = SEED
    scene.cycles.use_animated_seed = False
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = True
    if hasattr(scene.cycles, "denoiser"):
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    if hasattr(scene.cycles, "denoising_use_gpu"):
        scene.cycles.denoising_use_gpu = False
    device = {
        "engine": scene.render.engine,
        "device": scene.cycles.device,
        "compute_device_type": preferences.preferences.compute_device_type if preferences else None,
        "threads": scene.render.threads,
        "samples": scene.cycles.samples,
        "seed": scene.cycles.seed,
        "denoiser": getattr(scene.cycles, "denoiser", None),
    }
    print("[VIEWS] cycles device={device} compute_device_type={compute_device_type} "
          "threads={threads} samples={samples}".format(**device), flush=True)
    return device


def main() -> int:
    args = parse_args()
    asset, out_dir = args.asset.resolve(), args.out_dir.resolve()
    if not asset.is_file():
        print("[VIEWS] FAILED: the asset does not exist: {0}".format(asset))
        return 1
    manifest_path = out_dir / "views.json"
    if manifest_path.exists():
        print("[VIEWS] FAILED: refusing to overwrite views already rendered in {0}".format(out_dir))
        return 1
    framing = None
    if args.framing is not None:
        reference = json.loads(args.framing.read_text(encoding="utf-8-sig"))
        if reference.get("schema") != SCHEMA:
            print("[VIEWS] FAILED: {0} is not an appearance-views manifest".format(args.framing))
            return 1
        framing = reference["framing"]
        if int(reference["resolution"]) != args.resolution:
            print("[VIEWS] FAILED: borrowed framing was rendered at {0}, not {1}".format(
                reference["resolution"], args.resolution))
            return 1

    started = time.monotonic()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(asset)
    # Only the meshes compete. A .blend can arrive with its own lights and
    # cameras, which would light one side of a comparison and not the other.
    for obj in list(bpy.data.objects):
        if obj.type not in {"MESH"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if not meshes:
        print("[VIEWS] FAILED: no mesh to render")
        return 1

    if framing is None:
        low, high = mesh_bounds(meshes)
        centre = (low + high) * 0.5
        extent = max(high - low)
        framing = {"centre": [round(value, 6) for value in centre], "extent": round(extent, 6),
                   "from": str(asset)}
    centre = Vector(framing["centre"])
    extent = float(framing["extent"])

    scene = bpy.context.scene
    device = use_cpu(scene, args.threads, args.samples)
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"

    setup_world()
    add_key_lights(centre, extent * 0.5)
    profile = DISPLAY_PROFILES["calibrated"]
    view = scene.view_settings
    view.view_transform = profile["view_transform"]
    view.look = profile["look"]
    view.exposure = profile["exposure"]
    normalize_pbr_inputs(meshes)

    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for pass_name in PASSES:
        if pass_name == "albedo":
            apply_unlit_albedo(meshes)
        for name, angle in VIEWS.items():
            place_camera(centre, extent, angle)
            path = out_dir / "{0}-{1}.png".format(pass_name, name)
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            files.append({"pass": pass_name, "view": name, "file": path.name,
                          "sha256": sha256_file(path)})
            print("[VIEWS] {0}".format(path.name), flush=True)

    manifest = {
        "schema": SCHEMA,
        "source": str(asset),
        "source_sha256": sha256_file(asset),
        "resolution": args.resolution,
        "framing": framing,
        "framing_borrowed": args.framing is not None,
        "display": dict(profile),
        "device": device,
        "passes": list(PASSES),
        "views": files,
        "seconds": round(time.monotonic() - started, 1),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("RAC_APPEARANCE_VIEWS_OK manifest={0}".format(manifest_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
