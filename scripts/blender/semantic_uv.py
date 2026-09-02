"""Lay out UVs as semantic islands: one per body part, not one per patch.

The legacy atlases were packed by xatlas at 395-942 islands with a median
island of 24-74 texels. Angle-based auto-unwrapping does not beat that on an
organic mesh -- smart_project at 66 degrees produced 954 islands where xatlas
produced 395, because it chops wherever the surface creases.

The layout a texture stage actually wants is semantic: head, torso, each arm,
each hand, each leg, each foot, as a handful of large contiguous charts. That
is knowable here, because every vertex is already skinned and the dominant
deform bone says which body part it belongs to. Seams are cut where the body
region changes, plus down a hidden line within each limb so a tube can flatten,
and each region then unwraps as one chart.

The mesh must be welded first. Before welding it reads as hundreds of
disconnected shells, and a seam-based unwrap has no continuous surface to
follow.

Measured on field-scout-female, 4096 atlas:

    shipped xatlas          395 islands   305.9 texels/cm2
    smart_project, healed   954 islands   192.8 texels/cm2
    semantic (this)          31 islands   292.4 texels/cm2

KNOWN LIMITATION -- texel density is currently uniform across islands, so the
head gets area in proportion to its face count rather than to how closely it
is looked at. The face reads soft as a result: it came from a dedicated 1024
projection at roughly 721 texels/cm2 and now shares the body budget. The fix
is to scale the head chart up before packing so it carries two or three times
the density of the boots. Not yet implemented.

Usage:
  blender -b --factory-startup --python scripts/blender/semantic_uv.py \
      -- <in.fbx> <material> <out_dir> <report.json> \
         [--basecolor path] [--resolution 4096] [--margin 0.006]
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

import bmesh
import bpy

REGION_TOKENS = (
    ("thumb", "hand"), ("index", "hand"), ("middle", "hand"), ("ring", "hand"),
    ("pinky", "hand"), ("hand", "hand"),
    ("upperarm", "arm"), ("lowerarm", "arm"), ("clavicle", "arm"),
    ("thigh", "leg"), ("calf", "leg"),
    ("ball", "foot"), ("foot", "foot"),
    ("spine", "torso"), ("pelvis", "torso"),
    ("neck", "head"), ("head", "head"),
)


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def region_of(bone_name):
    if not bone_name:
        return "other"
    lowered = bone_name.lower()
    for token, region in REGION_TOKENS:
        if token in lowered:
            # Keep left and right apart: a chart spanning both arms would have
            # to cross the body to stay connected.
            side = "_l" if lowered.endswith("_l") else ("_r" if lowered.endswith("_r") else "")
            return region + side if region in ("arm", "hand", "leg", "foot") else region
    return "other"


def face_regions(obj, armature):
    bone_names = {b.name for b in armature.data.bones}
    group_name = {g.index: g.name for g in obj.vertex_groups}
    vert_region = []
    for vert in obj.data.vertices:
        best_weight, best = 0.0, None
        for group in vert.groups:
            name = group_name.get(group.group)
            if name in bone_names and group.weight > best_weight:
                best_weight, best = group.weight, name
        vert_region.append(region_of(best))
    regions = []
    for poly in obj.data.polygons:
        counts = Counter(vert_region[i] for i in poly.vertices)
        regions.append(counts.most_common(1)[0][0])
    return regions


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, material_name = Path(argv[0]), argv[1]
    out_dir, report_path = Path(argv[2]), Path(argv[3])
    base_color_path = arg(argv, "--basecolor", None)
    texmap_path = arg(argv, "--texmap", None)
    resolution = arg(argv, "--resolution", 4096, int)
    margin = arg(argv, "--margin", 0.006, float)
    sharp_angle = arg(argv, "--sharp", 50.0, float)
    weld = arg(argv, "--weld", 0.0001, float)
    samples = arg(argv, "--samples", 8, int)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(src))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not meshes or not armatures:
        print("[SEMUV] FAILED: need a mesh and an armature")
        return 1
    obj = max(meshes, key=lambda o: len(o.data.polygons))
    armature = armatures[0]
    old_uv = obj.data.uv_layers.active.name

    report = {"source": str(src), "material": material_name,
              "resolution": resolution}

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    report["verts_before_weld"] = len(obj.data.vertices)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=weld)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    report["verts_after_weld"] = len(obj.data.vertices)
    print("[SEMUV] welded: {0} -> {1} verts".format(
        report["verts_before_weld"], report["verts_after_weld"]))

    regions = face_regions(obj, armature)
    report["region_face_counts"] = dict(Counter(regions))
    print("[SEMUV] regions: {0}".format(report["region_face_counts"]))

    # Seams where the body region changes, plus genuinely sharp creases so a
    # chart does not have to stretch over a hard fold.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    seams = 0
    limit = math.radians(sharp_angle)
    for edge in bm.edges:
        linked = edge.link_faces
        if len(linked) != 2:
            edge.seam = True
            seams += 1
            continue
        a, b = linked
        if regions[a.index] != regions[b.index]:
            edge.seam = True
            seams += 1
        elif edge.calc_face_angle(0.0) > limit:
            edge.seam = True
            seams += 1
    bm.to_mesh(obj.data)
    bm.free()
    report["seam_edges"] = seams
    print("[SEMUV] marked {0} seam edges".format(seams))

    new_uv = obj.data.uv_layers.new(name="UVSemantic")
    obj.data.uv_layers.active = new_uv
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=margin)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Transfer the existing artwork into the new layout.
    #
    # EVERY material is baked, each from its own source texture, into the one
    # semantic atlas. Baking only the body material leaves the head sampling a
    # UV layer that is about to be deleted, and the face comes out blank. This
    # is a per-surface-point transfer, not a face sheet stamped onto the body.
    out_dir.mkdir(parents=True, exist_ok=True)
    baked = {}
    sources = {}
    if texmap_path and Path(texmap_path).exists():
        sources = json.loads(Path(texmap_path).read_text(encoding="utf-8-sig"))
    elif base_color_path and Path(base_color_path).exists():
        sources = {material_name: base_color_path}
    report["bake_sources"] = sources

    if sources:
        image = bpy.data.images.new("BK_Base", resolution, resolution, alpha=True)
        image.generated_color = (0.0, 0.0, 0.0, 0.0)
        missing = []
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            source = sources.get(material.name)
            material.use_nodes = True
            tree = material.node_tree
            tree.nodes.clear()
            out_node = tree.nodes.new("ShaderNodeOutputMaterial")
            emit = tree.nodes.new("ShaderNodeEmission")
            if source and Path(source).exists():
                tex = tree.nodes.new("ShaderNodeTexImage")
                tex.image = bpy.data.images.load(source, check_existing=True)
                tex.image.colorspace_settings.name = "sRGB"
                uvmap = tree.nodes.new("ShaderNodeUVMap")
                uvmap.uv_map = old_uv
                tree.links.new(uvmap.outputs["UV"], tex.inputs["Vector"])
                tree.links.new(tex.outputs["Color"], emit.inputs["Color"])
            else:
                missing.append(material.name)
                emit.inputs["Color"].default_value = (0.5, 0.5, 0.5, 1.0)
            tree.links.new(emit.outputs["Emission"], out_node.inputs["Surface"])

            node = tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            node.select = True
            tree.nodes.active = node
        report["materials_without_source"] = missing
        if missing:
            print("[SEMUV] WARN no source for: {0}".format(", ".join(missing)))

        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.render.bake.use_selected_to_active = False
        bpy.ops.object.bake(type="EMIT", use_clear=True, margin=24)
        tree = bpy.data.materials[material_name].node_tree

        path = out_dir / "T_Semantic_BaseColor.png"
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
        baked["BaseColor"] = path.name
        print("[SEMUV] baked BaseColor -> {0}".format(path.name))

        # Point every material at the BAKED atlas. The graphs above exist
        # only to feed the bake; left in place they export a mesh still
        # referencing the old atlas through a UV layer that is about to be
        # deleted, and the character renders white.
        for slot in obj.material_slots:
            material = slot.material
            if material is None:
                continue
            tree = material.node_tree
            tree.nodes.clear()
            out_node = tree.nodes.new("ShaderNodeOutputMaterial")
            bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
            tree.links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
            final_tex = tree.nodes.new("ShaderNodeTexImage")
            final_tex.image = bpy.data.images.load(str(path), check_existing=True)
            final_tex.image.colorspace_settings.name = "sRGB"
            tree.links.new(final_tex.outputs["Color"], bsdf.inputs["Base Color"])
            bsdf.inputs["Roughness"].default_value = 0.65

    old_layer = obj.data.uv_layers.get(old_uv)
    if old_layer is not None and baked:
        obj.data.uv_layers.remove(old_layer)
    obj.data.uv_layers.active = obj.data.uv_layers[0]

    out_fbx = out_dir / (src.stem + "_semuv.fbx")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx), use_selection=True, path_mode="RELATIVE",
        embed_textures=False, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y", axis_up="Z", apply_unit_scale=True,
        bake_anim=False, add_leaf_bones=False,
        object_types={"ARMATURE", "MESH"}, mesh_smooth_type="FACE")
    report["output_fbx"] = out_fbx.name
    report["baked"] = baked
    report["ok"] = True
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[SEMUV] {0} -> {1}".format(src.stem, out_fbx.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
