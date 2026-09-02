"""Wire a retopologised mesh to its baked atlas and export the shippable FBX.

The retopo stage leaves the mesh carrying the graph that fed the bake, which
samples the OLD atlas through a UV layer that no longer exists. Exported as-is
the character renders white. This rebuilds each material as a plain Principled
BSDF reading the baked BaseColor, Normal, Roughness and Metallic passes.

AO is baked and shipped but deliberately NOT multiplied into Base Color here:
in UE5 it belongs in the ORM texture's red channel, where the engine can apply
it to indirect lighting only. Burning it into albedo double-darkens every
crevice as soon as a real light hits it.

Usage:
  blender -b --factory-startup --python \
      scripts/blender/apply_production_material.py \
      -- <retopo.fbx> <basecolor.png> <normal.png> <ao.png> \
         <roughness.png> <metallic.png> <out.fbx>
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if len(argv) >= 7:
        src, base, normal, _ao, roughness, metallic, out = (
            Path(a).resolve() for a in argv[:7])
    else:
        # Compatibility with retained character builds created before the
        # authored surface-channel bake existed.
        src, base, normal, _ao, out = (Path(a).resolve() for a in argv[:5])
        roughness = metallic = Path("__channel_not_baked__").resolve()

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(src))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        print("[PRODMAT] FAILED: no mesh in {0}".format(src))
        return 1
    obj = max(meshes, key=lambda o: len(o.data.polygons))

    for slot in obj.material_slots:
        material = slot.material
        if material is None:
            continue
        material.use_nodes = True
        tree = material.node_tree
        tree.nodes.clear()
        output = tree.nodes.new("ShaderNodeOutputMaterial")
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

        # Straight into Base Color. ShaderNodeMix socket indices moved between
        # Blender versions, and getting them wrong leaves Base Color
        # unconnected -- which renders the character pure white and looks like
        # a bake failure rather than a wiring one.
        colour = tree.nodes.new("ShaderNodeTexImage")
        colour.image = bpy.data.images.load(str(base), check_existing=True)
        colour.image.colorspace_settings.name = "sRGB"
        tree.links.new(colour.outputs["Color"], bsdf.inputs["Base Color"])

        # A character that could not be reduced has no normal map, because
        # there was no denser surface to capture one from.
        if normal.exists():
            normal_tex = tree.nodes.new("ShaderNodeTexImage")
            normal_tex.image = bpy.data.images.load(str(normal), check_existing=True)
            normal_tex.image.colorspace_settings.name = "Non-Color"
            normal_map = tree.nodes.new("ShaderNodeNormalMap")
            tree.links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
            tree.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
        if roughness.exists():
            rough_tex = tree.nodes.new("ShaderNodeTexImage")
            rough_tex.image = bpy.data.images.load(str(roughness), check_existing=True)
            rough_tex.image.colorspace_settings.name = "Non-Color"
            tree.links.new(rough_tex.outputs["Color"], bsdf.inputs["Roughness"])
        else:
            bsdf.inputs["Roughness"].default_value = 0.62
        if metallic.exists():
            metal_tex = tree.nodes.new("ShaderNodeTexImage")
            metal_tex.image = bpy.data.images.load(str(metallic), check_existing=True)
            metal_tex.image.colorspace_settings.name = "Non-Color"
            tree.links.new(metal_tex.outputs["Color"], bsdf.inputs["Metallic"])

    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    # COPY, not RELATIVE: the shipped FBX must carry its own .fbm beside it, or
    # the UE import silently lands on WorldGridMaterial.
    bpy.ops.export_scene.fbx(
        filepath=str(out), use_selection=True, path_mode="COPY",
        embed_textures=False, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y", axis_up="Z", apply_unit_scale=True,
        bake_anim=False, add_leaf_bones=False,
        object_types={"ARMATURE", "MESH"}, mesh_smooth_type="FACE")
    print("[PRODMAT] {0} tris={1}".format(
        out, sum(len(p.vertices) - 2 for p in obj.data.polygons)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
