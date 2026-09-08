"""Composite a head-only Hunyuan paint into a body atlas that lives on a different UV layout.

The body mesh was painted once at full-body scale, so the head received about
fifty pixels of each 512 view. A second paint of the same head faces with the
same UVs fills the views with the head. This script brings that head paint onto
the body's repacked UV layout by CPU emission bake and blends it over the body
maps inside a geometry-derived head region with a short feather band at the
neck cut.

No vertex moves, no UV changes, no new artwork: every output texel is either a
body texel, a head-paint texel, or a linear blend of the two inside the band.

Usage (Blender -b --factory-startup --python-exit-code 1 --python ... --):
  composite_head_paint.py <config.json> <output-dir>

config = {
  "body_authority": ".../repacked-face-v006/uv-authority.blend",   # layout of the body maps
  "paint_authority": ".../uv-v001/uv-authority.blend",             # layout the head paint was baked on
  "paint_uv_layer": "UV_RAC_AI_Paint",
  "body_maps": {"BaseColor": ..., "Metallic": ..., "Roughness": ...},
  "head_maps": {"BaseColor": ..., "Metallic": ..., "Roughness": ...},
  "z_cut": 0.775, "feather": 0.035, "resolution": 4096, "bake_margin_pixels": 8,
  "mask_dilate_px": 3,
  "hashes": {<key>: sha256 for every path above}
}
"""
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fingerprint(obj):
    return hashlib.sha256(repr(([tuple(v.co) for v in obj.data.vertices],
                               [tuple(p.vertices) for p in obj.data.polygons])).encode()).hexdigest()


def single_mesh():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Expected one isolated mesh in the UV authority")
    return meshes[0]


def load_pixels(image):
    n = image.size[0]
    px = np.empty(n * n * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    return px.reshape(n, n, 4)


def save_pixels(name, rgb, path, colorspace):
    size = rgb.shape[0]
    image = bpy.data.images.new(name, width=size, height=size, alpha=False)
    image.colorspace_settings.name = colorspace
    px = np.concatenate([rgb, np.ones((size, size, 1), dtype=np.float32)], axis=2)
    image.pixels.foreach_set(px.astype(np.float32).ravel())
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    return image


def raster_weights(obj, layer_name, z_cut, feather, size):
    """Rasterize a per-polygon head weight (0 body .. 1 head) into UV space."""
    weights = np.zeros((size, size), dtype=np.float32)
    layer = obj.data.uv_layers[layer_name]
    mesh = obj.data
    for poly in mesh.polygons:
        zmin = min(mesh.vertices[v].co.z for v in poly.vertices)
        if zmin <= z_cut:
            continue
        w = min(1.0, (zmin - z_cut) / feather) if feather > 0 else 1.0
        pts = [layer.data[loop].uv for loop in poly.loop_indices]
        xs = np.array([p.x * size for p in pts])
        ys = np.array([p.y * size for p in pts])
        y0 = max(0, int(np.floor(ys.min())))
        y1 = min(size - 1, int(np.ceil(ys.max())))
        count = len(pts)
        for y in range(y0, y1 + 1):
            yc = y + 0.5
            nodes = []
            for i in range(count):
                xa, ya = xs[i], ys[i]
                xb, yb = xs[(i + 1) % count], ys[(i + 1) % count]
                if (ya <= yc < yb) or (yb <= yc < ya):
                    nodes.append(xa + (yc - ya) * (xb - xa) / (yb - ya))
            nodes.sort()
            for a, b in zip(nodes[0::2], nodes[1::2]):
                xa, xb = max(0, int(np.floor(a))), min(size - 1, int(np.ceil(b)))
                weights[y, xa:xb + 1] = np.maximum(weights[y, xa:xb + 1], w)
    return weights


def dilate(mask, px):
    out = mask.copy()
    for _ in range(px):
        shifted = [np.roll(out, s, axis=a) for a in (0, 1) for s in (1, -1)]
        out = np.maximum.reduce([out, *shifted])
    return out


def bake_channel(obj, material, source_layer, image_path, colorspace, size, margin):
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    emit = tree.nodes.new("ShaderNodeEmission")
    uvmap = tree.nodes.new("ShaderNodeUVMap")
    uvmap.uv_map = source_layer
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(Path(image_path).resolve()), check_existing=False)
    tex.image.colorspace_settings.name = colorspace
    tree.links.new(uvmap.outputs["UV"], tex.inputs["Vector"])
    tree.links.new(tex.outputs["Color"], emit.inputs["Color"])
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    dest = bpy.data.images.new("Transport", width=size, height=size, alpha=False)
    dest.colorspace_settings.name = colorspace
    target = tree.nodes.new("ShaderNodeTexImage")
    target.image = dest
    tree.nodes.active = target
    bpy.ops.object.bake(type="EMIT", use_clear=True, margin=margin)
    return dest


def main():
    config_path, output = [Path(x).resolve() for x in sys.argv[sys.argv.index("--") + 1:]]
    config = json.loads(config_path.read_text())
    if output.exists():
        raise RuntimeError("Composite output must be a fresh directory")
    inputs = {"body_authority": config["body_authority"], "paint_authority": config["paint_authority"],
              **{"body_" + k: v for k, v in config["body_maps"].items()},
              **{"head_" + k: v for k, v in config["head_maps"].items()}}
    for key, path in inputs.items():
        if sha(path) != config["hashes"][key]:
            raise RuntimeError("Changed pinned input: " + key)
    size = int(config["resolution"])
    margin = int(config["bake_margin_pixels"])

    # 1. Read the paint-layout UVs from the paint authority (same topology).
    bpy.ops.wm.open_mainfile(filepath=config["paint_authority"])
    paint_obj = single_mesh()
    paint_fp = fingerprint(paint_obj)
    paint_layer = paint_obj.data.uv_layers[config["paint_uv_layer"]]
    paint_uv = np.empty(len(paint_obj.data.loops) * 2, dtype=np.float32)
    paint_layer.data.foreach_get("uv", paint_uv)

    # 2. Open the body authority and add the paint layout as a second layer.
    bpy.ops.wm.open_mainfile(filepath=config["body_authority"])
    obj = single_mesh()
    if fingerprint(obj) != paint_fp:
        raise RuntimeError("Body and paint authorities are not the same geometry/face order")
    if len(obj.data.loops) * 2 != len(paint_uv):
        raise RuntimeError("Loop count differs between authorities")
    body_layer_name = obj.data.uv_layers.active.name
    src_layer = obj.data.uv_layers.new(name="UV_RAC_HeadPaintSource", do_init=False)
    src_layer.data.foreach_set("uv", paint_uv)
    obj.data.uv_layers.active = obj.data.uv_layers[body_layer_name]
    obj.data.uv_layers[body_layer_name].active_render = True

    output.mkdir(parents=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.render.bake.use_selected_to_active = False
    obj.data.materials.clear()
    material = bpy.data.materials.new("HeadTransport")
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.material_index = 0

    # 3. Bake each head channel from the paint layout onto the body layout.
    transported = {}
    for channel, path in config["head_maps"].items():
        colorspace = "sRGB" if channel == "BaseColor" else "Non-Color"
        dest = bake_channel(obj, material, "UV_RAC_HeadPaintSource", path, colorspace, size, margin)
        dest.filepath_raw = str(output / ("head-on-body-" + channel + ".png"))
        dest.file_format = "PNG"
        dest.save()
        transported[channel] = load_pixels(dest)[..., :3]

    # 4. Head weights in the body layout, then blend.
    weights = raster_weights(obj, body_layer_name, float(config["z_cut"]), float(config["feather"]), size)
    hard = dilate((weights > 0).astype(np.float32), int(config["mask_dilate_px"]))
    weights = np.where((weights == 0) & (hard > 0), 1.0, weights)
    stats = {"head_texels": int((weights > 0).sum()),
             "band_texels": int(((weights > 0) & (weights < 1)).sum()),
             "atlas_fraction": float((weights > 0).mean())}
    save_pixels("HeadWeights", np.repeat(weights[..., None], 3, axis=2), output / "head-weights.png", "Non-Color")

    outputs = {}
    for channel, body_path in config["body_maps"].items():
        colorspace = "sRGB" if channel == "BaseColor" else "Non-Color"
        body_img = bpy.data.images.load(str(Path(body_path).resolve()), check_existing=False)
        body_img.colorspace_settings.name = colorspace
        if body_img.size[0] != size:
            raise RuntimeError("Body map resolution must equal the composite resolution")
        body = load_pixels(body_img)[..., :3]
        head = transported[channel]
        w = weights[..., None]
        blended = body * (1.0 - w) + head * w
        save_pixels("Composite_" + channel, blended, output / (channel + ".png"), colorspace)
        outputs[channel] = str(output / (channel + ".png"))
        stats["changed_fraction_" + channel] = float((np.abs(blended - body).max(axis=2) > (1.0 / 255)).mean())

    # 5. Save an authority copy on the body layout only (unchanged UVs) for packaging.
    obj.data.uv_layers.remove(obj.data.uv_layers["UV_RAC_HeadPaintSource"])
    if fingerprint(obj) != paint_fp:
        raise RuntimeError("Compositing changed geometry")
    authority = output / "uv-authority.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(authority))
    report = {"schema": "reference-asset-compiler.head-paint-composite.v1",
              "config": str(config_path), "config_sha256": sha(config_path), "input_hashes": config["hashes"],
              "geometry_hash": paint_fp, "body_uv_layer": body_layer_name,
              "paint_uv_layer": config["paint_uv_layer"],
              "z_cut": config["z_cut"], "feather": config["feather"], "resolution": size,
              "operation": "CPU emission transport of head paint onto the body layout; linear blend inside "
                           "the geometry-derived head region; body texels outside it are byte-preserved",
              "stats": stats,
              "outputs": {str(p): sha(p) for p in [authority, *[Path(v) for v in outputs.values()]]},
              "production_ready": False}
    (output / "composite.json").write_text(json.dumps(report, indent=2) + "\n")
    print("HEAD_COMPOSITE_OK", json.dumps(stats))


if __name__ == "__main__":
    main()
