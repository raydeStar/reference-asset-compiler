"""Bind accepted texture maps to a geometry-locked UV authority and export FBX.

This is the character-side counterpart of ``normalize_prop.py`` for an asset
that has passed retopology and UV transport but is not rigged yet. It opens the
UV authority ``.blend``, optionally applies one uniform scale and one
translation (baked into mesh data, never left on the object), rebuilds the
single material as a plain Principled BSDF reading the staged BaseColor,
Roughness, and Metallic PNGs, and exports an FBX with relative texture paths.

It refuses to change topology. Face order and vertex count are compared before
and after, and every vertex must land within one micrometre of
``source * scale + translation``.

Usage:
  blender -b --python scripts/blender/bind_texture_payload.py -- \
      <uv-authority.blend> <out.fbx> <report.json> <textures.json> \
      [--target-height 1.0] [--recenter] [--material-name M_X] [--mesh-name SK_X]

``textures.json`` maps one material name to {"BaseColor": path,
"Roughness": path, "Metallic": path}; the paths must already sit beside the
FBX so the relative references resolve where the payload ships.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector


def arg(argv, name, default=None, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def mesh_bounds(obj):
    coords = np.empty(len(obj.data.vertices) * 3, dtype=np.float64)
    obj.data.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    world = coords @ np.asarray(obj.matrix_world.to_3x3()).T + np.asarray(obj.matrix_world.translation)
    return world.min(axis=0), world.max(axis=0), world


def build_material(material, textures):
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    for channel, socket, colorspace in (
        ("BaseColor", "Base Color", "sRGB"),
        ("Roughness", "Roughness", "Non-Color"),
        ("Metallic", "Metallic", "Non-Color"),
    ):
        path = textures.get(channel)
        if not path:
            continue
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(Path(path).resolve()), check_existing=True)
        node.image.colorspace_settings.name = colorspace
        node.label = channel
        tree.links.new(node.outputs["Color"], bsdf.inputs[socket])
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.5


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    source, out_fbx, report_path, textures_path = (Path(a).resolve() for a in argv[:4])
    target_height = arg(argv, "--target-height", None, float)
    recenter = "--recenter" in argv
    material_name = arg(argv, "--material-name", None)
    mesh_name = arg(argv, "--mesh-name", None)
    if source.suffix.lower() != ".blend":
        raise RuntimeError("Texture payload binding requires the native UV authority .blend")
    if out_fbx.exists() or report_path.exists():
        raise RuntimeError("Refusing to overwrite an existing payload or report")

    textures_by_material = json.loads(textures_path.read_text(encoding="utf-8-sig"))
    if len(textures_by_material) != 1:
        raise RuntimeError("Exactly one material texture set is expected")
    (target_material_name, textures), = textures_by_material.items()

    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    meshes = [o for o in scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("UV authority must contain exactly one mesh, found {0}".format(len(meshes)))
    obj = meshes[0]
    if [o for o in scene.objects if o.type == "ARMATURE"]:
        raise RuntimeError("UV authority unexpectedly carries an armature")
    if any(v for v in obj.matrix_world.to_euler()) or any(abs(s - 1.0) > 1e-9 for s in obj.scale):
        raise RuntimeError("UV authority object carries a rotation or scale; refusing")
    if obj.data.uv_layers.active is None:
        raise RuntimeError("UV authority has no active UV layer")
    uv_layer_name = obj.data.uv_layers.active.name

    lo, hi, before_coords = mesh_bounds(obj)
    faces_before = [tuple(p.vertices) for p in obj.data.polygons]
    before_height = float(hi[2] - lo[2])

    scale = 1.0
    if target_height:
        if before_height <= 1e-6:
            raise RuntimeError("Source has zero height")
        scale = target_height / before_height
    translation = Vector((0.0, 0.0, 0.0))
    if recenter:
        centre_xy = (lo + hi) * 0.5
        # UE expects the origin on the floor between the feet.
        translation = -Vector((centre_xy[0] * scale, centre_xy[1] * scale, lo[2] * scale))
    matrix = Matrix.Translation(translation) @ Matrix.Scale(scale, 4)
    obj.data.transform(obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    obj.data.transform(matrix)
    obj.data.update()

    _lo2, _hi2, after_coords = mesh_bounds(obj)
    expected = before_coords * scale + np.asarray(translation)
    max_delta = float(np.max(np.linalg.norm(after_coords - expected, axis=1)))
    faces_after = [tuple(p.vertices) for p in obj.data.polygons]
    if faces_after != faces_before or max_delta > 1.0e-6:
        raise RuntimeError(
            "Binding changed topology or moved vertices beyond tolerance: delta={0}".format(max_delta))

    if len(obj.data.materials) != 1 or obj.data.materials[0] is None:
        raise RuntimeError("UV authority must carry exactly one material")
    material = obj.data.materials[0]
    source_material_name = material.name
    if material_name:
        material.name = material_name
    if material.name != target_material_name:
        raise RuntimeError(
            "textures.json names material {0!r} but the payload material is {1!r}".format(
                target_material_name, material.name))
    build_material(material, textures)
    if mesh_name:
        obj.name = mesh_name
        obj.data.name = mesh_name

    obj.data.calc_loop_triangles()
    out_fbx.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx),
        use_selection=True,
        path_mode="RELATIVE",
        embed_textures=False,
        apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y",
        axis_up="Z",
        global_scale=1.0,
        apply_unit_scale=True,
        bake_anim=False,
        add_leaf_bones=False,
        object_types={"MESH"},
        mesh_smooth_type="FACE",
    )
    lo2, hi2, _ = mesh_bounds(obj)
    report = {
        "schema": "reference-asset-compiler.texture-payload-binding.v1",
        "source_blend": str(source),
        "blender_version": bpy.app.version_string,
        "uv_layer": uv_layer_name,
        "vertices": len(obj.data.vertices),
        "polygons": len(obj.data.polygons),
        "triangles": len(obj.data.loop_triangles),
        "before": {"height_m": round(before_height, 6),
                   "bounds_min": [round(float(v), 6) for v in lo],
                   "bounds_max": [round(float(v), 6) for v in hi]},
        "uniform_scale_applied": scale,
        "translation_applied": [round(float(v), 6) for v in translation],
        "after": {"height_m": round(float(hi2[2] - lo2[2]), 6),
                  "bounds_min": [round(float(v), 6) for v in lo2],
                  "bounds_max": [round(float(v), 6) for v in hi2]},
        "maximum_vertex_delta_from_similarity_m": max_delta,
        "face_order_unchanged": True,
        "material": {"source_name": source_material_name, "name": material.name,
                     "textures": textures},
        "mesh_name": obj.name,
        "output_fbx": str(out_fbx),
        "export_settings": {"path_mode": "RELATIVE", "axis_forward": "-Y", "axis_up": "Z",
                            "apply_scale_options": "FBX_SCALE_ALL", "mesh_smooth_type": "FACE"},
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[BIND] {0} tris={1} height {2:.4f}m -> {3:.4f}m scale x{4:.6f}".format(
        out_fbx, report["triangles"], before_height, report["after"]["height_m"], scale))
    return 0


if __name__ == "__main__":
    sys.exit(main())
