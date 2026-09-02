"""Normalize a static-prop authority into a UE5-ready FBX. Deterministic, headless.

The humanoid intake (`normalize_ue5.py`) cannot be reused for a prop, and not
because of a missing flag: it requires exactly one armature, derives its pivot
from that armature, and exports ARMATURE plus MESH. A chair has no skeleton to
pivot on and no bones to export. Everything else it does -- bake the scale and
origin into mesh DATA rather than leaving them on object transforms, rename
materials to the shipped convention, and point every material at the textures
that ship beside the FBX -- is exactly as necessary here, so it is done again
rather than adapted.

Two things are specific to props:

  Props arrive as many objects. The chair is 38 of them -- five casters, five
  spokes, seat, back, arms, and a dozen decorative seams and fasteners. The
  compiler downstream takes `max(meshes, key=polygons)` and would have
  compiled the seat cushion on its own, so they are joined into one mesh here.

  A prop has no height convention to inherit. A character is 2 m because the
  cohort is; a chair is whatever the recipe says, and the recipe has to say
  why.

Usage:
  blender -b --factory-startup --python scripts/blender/normalize_prop.py \
      -- <recipe.json> <out.fbx> <report.json> [texture-map.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

# The recipe is checked in and the assets it reads are not, so its paths are
# written as ${RAC_LEGACY_ROOT}/... and expanded here. A checked-in absolute
# path is a path that is correct on exactly one machine.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rac_env  # noqa: E402


def mesh_bounds(meshes):
    """World-space bounds from vertices, not obj.bound_box.

    bound_box is a cache. It survives data.transform() unchanged and will
    happily report pre-transform numbers, which reads as a scale bug that is
    not in the exported file.
    """
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for obj in meshes:
        matrix = obj.matrix_world
        for vert in obj.data.vertices:
            world = matrix @ vert.co
            for axis in range(3):
                lo[axis] = min(lo[axis], world[axis])
                hi[axis] = max(hi[axis], world[axis])
    return lo, hi


def import_authority(path: Path):
    suffix = path.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise SystemExit("unsupported authority format: {0}".format(suffix))


def join_meshes(meshes, name):
    """One object, so the compiler downstream does not pick a part of it."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    joined.data.name = name
    return joined


def bake_transform(matrix, obj):
    """Push the transform into vertex data and leave the object at identity.

    An unapplied object transform is what breaks FBX export scale and UE import
    scale at the same time, and it does it silently -- the viewport looks right
    the whole way.
    """
    obj.data.transform(matrix @ obj.matrix_world)
    obj.matrix_world = Matrix.Identity(4)
    obj.data.update()


def surface_constants(material):
    """Read the roughness and metallic the authority actually specified.

    They have to be read BEFORE the graph is rebuilt, and they are worth
    reading: the chair's six materials carry roughness from 0.68 to 0.95 and
    metallic 0.18 on the frame and 0.25 on the rust. Rebuilding without them
    leaves everything at the Principled default of 0.5 roughness and no metal,
    which renders the worn olive back as pale grey plastic.
    """
    values = {"roughness": 0.5, "metallic": 0.0}
    if not material.use_nodes:
        return values
    for node in material.node_tree.nodes:
        if node.type != "BSDF_PRINCIPLED":
            continue
        for key, socket in (("roughness", "Roughness"), ("metallic", "Metallic")):
            entry = node.inputs.get(socket)
            if entry is not None and not entry.is_linked:
                values[key] = round(float(entry.default_value), 4)
    return values


def rebuild_material(material, textures, constants, report):
    """Point one material at the files that ship beside the FBX.

    Rebuilt from scratch rather than edited. A material imported from a GLB
    carries whatever node graph the exporter emitted, including packed image
    datablocks with no file on disk, and an FBX export of that writes texture
    references that resolve to nothing.
    """
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = constants["roughness"]
    bsdf.inputs["Metallic"].default_value = constants["metallic"]
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    base = textures.get("BaseColor")
    if not base:
        report.setdefault("materials_without_texture", []).append(material.name)
        return
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(str(base), check_existing=True)
    node.image.colorspace_settings.name = "sRGB"
    tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
    for slot, socket_name in (("Roughness", "Roughness"), ("Metallic", "Metallic")):
        texture = textures.get(slot)
        if not texture:
            continue
        scalar = tree.nodes.new("ShaderNodeTexImage")
        scalar.name = "{0}_{1}".format(material.name, slot)
        scalar.image = bpy.data.images.load(str(texture), check_existing=True)
        scalar.image.colorspace_settings.name = "Non-Color"
        tree.links.new(scalar.outputs["Color"], bsdf.inputs[socket_name])


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    recipe_path, out_fbx, report_path = (Path(a) for a in argv[:3])
    recipe = rac_env.expand_tree(json.loads(recipe_path.read_text(encoding="utf-8-sig")))
    norm = recipe.get("normalize", {})

    material_textures = {}
    if len(argv) > 3 and argv[3]:
        material_textures = json.loads(
            Path(argv[3]).read_text(encoding="utf-8-sig"))
    elif recipe.get("material_textures"):
        material_textures = recipe["material_textures"]

    source = Path(recipe["source"]["authority_fbx"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    import_authority(source)

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        print("[NORMALIZE] FAILED: no mesh in {0}".format(source))
        return 1
    if [o for o in bpy.data.objects if o.type == "ARMATURE"]:
        print("[NORMALIZE] FAILED: this authority has an armature; it is not "
              "a static prop, so compile it through normalize_ue5.py")
        return 1

    lo, hi = mesh_bounds(meshes)
    report = {
        "asset_id": recipe["asset_id"],
        "asset_kind": recipe.get("kind", "static_prop"),
        "source_authority": str(source),
        "blender_version": bpy.app.version_string,
        "objects_joined": len(meshes),
        "before": {
            "height_m": round(hi.z - lo.z, 5),
            "bounds_min": [round(v, 5) for v in lo],
            "bounds_max": [round(v, 5) for v in hi],
        },
    }

    obj = join_meshes(meshes, norm.get("mesh_name", recipe["asset_id"]))

    scale = 1.0
    target_height = norm.get("target_height_m")
    if target_height:
        current = hi.z - lo.z
        if current <= 1e-6:
            print("[NORMALIZE] FAILED: source has zero height")
            return 1
        scale = target_height / current

    # A prop stands on the floor and turns about its own centre, so the origin
    # goes at the centre of its footprint with the lowest point on Z=0. Anything
    # else and every placement in the level needs a per-asset fudge.
    pivot = Vector(((lo.x + hi.x) * 0.5, (lo.y + hi.y) * 0.5, lo.z))
    translation = -(pivot * scale) if norm.get("recenter", True) else Vector()
    bake_transform(Matrix.Translation(translation) @ Matrix.Scale(scale, 4), obj)

    # Rotate about Z so the prop faces the way the cohort does. The characters
    # face -Y, and a chair that faces the other way looks like a placement
    # mistake in the level rather than a compile one.
    yaw = float(norm.get("yaw_degrees", 0.0) or 0.0)
    if yaw:
        bake_transform(Matrix.Rotation(__import__("math").radians(yaw), 4, "Z"), obj)
    report["yaw_degrees"] = yaw

    renames = norm.get("material_renames", {})
    for material in list(bpy.data.materials):
        if material.name in renames:
            material.name = renames[material.name]
    report["material_renames"] = renames

    # Accept a texture map keyed by either the source material name or the
    # renamed one. The rename happens above, so a recipe that keys its textures
    # by the name in the file -- the obvious thing to write -- would otherwise
    # fail with "material not found" naming a material the recipe never
    # mentioned. Both spellings mean the same thing and both should work.
    material_textures = {renames.get(name, name): textures
                         for name, textures in material_textures.items()}
    missing = [name for name in material_textures
               if bpy.data.materials.get(name) is None]
    if missing:
        print("[NORMALIZE] FAILED: materials {0} not found after rename; "
              "have {1}".format(missing, sorted(m.name for m in bpy.data.materials)))
        return 1
    surfaces = {name: surface_constants(bpy.data.materials[name])
                for name in material_textures}
    report["surface_constants"] = surfaces
    for name, textures in material_textures.items():
        rebuild_material(bpy.data.materials[name], textures, surfaces[name], report)

    lo2, hi2 = mesh_bounds([obj])
    report["uniform_scale_applied"] = round(scale, 6)
    report["translation_applied"] = [round(v, 5) for v in translation]
    report["after"] = {
        "height_m": round(hi2.z - lo2.z, 5),
        "bounds_min": [round(v, 5) for v in lo2],
        "bounds_max": [round(v, 5) for v in hi2],
        "verts": len(obj.data.vertices),
        "tris": sum(len(p.vertices) - 2 for p in obj.data.polygons),
        "materials": sorted(s.material.name for s in obj.material_slots if s.material),
    }

    out_fbx.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx), use_selection=True, add_leaf_bones=False,
        bake_anim=False, object_types={"MESH"}, mesh_smooth_type="FACE",
        path_mode="COPY", embed_textures=False)
    report["output_fbx"] = str(out_fbx)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[NORMALIZE] {0}: {1} objects joined, {2:.4f}x scale, "
          "{3:.3f} m tall, base on Z={4:.4f}".format(
              recipe["asset_id"], report["objects_joined"], scale,
              report["after"]["height_m"], lo2.z))
    print("[NORMALIZE] wrote {0}".format(out_fbx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
