"""Immutable calibrated face evidence of the actual packaged texture payload."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_turnaround import (import_asset, mesh_bounds, setup_world, add_key_lights,
                               place_camera, normalize_pbr_inputs, apply_unlit_albedo,
                               DISPLAY_PROFILES)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--opposite", action="store_true")
    parser.add_argument("--target", type=float, nargs=3,
                        help="Explicit face centre in Blender world metres, for quadrupeds and off-centre heads")
    parser.add_argument("--extent", type=float,
                        help="Height of the face review region in metres; required with --target")
    parser.add_argument("--front-angle", type=float, default=0,
                        help="Face-forward azimuth in degrees, relative to Blender -Y")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if (args.target is None) != (args.extent is None):
        parser.error("--target and --extent must be supplied together")
    if args.target is not None and (not all(math.isfinite(v) for v in args.target)
                                    or not math.isfinite(args.extent) or args.extent <= 0):
        parser.error("face target must be finite and extent must be positive and finite")
    if not math.isfinite(args.front_angle):
        parser.error("--front-angle must be finite")
    source, destination = args.source.resolve(), args.destination.resolve()
    if destination.exists():
        raise RuntimeError("Close-up evidence is retained, never overwritten")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(source)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    low, high = mesh_bounds(meshes)
    size, center = high - low, (high + low) / 2
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    profile = DISPLAY_PROFILES["calibrated"]
    for key in ("view_transform", "look", "exposure"):
        setattr(scene.view_settings, key, profile[key])
    setup_world()
    add_key_lights(center, size.z * .5)
    normalize_pbr_inputs(meshes)
    for mesh in meshes:
        for polygon in mesh.data.polygons:
            polygon.use_smooth = True
    aim = Vector(args.target) if args.target is not None else Vector((center.x, center.y, low.z + size.z * .91))
    extent = args.extent if args.extent is not None else size.z * .24
    views = [("face-front", aim, extent, args.front_angle),
             ("face-three-quarter", aim, extent, args.front_angle + 40),
             ("face-side", aim, extent, args.front_angle + 90)]
    if args.opposite:
        views += [("face-opposite-three-quarter", aim, extent, args.front_angle - 40),
                  ("face-opposite-side", aim, extent, args.front_angle - 90)]
    destination.mkdir(parents=True)
    frames = []
    for mode in ("beauty", "albedo"):
        if mode == "albedo":
            apply_unlit_albedo(meshes)
        for name, target, extent, angle in views:
            place_camera(target, extent, angle)
            path = destination / (mode + "-" + name + ".png")
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            frames.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "display": profile, "frames": frames, "geometry_edited": False,
              "face_target_blender_m": list(aim), "face_extent_m": extent,
              "front_angle_degrees": args.front_angle,
              "production_grade": False}
    (destination / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    print("TEXTURE_CLOSEUPS_READY -- the face must survive more than a flattering distance.")


if __name__ == "__main__":
    main()
