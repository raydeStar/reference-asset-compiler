"""Render unchanged packaged art as true unlit sRGB/RGBA inputs, without display exposure."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_turnaround import import_asset, mesh_bounds, place_camera
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from projection_visibility import raster_depth


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--body-multiview", action="store_true")
    parser.add_argument("--oblique-sides", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source, output = args.source.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Retain inference input renders; never overwrite them.")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_asset(source)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    lo, hi = mesh_bounds(meshes)
    centre, size = (lo + hi) * .5, hi - lo
    textures = {}
    for obj in meshes:
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                raise ValueError("Expected an existing textured material")
            nodes, links = material.node_tree.nodes, material.node_tree.links
            bsdf = nodes.get("Principled BSDF")
            base = bsdf.inputs["Base Color"]
            if not base.is_linked:
                raise ValueError("Expected bound base-color image")
            source_socket = base.links[0].from_socket
            image = source_socket.node.image
            image_path = Path(bpy.path.abspath(image.filepath)).resolve()
            textures[str(image_path)] = sha(image_path)
            image.colorspace_settings.name = "sRGB"
            emission = nodes.new("ShaderNodeEmission")
            emission.inputs["Strength"].default_value = 1
            links.new(source_socket, emission.inputs["Color"])
            links.new(emission.outputs[0], nodes.get("Material Output").inputs["Surface"])
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 16
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = 1024
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    output.mkdir(parents=True)
    (output / "images").mkdir()
    frames = []
    views = [("body-front", centre, max(size), 0, None),
             ("face-front", Vector((centre.x, centre.y, lo.z + size.z * .91)), size.z * .24, 0, None)]
    if args.body_multiview:
        if len(meshes) != 1:
            raise ValueError("Multiview correspondence requires one unambiguous mesh")
        views = [("body-" + name, centre, max(size), angle, elevation)
                 for name, angle, elevation in [("front", 0, None), ("side", 90, None),
                                                ("back", 180, None), ("opposite", 270, None),
                                                ("top", 0, 90), ("bottom", 0, -90)]]
        if args.oblique_sides:
            views[1] = ("body-right-oblique", centre, max(size), 60, None)
            views[3] = ("body-left-oblique", centre, max(size), 300, None)
    for name, aim, extent, angle, elevation in views:
        camera = place_camera(aim, extent, angle, elevation)
        path = output / "images" / (name + ".png")
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        frames.append({"path": str(path), "sha256": sha(path),
                       "camera_position": list(camera.location), "target": list(aim),
                       "lens_mm": camera.data.lens, "angle_degrees": angle, "elevation_degrees": elevation})
        if args.body_multiview:
            obj = meshes[0]
            mesh = obj.data
            mesh.calc_loop_triangles()
            rows = {key: [] for key in ("uv", "screen", "depth", "cosine", "height")}
            for triangle in mesh.loop_triangles:
                points = [obj.matrix_world @ mesh.vertices[index].co for index in triangle.vertices]
                projected = [world_to_camera_view(scene, camera, point) for point in points]
                rows["screen"].append([[p.x * 1024, (1 - p.y) * 1024] for p in projected])
                rows["depth"].append([p.z for p in projected])
                rows["uv"].append([list(mesh.uv_layers.active.data[index].uv) for index in triangle.loops])
                rows["height"].append([(point.z - lo.z) / size.z for point in points])
                rows["cosine"].append([
                    max(0., (obj.matrix_world.to_3x3() @ mesh.vertices[index].normal).normalized().dot(
                        (camera.location - point).normalized())) for index, point in zip(triangle.vertices, points)])
            arrays = {key: np.asarray(value) for key, value in rows.items()}
            arrays["depth_buffer"] = raster_depth(arrays["screen"], arrays["depth"], 1024)
            arrays["depth_tolerance"] = np.asarray(size.z * .001)
            correspondence = output / (name + "-correspondence.npz")
            np.savez_compressed(correspondence, **arrays)
            frames[-1].update(correspondence=str(correspondence), correspondence_sha256=sha(correspondence))
    report = {"source": str(source), "source_sha256": sha(source), "textures": textures,
              "frames": frames, "geometry_edited": False, "uv_edited": False,
              "shader": "base color -> emission only, strength1",
              "display": "Standard sRGB, look None, exposure0, gamma1, transparent RGBA",
              "blender": bpy.app.version_string, "script_sha256": sha(__file__),
              "note": "Inference inputs; do not compare brightness to exposure -1.5 beauty evidence."}
    (output / "inputs.json").write_text(json.dumps(report, indent=2) + "\n")
    print("INTRINSIC_INPUTS_READY -- no borrowed light, no repainted pixels.", flush=True)


if __name__ == "__main__":
    main()
