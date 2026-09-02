"""Normalize an authority FBX into a UE5-ready FBX. Deterministic, headless.

Bakes uniform scale and origin correction into mesh and armature data rather
than leaving them on object transforms, because unapplied transforms are what
break shrinkwrap distance, FBX export, and UE import scale simultaneously.

Reads and writes only the paths it is given. Never touches the authority file.

Usage:
  blender -b --factory-startup --python scripts/blender/normalize_ue5.py \
      -- <recipe.json> <out.fbx> <report.json>
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

# The recipe is checked in and the assets it reads are not, so its paths are
# written as ${RAC_LEGACY_ROOT}/... and expanded here. A checked-in absolute
# path is a path that is correct on exactly one machine.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rac_env  # noqa: E402

DUPLICATE_SUFFIX = re.compile(r"\.\d{3}$")


def scene_objects():
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    return meshes, armatures


def mesh_bounds(meshes):
    """World-space bounds from vertices, not obj.bound_box.

    bound_box is a cache. It survives data.transform() unchanged and will
    happily report pre-transform numbers, which reads as a 100x scale bug that
    is not actually in the exported file.
    """
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for obj in meshes:
        mw = obj.matrix_world
        for vert in obj.data.vertices:
            world = mw @ vert.co
            for i in range(3):
                lo[i] = min(lo[i], world[i])
                hi[i] = max(hi[i], world[i])
    return lo, hi


def pivot_world(armature, meshes):
    """Where the character's floor-level origin currently sits.

    Prefer the root bone; fall back to the pelvis column at the lowest mesh
    point. UE expects the skeletal mesh origin between the feet.
    """
    lo, _ = mesh_bounds(meshes)
    bones = armature.data.bones
    for name in ("root", "pelvis"):
        bone = bones.get(name)
        if bone is None:
            continue
        world = armature.matrix_world @ bone.head_local
        return Vector((world.x, world.y, world.z if name == "root" else lo.z)), name
    return Vector((0.0, 0.0, lo.z)), "mesh_bounds"


def bake_transform(matrix, meshes, armature):
    """Apply `matrix` to object data, then reset every object transform.

    Only uniform scale and translation are passed here, so bone roll is
    preserved and heads/tails can be transformed directly.
    """
    bpy.ops.object.mode_set(mode="OBJECT")
    # Capture world matrices before unparenting. Clearing the parent changes
    # matrix_world, and reading it afterwards silently drops the armature's
    # 0.01 centimetre scale.
    world_before = {obj.name: obj.matrix_world.copy() for obj in meshes}
    for obj in meshes:
        obj.parent = None

    baked_meshes = set()
    for obj in meshes:
        final = matrix @ world_before[obj.name]
        if obj.data.name not in baked_meshes:
            obj.data.transform(final)
            baked_meshes.add(obj.data.name)
        obj.matrix_world = Matrix.Identity(4)

    arm_final = matrix @ armature.matrix_world
    # Armature.transform() rewrites the rest pose in one pass. Assigning
    # edit_bone.head/tail individually instead lets connected children drag
    # their parent's tail around mid-loop and silently shortens the chain.
    armature.data.transform(arm_final)
    armature.matrix_world = Matrix.Identity(4)

    for obj in meshes:
        obj.parent = armature
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_world = Matrix.Identity(4)


def build_material(mat, textures, report):
    """Rebuild a material's shading graph from declared texture files.

    The authority FBX files carry texture references that no longer resolve
    (fox-v4 points at a 'textures/packed/fox' that does not exist, which is why
    it renders untextured). Trusting the embedded reference means shipping a
    character with no albedo, so the declared path in the recipe wins.
    """
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (280, 0)
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    wired = []

    base_color = textures.get("BaseColor")
    if base_color:
        node = tree.nodes.new("ShaderNodeTexImage")
        node.location = (-360, 260)
        node.image = bpy.data.images.load(base_color, check_existing=True)
        node.image.colorspace_settings.name = "sRGB"
        tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
        wired.append("BaseColor")

    orm = textures.get("ORM")
    if orm:
        node = tree.nodes.new("ShaderNodeTexImage")
        node.location = (-360, -60)
        node.image = bpy.data.images.load(orm, check_existing=True)
        # ORM is data, not colour. sRGB here would skew roughness noticeably.
        node.image.colorspace_settings.name = "Non-Color"
        split = tree.nodes.new("ShaderNodeSeparateColor")
        split.location = (-90, -60)
        tree.links.new(node.outputs["Color"], split.inputs["Color"])
        # R=AO (consumed by UE, not by the Principled BSDF), G=Roughness, B=Metallic
        tree.links.new(split.outputs["Green"], bsdf.inputs["Roughness"])
        tree.links.new(split.outputs["Blue"], bsdf.inputs["Metallic"])
        wired.append("ORM")

    normal = textures.get("Normal")
    if normal:
        node = tree.nodes.new("ShaderNodeTexImage")
        node.location = (-360, -380)
        node.image = bpy.data.images.load(normal, check_existing=True)
        node.image.colorspace_settings.name = "Non-Color"
        nmap = tree.nodes.new("ShaderNodeNormalMap")
        nmap.location = (-90, -380)
        tree.links.new(node.outputs["Color"], nmap.inputs["Color"])
        tree.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
        wired.append("Normal")

    report.setdefault("materials_rebuilt", {})[mat.name] = wired


def flip_mesh_180(meshes, armature, report):
    """Rotate mesh geometry 180 degrees about Z and swap _l/_r weight groups.

    For an asset whose mesh faces +Y while its skeleton correctly faces -Y.
    Rotating the geometry alone would leave every vertex weighted to the bone
    on the opposite side, so the side-paired vertex groups must be renamed in
    the same pass. Centre chains (pelvis, spine, neck, head) sit on the X=0,
    Y~0 axis and need no remap.
    """
    # Spin about the character's own vertical axis, not the world origin.
    # An asset that stands off-centre would otherwise be translated to the far
    # side of the origin and end up further from its skeleton than it started.
    bones = armature.data.bones
    axis_bone = bones.get("root") or bones.get("pelvis")
    if axis_bone is not None:
        pivot = armature.matrix_world @ axis_bone.head_local
    else:
        lo, hi = mesh_bounds(meshes)
        pivot = (lo + hi) * 0.5
    offset = Vector((pivot.x, pivot.y, 0.0))
    spin_world = (
        Matrix.Translation(offset)
        @ Matrix.Rotation(math.pi, 4, "Z")
        @ Matrix.Translation(-offset)
    )
    report["flip_pivot_xy"] = [round(offset.x, 5), round(offset.y, 5)]
    flipped_data = set()
    swapped_groups = []

    for obj in meshes:
        if obj.data.name not in flipped_data:
            # data.transform() works in mesh-local space. These meshes are
            # parented to an armature carrying a 0.01 centimetre scale, so a
            # world-space pivot applied directly lands 100x off.
            local_spin = obj.matrix_world.inverted() @ spin_world @ obj.matrix_world
            obj.data.transform(local_spin)
            # A 180 degree rotation is orientation preserving, so winding and
            # normals stay valid; no flip_normals is needed or wanted.
            flipped_data.add(obj.data.name)

        # Rename through a temporary prefix so the two-way swap cannot collide.
        groups = {g.name: g for g in obj.vertex_groups}
        pairs = []
        for name in list(groups):
            if name.endswith("_l"):
                partner = name[:-2] + "_r"
                if partner in groups:
                    pairs.append((name, partner))
        for left, right in pairs:
            groups[left].name = "__swap__" + left
        for left, right in pairs:
            groups[right].name = left
            groups[left].name = right
            swapped_groups.append("{0}<->{1}".format(left, right))

    report["mesh_flipped_180_z"] = True
    report["vertex_groups_swapped"] = len(swapped_groups)
    report["vertex_group_swap_sample"] = sorted(swapped_groups)[:8]


def rename_materials(meshes, renames, report):
    applied = {}
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is None:
                continue
            target = renames.get(mat.name)
            if target is None:
                # Strip Blender's duplicate suffix even when unmapped; ".001"
                # becomes a permanent material slot name in UE otherwise.
                stripped = DUPLICATE_SUFFIX.sub("", mat.name)
                target = stripped if stripped != mat.name else None
            if target and target != mat.name:
                applied[mat.name] = target
                mat.name = target
    report["material_renames_applied"] = applied


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    recipe_path, out_fbx, report_path = (Path(a) for a in argv[:3])
    recipe = rac_env.expand_tree(json.loads(recipe_path.read_text(encoding="utf-8-sig")))
    norm = recipe.get("normalize", {})

    # The driver stages textures under their final shipped names next to where
    # the FBX will be written, and passes that map here, keyed by the material
    # each set belongs to. Materials are then built against the files we
    # actually ship, so the exported relative paths resolve.
    material_textures = {}
    if len(argv) > 3 and argv[3]:
        material_textures = json.loads(Path(argv[3]).read_text(encoding="utf-8-sig"))
    elif recipe.get("material_textures"):
        material_textures = recipe["material_textures"]
    elif norm.get("textured_material") and recipe.get("textures"):
        material_textures = {norm["textured_material"]: recipe["textures"]}

    source = Path(recipe["source"]["authority_fbx"])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    bpy.ops.import_scene.fbx(filepath=str(source))

    pre_report = {}
    meshes, armatures = scene_objects()
    if len(armatures) != 1:
        print("[NORMALIZE] FAILED: expected 1 armature, found {0}".format(len(armatures)))
        return 1
    armature = armatures[0]

    repair = recipe.get("repair", {})
    if repair.get("flip_mesh_180_z"):
        flip_mesh_180(meshes, armatures[0], pre_report)

    lo, hi = mesh_bounds(meshes)
    before = {
        "height_m": round(hi.z - lo.z, 5),
        "bounds_min": [round(v, 5) for v in lo],
        "bounds_max": [round(v, 5) for v in hi],
        "armature_scale": [round(v, 5) for v in armature.scale],
    }

    target_height = norm.get("target_height_m")
    scale = 1.0
    if target_height:
        current = hi.z - lo.z
        if current <= 1e-6:
            print("[NORMALIZE] FAILED: source has zero height")
            return 1
        scale = target_height / current

    pivot, pivot_source = pivot_world(armature, meshes)
    translation = Vector((0.0, 0.0, 0.0))
    if norm.get("recenter", True):
        # Scale about the world origin first, so the pivot moves with it.
        translation = -(pivot * scale)

    matrix = Matrix.Translation(translation) @ Matrix.Scale(scale, 4)
    bake_transform(matrix, meshes, armature)

    report = {
        "asset_id": recipe["asset_id"],
        "source_authority": str(source),
        "blender_version": bpy.app.version_string,
        "pivot_source": pivot_source,
        "uniform_scale_applied": round(scale, 6),
        "translation_applied": [round(v, 5) for v in translation],
        "before": before,
    }
    report.update(pre_report)
    rename_materials(meshes, norm.get("material_renames", {}), report)

    for material_name, texture_set in material_textures.items():
        target = bpy.data.materials.get(material_name)
        if target is None:
            print("[NORMALIZE] FAILED: material '{0}' not found after rename; "
                  "have {1}".format(
                      material_name, sorted(m.name for m in bpy.data.materials)))
            return 1
        build_material(target, texture_set, report)

    sk_name = norm.get("sk_mesh_name")
    if sk_name and len(meshes) == 1:
        meshes[0].data.name = sk_name
        meshes[0].name = sk_name

    # UE5 derives the root bone from the armature object node. Male and ninja
    # already ship an object named "root"; leave any other name alone rather
    # than colliding with an existing root bone.
    report["armature_object_name"] = armature.name
    report["ue5_root_bone_will_be"] = armature.name

    lo2, hi2 = mesh_bounds(meshes)
    report["after"] = {
        "height_m": round(hi2.z - lo2.z, 5),
        "bounds_min": [round(v, 5) for v in lo2],
        "bounds_max": [round(v, 5) for v in hi2],
        "armature_scale": [round(v, 5) for v in armature.scale],
    }

    out_fbx.parent.mkdir(parents=True, exist_ok=True)
    for obj in bpy.data.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature

    # These settings are not negotiable and are the usual source of
    # "why is my character 100x too large".
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx),
        use_selection=True,
        # RELATIVE, not COPY. COPY duplicates each atlas into a <name>.fbm
        # sidecar under its original name, which then imports into UE as a
        # second, differently-named set of textures. The driver stages the
        # shipped textures next to the FBX, so a relative reference resolves
        # and there is exactly one copy of each map.
        path_mode="RELATIVE",
        embed_textures=False,
        apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y",
        axis_up="Z",
        global_scale=1.0,
        apply_unit_scale=True,
        bake_anim=False,
        add_leaf_bones=False,
        object_types={"ARMATURE", "MESH"},
        use_armature_deform_only=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        mesh_smooth_type="FACE",
    )
    report["export_settings"] = {
        "path_mode": "RELATIVE",
        "embed_textures": False,
        "apply_scale_options": "FBX_SCALE_ALL",
        "axis_forward": "-Y",
        "axis_up": "Z",
        "apply_unit_scale": True,
        "bake_anim": False,
        "add_leaf_bones": False,
    }
    report["output_fbx"] = str(out_fbx)
    report["textures_used"] = material_textures

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        "[NORMALIZE] {0}: height {1:.3f}m -> {2:.3f}m, scale x{3:.5f}, "
        "origin shifted {4}".format(
            recipe["asset_id"],
            before["height_m"],
            report["after"]["height_m"],
            scale,
            [round(v, 4) for v in translation],
        )
    )
    print("[NORMALIZE] wrote {0}".format(out_fbx))
    return 0


if __name__ == "__main__":
    sys.exit(main())
