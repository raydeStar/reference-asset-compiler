"""Bake the maps a hard-surface painter needs, off the part's own geometry.

    blender -b --factory-startup --python scripts/blender/bake_surface_maps.py -- source maps.npz report.json --textures recipe.json
    rac run-stage bake-surface-maps --source part.glb --textures recipe.json --output maps.npz --report maps.json

For every texel of UV0 this records, in the part's own space and in metres:

    valid   whether the texel lies on the surface
    pos     where it is                       nrm    which way it faces
    ao      how open it is at 30 cm, 12 mm and 6 cm (wide shadowing, crevices, and the scale edges are judged at)
    bev     a tangent-space normal with every edge rounded to 3 mm, and how far an 11 mm rounding bends it (an edge mask)
    cls     what it is made of: the face attribute named by the recipe if the mesh has one, else its material slot

A mesh that carries the optional annotations `axisv` (grain direction per face), `rnd` (1 on tubes and domes)
and `dome` (0 at a rivet's foot to 1 at its crown, per vertex) has them baked too; the painter works without
them. Small loose parts that bulge (rivet and bolt heads) are listed as fasteners, where rain picks rust up.

Nothing is unwrapped or moved here. UV0 must already be unique and inside 0..1, and the mesh should be
triangulated the way it will ship, so the baked tangent space is the consumer's. The maps are in Blender's
axes (Z up) whatever the source file's were.

The recipe (schema rac.surface-maps-recipe.v1): source_sha256; resolution (64..4096); optional object (a
mesh object's name, for a .blend holding several), class_attribute (default "cls"), samples (1 = full
quality; less for a quick look), fasteners (false to list none).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np

RECIPE_SCHEMA = "rac.surface-maps-recipe.v1"
MAPS_SCHEMA = "rac.surface-maps.v1"
ANNOTATIONS = ("axisv", "rnd", "dome")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(source, wanted):
    """The part as one mesh object, a copy: the source file is never written."""
    if source.suffix.lower() == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source.resolve()))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(source.resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and (wanted is None or o.name == wanted)]
    if not meshes:
        raise ValueError("No mesh object to bake" + (f" named {wanted!r}" if wanted else ""))
    bpy.ops.object.select_all(action="DESELECT")
    copies = []
    for obj in meshes:
        copy = obj.copy()
        copy.data = obj.data.copy()
        bpy.context.scene.collection.objects.link(copy)
        copies.append(copy)
    for obj in copies:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    if len(copies) > 1:
        bpy.ops.object.join()
    part = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for obj in list(bpy.context.scene.objects):
        if obj is not part:
            obj.hide_render = True                 # nothing else may shadow the part
    return part


def classes(mesh, attribute):
    """Per-face class numbers and their names: the mesh's own attribute if it has one, else material slots."""
    layer = mesh.attributes.get(attribute)
    if layer is not None and layer.domain == "FACE":
        values = np.empty(len(mesh.polygons), np.int32)
        layer.data.foreach_get("value", values)
        names = [str(i) for i in range(int(values.max()) + 1)]
        source = f"face attribute {attribute}"
    else:
        values = np.empty(len(mesh.polygons), np.int32)
        mesh.polygons.foreach_get("material_index", values)
        names = [slot.name if slot else f"slot {i}" for i, slot in enumerate(mesh.materials)] or ["slot 0"]
        source = "material slots"
    if values.max() > 62:
        raise ValueError("More than 63 classes; one atlas is not that many materials")
    held = mesh.attributes.get("rac_class") or mesh.attributes.new("rac_class", "INT", "FACE")
    held.data.foreach_set("value", values)
    return names, source


def fasteners(mesh):
    """Small loose parts that bulge: [x, y, z, nx, ny, nz, radius] each, where rain picks rust up."""
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    seen, found = set(), []
    for start in bm.faces:
        if start.index in seen:
            continue
        stack, island = [start], []
        seen.add(start.index)
        while stack:
            face = stack.pop()
            island.append(face)
            for edge in face.edges:
                for other in edge.link_faces:
                    if other.index not in seen:
                        seen.add(other.index)
                        stack.append(other)
        points = np.array([v.co[:] for v in {v for f in island for v in f.verts}])
        if len(island) < 4 or np.linalg.norm(points.max(0) - points.min(0)) > .07:
            continue
        areas = np.array([f.calc_area() for f in island])
        normals = np.array([f.normal[:] for f in island])
        mean = (normals * areas[:, None]).sum(0) / max(areas.sum(), 1e-12)
        centre = points.mean(0)                                     # a head is a few millimetres tall: close enough to its seat
        if np.linalg.norm(mean) >= .97:                             # flat: a small plate, not a head
            continue
        if np.linalg.norm(mean) > .15:                              # an open dome: it faces the way its normals lean
            axes = [mean / np.linalg.norm(mean)]
        else:                                                       # a closed washer or bolt head: it sits on its flattest side,
            thin = np.linalg.eigh(np.cov((points - centre).T))[1][:, 0]     # and either face may be the one that shows
            axes = [thin, -thin]
        for axis in axes:
            radial = (points - centre) - np.outer((points - centre) @ axis, axis)
            found.append([*centre, *axis, float(np.linalg.norm(radial, axis=1).max())])
    bm.free()
    return found


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    for name in ("source", "output", "report"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--textures", type=Path, required=True, help="the surface-maps recipe")
    args = parser.parse_args(argv)
    began = time.time()
    recipe = json.loads(args.textures.read_text(encoding="utf-8-sig"))
    if recipe.get("schema") != RECIPE_SCHEMA or recipe.get("source_sha256") != sha(args.source):
        raise ValueError("The recipe must be a surface-maps recipe bound to this source")
    if args.output.exists() or args.report.exists() or len({p.resolve() for p in (args.source, args.output, args.report, args.textures)}) != 4:
        raise ValueError("Keep earlier bakes; choose distinct new paths")
    res = int(recipe.get("resolution", 2048))
    quality = float(recipe.get("samples", 1))
    if not 64 <= res <= 4096 or not .05 <= quality <= 4:
        raise ValueError("resolution is 64..4096 and samples 0.05..4")

    part = load(args.source, recipe.get("object"))
    mesh = part.data
    if not mesh.uv_layers:
        raise ValueError("The part has no UV0")
    names, class_source = classes(mesh, recipe.get("class_attribute", "cls"))
    annotations = [name for name in ANNOTATIONS if mesh.attributes.get(name) is not None]
    heads = fasteners(mesh) if recipe.get("fasteners", True) else []

    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    loops = np.empty(count * 3, np.int32)
    mesh.loop_triangles.foreach_get("loops", loops)
    loops = loops.reshape(-1, 3)
    area = np.empty(count, np.float32)
    mesh.loop_triangles.foreach_get("area", area)
    uv = np.empty(len(mesh.loops) * 2, np.float32)
    mesh.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    if uv.min() < -1e-4 or uv.max() > 1 + 1e-4:
        raise ValueError("UV0 leaves the 0..1 square; a tiled layout needs its own unique atlas first")
    a, b, c = uv[loops[:, 0]], uv[loops[:, 1]], uv[loops[:, 2]]
    uv_area = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])) / 2
    ok = (area > 1e-10) & (uv_area > 1e-14)
    density = res * np.sqrt(uv_area[ok] / area[ok])
    order = np.argsort(density)
    cumulative = np.cumsum(area[ok][order]) / max(float(area[ok].sum()), 1e-12)

    def quantile(q):
        return float(density[order][min(len(order) - 1, np.searchsorted(cumulative, q))]) if len(order) else 0.0
    verts = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", verts)
    verts = verts.reshape(-1, 3)
    low, high = verts.min(0), verts.max(0)
    size = np.maximum(high - low, 1e-5)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    device = "CPU"
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        usable = [d for d in prefs.devices if d.type == "OPTIX"]
        for d in prefs.devices:
            d.use = d.type == "OPTIX"
        if usable:
            device = "GPU"
    except Exception:
        pass
    scene.cycles.device = device
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    image = bpy.data.images.new("rac surface maps", res, res, alpha=True, float_buffer=True)
    image.colorspace_settings.name = "Non-Color"
    material = bpy.data.materials.new("rac bake rig")
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    new, link = tree.nodes.new, tree.links.new
    output = new("ShaderNodeOutputMaterial")
    emission = new("ShaderNodeEmission")
    diffuse = new("ShaderNodeBsdfDiffuse")
    target = new("ShaderNodeTexImage")
    target.image = image
    tree.nodes.active = target
    target.select = True
    mesh.materials.clear()
    mesh.materials.append(material)
    bpy.ops.object.select_all(action="DESELECT")
    part.select_set(True)
    bpy.context.view_layer.objects.active = part

    def attribute(label):
        node = new("ShaderNodeAttribute")
        node.attribute_type = "GEOMETRY"
        node.attribute_name = label
        return node

    def combine(x, y, z):
        node = new("ShaderNodeCombineXYZ")
        for socket, source in zip(node.inputs, (x, y, z)):
            if isinstance(source, (int, float)):
                socket.default_value = source
            else:
                link(source, socket)
        return node.outputs[0]

    def occlusion(distance):
        node = new("ShaderNodeAmbientOcclusion")
        node.samples = 16
        node.only_local = True
        node.inputs["Distance"].default_value = distance
        return node.outputs["AO"]

    def run(kind, samples, **options):
        image.pixels.foreach_set(np.zeros(res * res * 4, np.float32))
        scene.cycles.samples = max(1, round(samples * quality))
        bpy.ops.object.bake(type=kind, margin=0, use_clear=False, **options)
        buffer = np.empty(res * res * 4, np.float32)
        image.pixels.foreach_get(buffer)
        return buffer.reshape(res, res, 4)[::-1]                    # row 0 at the top, as a PNG stores it

    def emit(source, samples):
        for old in list(emission.inputs["Color"].links):
            tree.links.remove(old)
        link(source, emission.inputs["Color"])
        link(emission.outputs[0], output.inputs["Surface"])
        return run("EMIT", samples)

    # Position travels normalised to the part's bounds, so nothing is negative in transit.
    coords = new("ShaderNodeTexCoord")
    shift = new("ShaderNodeVectorMath")
    shift.operation = "SUBTRACT"
    link(coords.outputs["Object"], shift.inputs[0])
    shift.inputs[1].default_value = tuple(low)
    scale = new("ShaderNodeVectorMath")
    scale.operation = "DIVIDE"
    link(shift.outputs[0], scale.inputs[0])
    scale.inputs[1].default_value = tuple(size)
    position = emit(scale.outputs[0], 4)[..., :3] * size + low

    lift = new("ShaderNodeMath")
    lift.operation = "MULTIPLY_ADD"
    link(attribute("rac_class").outputs["Fac"], lift.inputs[0])
    lift.inputs[1].default_value = 1 / 64
    lift.inputs[2].default_value = 1 / 64
    labels = emit(combine(lift.outputs[0], attribute("dome").outputs["Fac"] if "dome" in annotations else 0.0,
                          attribute("rnd").outputs["Fac"] if "rnd" in annotations else 0.0), 1)
    valid = labels[..., 0] > .008
    if not valid.any():
        raise ValueError("The bake covered no texel")
    arrays = {"valid": valid, "pos": position.astype(np.float32),
              "cls": np.clip(np.rint(labels[..., 0] * 64 - 1), 0, 62).astype(np.uint8)}
    if "dome" in annotations:
        arrays["dome"] = labels[..., 1].astype(np.float16)
    if "rnd" in annotations:
        arrays["rnd"] = labels[..., 2] > .5
    if "axisv" in annotations:
        grain = new("ShaderNodeVectorMath")
        grain.operation = "MULTIPLY_ADD"
        link(attribute("axisv").outputs["Vector"], grain.inputs[0])
        grain.inputs[1].default_value = (.5, .5, .5)
        grain.inputs[2].default_value = (.5, .5, .5)
        arrays["axis"] = (emit(grain.outputs[0], 1)[..., :3] * 2 - 1).astype(np.float16)
    arrays["ao"] = emit(combine(occlusion(.30), occlusion(.012), occlusion(.06)), 8)[..., :3].astype(np.float16)

    link(diffuse.outputs[0], output.inputs["Surface"])
    arrays["nrm"] = (run("NORMAL", 4, normal_space="OBJECT")[..., :3] * 2 - 1).astype(np.float16)
    bevel = new("ShaderNodeBevel")
    bevel.samples = 8
    link(bevel.outputs["Normal"], diffuse.inputs["Normal"])
    bevel.inputs["Radius"].default_value = .003
    rounded = run("NORMAL", 12, normal_space="TANGENT")[..., :3] * 2 - 1
    bevel.inputs["Radius"].default_value = .011
    worn = run("NORMAL", 12, normal_space="TANGENT")[..., 2:3] * 2 - 1
    arrays["bev"] = np.concatenate([rounded, worn], axis=2).astype(np.float16)
    arrays["bounds"] = np.stack([low, high]).astype(np.float32)
    arrays["class_names"] = np.array(names)
    arrays["fasteners"] = np.array(heads, np.float32).reshape(-1, 7)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    present = sorted(int(i) for i in np.unique(arrays["cls"][valid]))
    receipt = {"schema": MAPS_SCHEMA, "source": args.source.name, "source_sha256": sha(args.source), "recipe_sha256": sha(args.textures),
               "output_sha256": sha(args.output), "blender": bpy.app.version_string, "device": device,
               "resolution": res, "samples": quality, "object": part.name, "triangles": int(count), "vertices": len(mesh.vertices),
               "bounds_min_m": [round(float(v), 5) for v in low], "bounds_max_m": [round(float(v), 5) for v in high],
               "surface_area_m2": round(float(area.sum()), 4), "atlas_fill": round(float(valid.mean()), 3),
               "texels_per_metre": {"p10": round(quantile(.1)), "median": round(quantile(.5)), "p90": round(quantile(.9))},
               "class_source": class_source, "class_names": names, "classes_present": [names[i] if i < len(names) else str(i) for i in present],
               "annotations": annotations, "fasteners": len(heads), "maps": sorted(arrays), "axes": "Blender: Z up, metres",
               "seconds": round(time.time() - began, 1)}
    with args.report.open("x", encoding="utf8") as stream:
        json.dump(receipt, stream, indent=2)
    print("BAKE_SURFACE_MAPS_COMPLETE -- {0} px, {1:.0f} texels per metre typical, {2} fasteners; the part has told what it knows.".format(
        res, quantile(.5), len(heads)))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:])
