"""Give the production mesh's body and head their real metalness.

calibrate_pbr.py writes metallic and roughness as two greyscale maps; obj_to_glb.py wired every such map as a
packed glTF metallic-roughness texture (green roughness, blue metallic), so the roughness map, wired last, set
metallic too: the whole body and head were 47-99% metallic. Plates read as chrome, cloth and skin as lacquer.
(obj_to_glb.py now wires separate maps separately; this repairs meshes packed before that.)

For each material named here, the packed texture is rebuilt from the calibrated pair (green roughness, blue
metallic) after checking that the pair's roughness map is the one already on the material, texel for texel. A body
packed correctly to begin with carries the exporter's own name for the packed map (raider-body_metallic); when the
named image is absent, an image named after the same stem is taken instead, and the rebuilt map keeps the name
given here, so the names downstream (tone_metal.py, the UE import's texture files) do not change.

  $B -b --factory-startup --python fix_pbr_maps.py -- <production.glb> <out.glb> <image_name>=<maps_dir>/<stem> ...
"""
import bpy
import json
import os
import sys

import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
src, out, pairs = a[0], a[1], [p.split("=", 1) for p in a[2:]]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)


def pixels(img):
    px = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(img.size[1], img.size[0], 4)


report = {}
for image_name, stem in pairs:
    images = [n for m in bpy.data.materials if m.node_tree for n in m.node_tree.nodes
              if n.type == 'TEX_IMAGE' and n.image]
    node = next((n for n in images if n.image.name == image_name), None)
    if node is None:
        prefix = os.path.basename(stem) + "_"
        node = next((n for n in images if n.image.name.startswith(prefix)), None)
    if node is None:
        raise SystemExit(f"no material uses image {image_name}")
    report.setdefault("matched", {})[image_name] = node.image.name
    cur = pixels(node.image)
    rough = pixels(bpy.data.images.load(stem + "_roughness.png"))
    metal = pixels(bpy.data.images.load(stem + "_metallic.png"))
    if rough.shape != cur.shape:
        raise SystemExit(f"{image_name}: map size {rough.shape[:2]} is not the material's {cur.shape[:2]}")
    diff = float(np.abs(rough[..., 1] - cur[..., 1]).mean())
    if diff > 0.01:
        raise SystemExit(f"{image_name}: {stem}_roughness.png is not this material's roughness (mean diff {diff:.3f})")
    packed = np.zeros_like(cur)
    packed[..., 0] = 1.0                       # unused by glTF metallic-roughness; white keeps any occlusion read neutral
    packed[..., 1] = rough[..., 1]
    packed[..., 2] = metal[..., 0]
    packed[..., 3] = 1.0
    path = os.path.join(os.path.dirname(out), os.path.splitext(os.path.basename(out))[0] + "-" + image_name + ".png")
    img = bpy.data.images.new(image_name + "-mr", cur.shape[1], cur.shape[0], alpha=False)
    img.colorspace_settings.name = 'Non-Color'
    img.pixels.foreach_set(packed.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    fresh = bpy.data.images.load(path)      # a loaded file is what the exporter embeds
    fresh.colorspace_settings.name = 'Non-Color'
    node.image = fresh
    report[image_name] = {"maps": stem, "roughness_match_mean_diff": round(diff, 5),
                          "metallic_before_mean": round(float(cur[..., 2].mean()), 3),
                          "metallic_after_mean": round(float(packed[..., 2].mean()), 3),
                          "metallic_after_texels_over_half": round(float((packed[..., 2] > 0.5).mean()), 4)}
    print("PBR", image_name, report[image_name])
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB')
side = json.load(open(src + ".json")) if os.path.exists(src + ".json") else {}
side.update({"pbr_fix": report, "pbr_fix_source": src})
json.dump(side, open(out + ".json", "w"), indent=2)
print("PBR_FIX_OK")
