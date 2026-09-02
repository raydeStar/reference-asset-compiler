"""Bake ambient occlusion on a character's existing UVs and pack an ORM map.

Retopology is not available for these assets: they are multi-shell generated
meshes (1,915 disconnected pieces before voxel remeshing, 19 after) and
QuadriFlow refuses anything that is not a single manifold component. Blender's
Decimate is forbidden by the brief, and rightly so. So the low-poly target a
normal-map bake would need does not exist.

What can be produced honestly on the existing topology is the rest of the PBR
set:

  AO         Baked from the real geometry. This is genuine occlusion
             information the assets did not have.
  Roughness  Carried over from any existing ORM, otherwise derived from
             albedo luminance: darker cloth reads rougher than bright
             highlights, which is a reasonable stylised default and far
             better than a flat 0.5.
  Metallic   Zero unless an existing ORM says otherwise. Nothing in this
             cohort is metal.

Packed as R=AO, G=Roughness, B=Metallic, which is what the UE5 material
instance expects.

Usage:
  blender -b --factory-startup --python scripts/blender/bake_pbr.py \
      -- <asset.fbx> <material> <out_orm.png> <report.json> \
         [--basecolor path] [--existing-orm path] [--resolution 2048] \
         [--samples 64]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
import numpy as np


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    src = Path(argv[0])
    material_name = argv[1]
    out_orm = Path(argv[2])
    report_path = Path(argv[3])
    base_color_path = arg(argv, "--basecolor", None)
    existing_orm_path = arg(argv, "--existing-orm", None)
    resolution = arg(argv, "--resolution", 2048, int)
    samples = arg(argv, "--samples", 64, int)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(src))

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes:
        print("[PBR] FAILED: no mesh")
        return 1

    target = None
    for obj in meshes:
        for slot in obj.material_slots:
            if slot.material is not None and slot.material.name == material_name:
                target = obj
                break
        if target:
            break
    if target is None:
        print("[PBR] FAILED: material {0} not found; have {1}".format(
            material_name, sorted(m.name for m in bpy.data.materials)))
        return 1

    report = {
        "asset": str(src),
        "material": material_name,
        "resolution": resolution,
        "samples": samples,
    }

    # Bind the bake target to THIS material only. Other materials still cast
    # occlusion -- AO is ray traced against all geometry -- but only faces
    # using this material write into the image. Binding it everywhere lets a
    # second material with its own full-atlas UV projection overwrite the map.
    ao_image = bpy.data.images.new(
        "BK_AO", resolution, resolution, alpha=True, float_buffer=False)
    ao_image.generated_color = (1.0, 1.0, 1.0, 0.0)
    ao_image.colorspace_settings.name = "Non-Color"

    bake_nodes = []
    for slot in target.material_slots:
        mat = slot.material
        if mat is None or mat.name != material_name:
            continue
        mat.use_nodes = True
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = ao_image
        node.select = True
        mat.node_tree.nodes.active = node
        bake_nodes.append((mat, node))
    if not bake_nodes:
        print("[PBR] FAILED: no slot on {0} uses {1}".format(target.name, material_name))
        return 1

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.margin = 16

    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target

    try:
        bpy.ops.object.bake(type="AO", use_clear=True, margin=32)
    except RuntimeError as error:
        print("[PBR] FAILED: AO bake: {0}".format(error))
        return 1

    ao = np.array(ao_image.pixels[:], dtype=np.float32).reshape(resolution, resolution, 4)
    ao_channel = ao[..., 0]

    # Fill the gutters. The bake margin covers the first 16 texels past each
    # island edge, but the rest of the atlas stays at zero. Left black, those
    # texels average into the lower mips and darken the character at distance.
    # Unwritten texels have alpha 0, which distinguishes them from a genuine
    # crevice that legitimately bakes near zero.
    # Alpha is not a reliable "was this baked" flag: use_clear writes an
    # opaque black, so alpha comes back 1 everywhere. An exactly-zero RGB is
    # the real signal -- the 32 texel bake margin has already filled the band
    # around each island, so anything still at zero is gutter, not a crevice.
    written = ao[..., :3].max(axis=2) > 1e-5
    gutter = int((~written).sum())
    if gutter and written.any():
        fill = float(np.median(ao_channel[written]))
        ao_channel = np.where(written, ao_channel, fill)
        report["gutter_texels_filled"] = gutter
        report["gutter_fill_value"] = round(fill, 4)

    report["ao_mean"] = round(float(ao_channel[written].mean()), 4) if written.any() else 0.0
    report["ao_min"] = round(float(ao_channel[written].min()), 4) if written.any() else 0.0
    report["ao_coverage_pct"] = round(100.0 * written.mean(), 1)

    for mat, node in bake_nodes:
        mat.node_tree.nodes.remove(node)

    # Roughness and metallic.
    rough = None
    metal = None
    if existing_orm_path and Path(existing_orm_path).exists():
        existing = bpy.data.images.load(existing_orm_path, check_existing=True)
        width, height = existing.size
        pixels = np.array(existing.pixels[:], dtype=np.float32).reshape(height, width, 4)
        if (height, width) != (resolution, resolution):
            ys = (np.linspace(0, height - 1, resolution)).astype(int)
            xs = (np.linspace(0, width - 1, resolution)).astype(int)
            pixels = pixels[np.ix_(ys, xs)]
        rough = pixels[..., 1]
        metal = pixels[..., 2]
        report["roughness_source"] = "existing ORM green channel"
        report["metallic_source"] = "existing ORM blue channel"
    elif base_color_path and Path(base_color_path).exists():
        albedo = bpy.data.images.load(base_color_path, check_existing=True)
        width, height = albedo.size
        pixels = np.array(albedo.pixels[:], dtype=np.float32).reshape(height, width, 4)
        if (height, width) != (resolution, resolution):
            ys = (np.linspace(0, height - 1, resolution)).astype(int)
            xs = (np.linspace(0, width - 1, resolution)).astype(int)
            pixels = pixels[np.ix_(ys, xs)]
        luma = (
            0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]
        )
        # Bright surfaces read a little glossier, dark cloth a little rougher.
        # Kept in a narrow band so it reads as material variation, not noise.
        rough = np.clip(0.86 - 0.34 * np.sqrt(np.clip(luma, 0.0, 1.0)), 0.35, 0.92)
        metal = np.zeros_like(rough)
        report["roughness_source"] = "derived from albedo luminance"
        report["metallic_source"] = "constant 0 (nothing in this cohort is metal)"
    else:
        rough = np.full((resolution, resolution), 0.72, dtype=np.float32)
        metal = np.zeros_like(rough)
        report["roughness_source"] = "constant 0.72"
        report["metallic_source"] = "constant 0"

    orm = np.zeros((resolution, resolution, 4), dtype=np.float32)
    orm[..., 0] = ao_channel
    orm[..., 1] = rough
    orm[..., 2] = metal
    orm[..., 3] = 1.0

    out_image = bpy.data.images.new(
        "ORM", resolution, resolution, alpha=False, float_buffer=False)
    out_image.colorspace_settings.name = "Non-Color"
    out_image.pixels = orm.reshape(-1).tolist()
    out_orm.parent.mkdir(parents=True, exist_ok=True)
    out_image.filepath_raw = str(out_orm)
    out_image.file_format = "PNG"
    out_image.save()

    report["output"] = str(out_orm)
    report["roughness_mean"] = round(float(rough.mean()), 4)
    report["ok"] = True
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[PBR] {0} / {1}: AO mean {2:.3f}, roughness {3} -> {4}".format(
        src.stem, material_name, report["ao_mean"],
        report["roughness_source"], out_orm.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
