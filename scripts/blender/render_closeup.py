"""Tight fixed-view renders around a named bone, for reviewing detail.

Full-body turnarounds are too small to judge hands, faces or a texture seam.
This frames a sphere around one bone and renders it in several passes so the
cause of a problem is separable: albedo alone rules lighting out, checker rules
UV stretching in or out, clay rules texture out entirely.

Usage:
  blender -b --factory-startup --python scripts/blender/render_closeup.py \
      -- <asset.fbx> <out_dir> <bone> <radius_m> [passes] [angles]

  passes  comma list of beauty,albedo,checker,clay   (default all)
  angles  comma list of degrees                      (default 0,45,90)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def checker_material():
    mat = bpy.data.materials.new("EvidenceChecker")
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfDiffuse")
    tex = tree.nodes.new("ShaderNodeTexChecker")
    # One square per ~1/64 of UV space. Squares that stop being square are
    # stretched UVs; squares that change size are texel-density breaks.
    tex.inputs["Scale"].default_value = 64.0
    tex.inputs["Color1"].default_value = (0.9, 0.9, 0.9, 1.0)
    tex.inputs["Color2"].default_value = (0.15, 0.35, 0.75, 1.0)
    coord = tree.nodes.new("ShaderNodeUVMap")
    tree.links.new(coord.outputs["UV"], tex.inputs["Vector"])
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Color"])
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def clay_material():
    mat = bpy.data.materials.new("EvidenceClay")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.62, 0.62, 0.64, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def albedo_mode(meshes):
    """Emission-only shading: shows the texture with zero lighting response.

    If a shadow is visible in this pass, it is painted into the albedo.
    """
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None or not mat.use_nodes:
                continue
            tree = mat.node_tree
            output = next(
                (n for n in tree.nodes if n.type == "OUTPUT_MATERIAL"), None
            )
            bsdf = next(
                (n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None
            )
            if output is None or bsdf is None:
                continue
            emission = tree.nodes.new("ShaderNodeEmission")
            base = bsdf.inputs["Base Color"]
            if base.is_linked:
                tree.links.new(base.links[0].from_socket, emission.inputs["Color"])
            else:
                emission.inputs["Color"].default_value = base.default_value
            tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])


def setup_lights(centre, radius):
    world = bpy.data.worlds.new("CloseupWorld")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.2, 0.2, 0.2, 1.0)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.6
    bpy.context.scene.world = world
    for name, offset, power in (
        ("Key", (1.0, -1.5, 1.1), 900.0),
        ("Fill", (-1.3, -1.0, 0.3), 320.0),
    ):
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = power * (radius ** 2) * 4.0
        data.size = radius * 2.0
        lamp = bpy.data.objects.new(name, data)
        lamp.location = centre + Vector(offset) * radius * 4.0
        lamp.rotation_euler = (centre - lamp.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.collection.objects.link(lamp)


def place_camera(centre, radius, angle_deg):
    cam_data = bpy.data.cameras.new("CloseupCam")
    cam_data.lens = 85.0
    cam = bpy.data.objects.new("CloseupCam", cam_data)
    bpy.context.collection.objects.link(cam)
    fov = 2.0 * math.atan(0.5 * cam_data.sensor_width / cam_data.lens)
    distance = (radius * 2.4) / (2.0 * math.tan(fov * 0.5))
    angle = math.radians(angle_deg)
    cam.location = centre + Vector(
        (math.sin(angle) * distance, -math.cos(angle) * distance, radius * 0.2)
    )
    cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, out_dir = Path(argv[0]), Path(argv[1])
    bone_name = argv[2]
    radius = float(argv[3])
    passes = argv[4].split(",") if len(argv) > 4 else ["beauty", "albedo", "checker", "clay"]
    angles = [float(a) for a in argv[5].split(",")] if len(argv) > 5 else [0.0, 45.0, 90.0]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(asset_path))

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not meshes or not armatures:
        print("[RENDER] FAILED: need a mesh and an armature")
        return 1

    armature = armatures[0]
    bone = armature.data.bones.get(bone_name)
    if bone is None:
        print("[RENDER] FAILED: no bone '{0}'. Have: {1}".format(
            bone_name, ", ".join(sorted(b.name for b in armature.data.bones))[:400]))
        return 1
    centre = armature.matrix_world @ bone.head_local

    scene = bpy.context.scene
    engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        if candidate in engines:
            scene.render.engine = candidate
            break
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1000
    scene.render.image_settings.file_format = "PNG"
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 48

    setup_lights(centre, radius)
    out_dir.mkdir(parents=True, exist_ok=True)

    view_layer = scene.view_layers[0]
    for pass_name in passes:
        view_layer.material_override = None
        if pass_name == "checker":
            view_layer.material_override = checker_material()
        elif pass_name == "clay":
            view_layer.material_override = clay_material()
        elif pass_name == "albedo":
            albedo_mode(meshes)

        for angle in angles:
            place_camera(centre, radius, angle)
            path = out_dir / "{0}-{1}-{2:03.0f}.png".format(bone_name, pass_name, angle)
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            print("[RENDER] {0}".format(path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
