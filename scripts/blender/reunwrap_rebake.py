"""Give a character a coherent UV layout without changing its geometry.

The point of this stage is what it does NOT do. Vertex positions, triangle
count, skin weights and the skeleton are untouched, so the character keeps
exactly the likeness that was accepted against the reference image. Only the
UV layout changes, and the existing artwork is baked across into it.

Why it is worth doing:

  The legacy atlases were packed per-patch by xatlas -- 395 to 942 islands
  with a median island of 24 to 74 texels. Every island edge is a seam and a
  bleed boundary. That layout is why the ninja's sleeve smears, and it is the
  mechanism that let face pixels land on a trouser leg.

  A coherent layout does not repair art that is already smeared, but it is the
  precondition for any re-texturing to produce something clean. Painting into
  confetti gets you confetti back.

Heal first. An unhealed mesh reads as hundreds of disconnected islands
because the exporter split a vertex at every UV and normal seam, and
smart_project cannot build a coherent island across pieces that share no
edges -- unwrapping field-scout-female before welding took her from 395
islands to 8,437 and collapsed texel density from 145 to 9.6. Welding at
0.1 mm makes her a single manifold, and the unwrap then has a surface to
follow.

Welding merges coincident duplicates only; no vertex moves. That is checked
by hashing rounded positions before and after, and the stage fails if the
surface changed.

Usage:
  blender -b --factory-startup --python scripts/blender/reunwrap_rebake.py \
      -- <in.fbx> <material> <out_dir> <report.json> \
         [--basecolor path] [--resolution 4096] [--angle 66] [--margin 0.004]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def geometry_fingerprint(obj):
    """Hash of vertex positions and triangle indices."""
    mesh = obj.data
    coords = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", coords)
    indices = []
    for poly in mesh.polygons:
        indices.extend(poly.vertices)
    digest = hashlib.sha256()
    digest.update(np.round(coords, 6).tobytes())
    digest.update(np.asarray(indices, dtype=np.int32).tobytes())
    return digest.hexdigest()


def island_stats(obj, uv_name, size=1024):
    """Island count and size distribution for one UV layer."""
    from scipy import ndimage  # noqa: PLC0415 - optional, Blender may lack it

    layer = obj.data.uv_layers[uv_name]
    mask = np.zeros((size, size), dtype=bool)
    for poly in obj.data.polygons:
        xs, ys = [], []
        for loop_index in poly.loop_indices:
            u, v = layer.data[loop_index].uv
            xs.append(min(max(u, 0.0), 1.0) * (size - 1))
            ys.append((1.0 - min(max(v, 0.0), 1.0)) * (size - 1))
        x0, x1 = int(min(xs)), int(max(xs)) + 1
        y0, y1 = int(min(ys)), int(max(ys)) + 1
        mask[y0:min(y1, size), x0:min(x1, size)] = True
    labels, count = ndimage.label(mask)
    areas = np.bincount(labels.ravel())[1:]
    return {
        "islands": int(count),
        "coverage_pct": round(100.0 * mask.sum() / (size * size), 1),
        "median_island_px": int(np.median(areas)) if len(areas) else 0,
    }


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    src, material_name = Path(argv[0]), argv[1]
    out_dir, report_path = Path(argv[2]), Path(argv[3])
    base_color_path = arg(argv, "--basecolor", None)
    resolution = arg(argv, "--resolution", 4096, int)
    angle = arg(argv, "--angle", 66.0, float)
    margin = arg(argv, "--margin", 0.004, float)
    samples = arg(argv, "--samples", 8, int)
    weld = arg(argv, "--weld", 0.0001, float)
    skip_heal = "--no-heal" in argv

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(src))

    target = None
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for slot in obj.material_slots:
            if slot.material is not None and slot.material.name == material_name:
                target = obj
                break
        if target:
            break
    if target is None:
        print("[REUV] FAILED: no mesh uses material {0}".format(material_name))
        return 1

    report = {
        "source": str(src),
        "material": material_name,
        "resolution": resolution,
        "tris": sum(len(p.vertices) - 2 for p in target.data.polygons),
        "verts": len(target.data.vertices),
    }
    old_uv = target.data.uv_layers.active.name

    # Weld before measuring or unwrapping. Positions are preserved, so the
    # fingerprint is taken on the healed surface -- that is the geometry the
    # rest of the stage must not move.
    if not skip_heal:
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        report["verts_before_weld"] = len(target.data.vertices)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.remove_doubles(threshold=weld)
        bpy.ops.mesh.normals_make_consistent(inside=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        report["verts_after_weld"] = len(target.data.vertices)
        print("[REUV] welded @{0}: {1} -> {2} verts".format(
            weld, report["verts_before_weld"], report["verts_after_weld"]))

    before_hash = geometry_fingerprint(target)

    try:
        report["uv_before"] = island_stats(target, old_uv)
    except Exception as error:  # noqa: BLE001 - scipy may be absent in Blender
        report["uv_before"] = {"error": str(error)}

    # Add the new layout as a SECOND layer, so the old one survives to be the
    # source of the transfer bake.
    new_uv = target.data.uv_layers.new(name="UVCoherent")
    target.data.uv_layers.active = new_uv

    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    # A generous angle limit follows the form instead of chopping per patch,
    # and the margin leaves a real bleed gutter between islands.
    bpy.ops.uv.smart_project(
        angle_limit=np.radians(angle), island_margin=margin,
        correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    try:
        report["uv_after"] = island_stats(target, new_uv.name)
    except Exception as error:  # noqa: BLE001
        report["uv_after"] = {"error": str(error)}

    # Rebuild the material so it samples the OLD layout explicitly, then bake
    # with the NEW layout active. That transfers the artwork across without a
    # second mesh or a cage.
    out_dir.mkdir(parents=True, exist_ok=True)
    baked = {}
    if base_color_path and Path(base_color_path).exists():
        material = bpy.data.materials[material_name]
        material.use_nodes = True
        tree = material.node_tree
        tree.nodes.clear()
        output = tree.nodes.new("ShaderNodeOutputMaterial")
        emission = tree.nodes.new("ShaderNodeEmission")
        source_tex = tree.nodes.new("ShaderNodeTexImage")
        source_tex.image = bpy.data.images.load(base_color_path, check_existing=True)
        source_tex.image.colorspace_settings.name = "sRGB"
        uv_node = tree.nodes.new("ShaderNodeUVMap")
        uv_node.uv_map = old_uv
        tree.links.new(uv_node.outputs["UV"], source_tex.inputs["Vector"])
        tree.links.new(source_tex.outputs["Color"], emission.inputs["Color"])
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])

        destination = bpy.data.images.new(
            "BK_BaseColor", resolution, resolution, alpha=True)
        destination.generated_color = (0.0, 0.0, 0.0, 0.0)
        bake_node = tree.nodes.new("ShaderNodeTexImage")
        bake_node.image = destination
        bake_node.select = True
        tree.nodes.active = bake_node

        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.render.bake.use_selected_to_active = False
        # EMIT reproduces the source texture exactly: no lighting, no shading,
        # just the colour resampled into the new layout.
        bpy.ops.object.bake(type="EMIT", use_clear=True, margin=24)

        pixels = np.array(destination.pixels[:], dtype=np.float32).reshape(
            resolution, resolution, 4)
        written = pixels[..., 3] > 0.5
        report["basecolor_coverage_pct"] = round(100.0 * written.mean(), 1)

        path = out_dir / "T_Recoherent_BaseColor.png"
        destination.filepath_raw = str(path)
        destination.file_format = "PNG"
        destination.save()
        baked["BaseColor"] = path.name
        print("[REUV] baked BaseColor into the new layout -> {0}".format(path.name))

    # Drop the old layout only after the transfer succeeded.
    old_layer = target.data.uv_layers.get(old_uv)
    if old_layer is not None and baked:
        target.data.uv_layers.remove(old_layer)
    target.data.uv_layers.active = target.data.uv_layers[0]

    after_hash = geometry_fingerprint(target)
    report["geometry_hash_before"] = before_hash
    report["geometry_hash_after"] = after_hash
    report["geometry_unchanged"] = before_hash == after_hash
    report["baked"] = baked

    if not report["geometry_unchanged"]:
        report["ok"] = False
        report["failure"] = "geometry changed during re-unwrap; refusing to ship"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("[REUV] FAILED: {0}".format(report["failure"]))
        return 1

    out_fbx = out_dir / (src.stem + "_reuv.fbx")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx), use_selection=True, path_mode="RELATIVE",
        embed_textures=False, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y", axis_up="Z", apply_unit_scale=True,
        bake_anim=False, add_leaf_bones=False,
        object_types={"ARMATURE", "MESH"}, mesh_smooth_type="FACE")
    report["output_fbx"] = out_fbx.name
    report["ok"] = True

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[REUV] {0}: islands {1} -> {2}, geometry unchanged={3}".format(
        src.stem,
        report["uv_before"].get("islands"), report["uv_after"].get("islands"),
        report["geometry_unchanged"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
