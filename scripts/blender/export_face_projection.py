"""Export camera correspondence for a bounded face texture repair; no mesh edits."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_turnaround import import_asset, mesh_bounds, place_camera
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from projection_visibility import raster_depth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--angle", type=float, default=0)
    parser.add_argument("--min-height", type=float, default=.84)
    parser.add_argument("--max-height", type=float, default=.975)
    parser.add_argument("--half-width", type=float, default=.12)
    parser.add_argument("--visibility", choices=("midpoint", "pixel"), default="midpoint")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source, output = args.source.resolve(), args.output.resolve()
    if not 0 <= args.min_height < args.max_height <= 1 or not 0 < args.half_width <= .2:
        raise ValueError("Projection bounds must remain a bounded head/neck region")
    if output.exists():
        raise RuntimeError("Projection correspondence must use a new evidence directory")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(source)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("A single unambiguous face-bearing mesh is required")
    obj = meshes[0]
    mesh = obj.data
    mesh.calc_loop_triangles()
    low, high = mesh_bounds(meshes)
    height = high.z - low.z
    center = (high + low) / 2
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    camera = place_camera(Vector((center.x, center.y, low.z + height * .91)), height * .24, args.angle)
    bpy.context.view_layer.update()
    vertices = [obj.matrix_world @ v.co for v in mesh.vertices]
    tree = BVHTree.FromPolygons(vertices, [tuple(t.vertices) for t in mesh.loop_triangles], all_triangles=True)
    uv_layer = mesh.uv_layers.active
    rows = {key: [] for key in ("uv", "screen", "cosine", "eligible")}
    depths = []
    for tri in mesh.loop_triangles:
        points = [vertices[i] for i in tri.vertices]
        midpoint = sum(points, Vector()) / 3
        direction = midpoint - camera.location
        distance = direction.length
        direction.normalize()
        hit, _normal, hit_index, hit_distance = tree.ray_cast(camera.location, direction, distance + 1e-5)
        visible = hit is not None and abs(hit_distance - distance) < height * .0005
        eligible = ((visible or args.visibility == "pixel")
                    and low.z + height * args.min_height < midpoint.z < low.z + height * args.max_height
                    and abs(midpoint.x - center.x) < height * args.half_width)
        screen, cosine, depth = [], [], []
        for index, point in zip(tri.vertices, points):
            projected = world_to_camera_view(scene, camera, point)
            screen.append([projected.x * 1024, (1 - projected.y) * 1024])
            depth.append(projected.z)
            normal = (obj.matrix_world.to_3x3() @ mesh.vertices[index].normal).normalized()
            cosine.append(max(0., normal.dot((camera.location - point).normalized())))
        rows["uv"].append([list(uv_layer.data[i].uv) for i in tri.loops])
        rows["screen"].append(screen)
        rows["cosine"].append(cosine)
        rows["eligible"].append(eligible)
        depths.append(depth)
    output.mkdir(parents=True)
    arrays = {k: np.asarray(v) for k, v in rows.items()}
    if args.visibility == "pixel":
        arrays["depth"] = np.asarray(depths)
        arrays["depth_buffer"] = raster_depth(arrays["screen"], arrays["depth"], 1024)
        arrays["depth_tolerance"] = np.asarray(height * .001)
    np.savez_compressed(output / "correspondence.npz", **arrays)
    report = {"source": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "geometry_edited": False, "eligible_triangles": sum(rows["eligible"]),
              "camera": {"matrix_world": [list(row) for row in camera.matrix_world],
                         "lens": camera.data.lens, "frame_size": [1024, 1024]},
              "selection": "camera-visible bounded head/neck geometry, midpoint ray visibility, per-vertex cosine",
              "bounds": {"angle_degrees": args.angle, "minimum_height_fraction": args.min_height,
                         "maximum_height_fraction": args.max_height, "half_width_fraction": args.half_width},
              "visibility_mode": args.visibility,
              "correspondence_sha256": hashlib.sha256((output / "correspondence.npz").read_bytes()).hexdigest()}
    (output / "projection.json").write_text(json.dumps(report, indent=2) + "\n")
    print("FACE_CORRESPONDENCE_READY -- only the declared surface gets a hearing.")


if __name__ == "__main__":
    main()
