"""Re-bake a painted mesh's maps from its dense original onto its reduction.

Reducing a mesh after it was painted moves its UVs with the collapse. Every
vertex that survives is re-placed, and its UV is interpolated with it, so the
paint slides across the surface: a floor brazier reduced from 120k triangles
kept its silhouette within millimetres and still lost its iron bands and rivets
at every rung. Its shading was not the problem -- transferring the dense
normals changed nothing -- because the damage is where the paint landed.

So the paint is not carried across by the UVs at all. Each texel of the
reduced mesh looks a few millimetres along its normal, finds the dense surface
there, and takes what that surface was painted:

  base colour   (and alpha, when the original had a cutout)
  roughness and metallic, packed the way glTF reads them
  occlusion, transmission and emission, when the original used them
  a tangent-space normal map, which carries the dense surface's relief -- its
                own geometry and any normal map it already had -- onto the
                lighter one

Rays are short on purpose (see "Bake rays must be short" in docs/COMPILER.md):
they only need to cross the gap between the two surfaces, which the reduction
measured, and a longer ray lands on the wrong part.

Only the painted atlas is re-baked. A material with no texture, or one whose
texture tiles or samples another UV layer, cannot smear -- a tiling oak grain
that slides is still oak grain -- so it is kept exactly as it was.

The reduced mesh's own UVs are used when they are still a usable atlas. A
collapse can fold them (overlaps, flipped or crushed triangles); when it
introduced more of that than the source already had, the painted faces are
unwrapped afresh and baked onto that instead. Either way the receipt says which
and why.

Everything runs on the CPU. The device is set and printed, and the thread count
is capped, because the GPU on this machine usually belongs to somebody else.

Usage:
  blender -b --factory-startup -t 8 --python scripts/blender/rebake_dense_maps.py -- \
      <dense.blend|.glb> <reduced.blend|.glb> <out_dir> <report.json> \
      [--uv-layout auto|keep|fresh] [--normal-resolution 2048] [--samples 4] \
      [--threads 8]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rebake_rules import painted_shares, plan_channels, ray_settings, uv_verdict  # noqa: E402
from retopo_bake import fill_unbaked, sanitise_normal_map  # noqa: E402

GLTF_OUTPUT_GROUPS = ("glTF Material Output", "glTF Settings")


def parse_args() -> argparse.Namespace:
    values = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("dense", type=Path)
    parser.add_argument("reduced", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--uv-layout", choices=("auto", "keep", "fresh"), default="auto")
    parser.add_argument("--normal-resolution", type=int, default=2048)
    # Normal maps are geometry and alias like geometry; colour channels are
    # texture lookups that the image's own filtering already smooths.
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--asset-label", default="")
    return parser.parse_args(values)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def use_cpu(scene, threads: int) -> dict:
    """Cycles on the CPU, a fixed number of threads, and say so."""
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    preferences = bpy.context.preferences.addons.get("cycles")
    if preferences is not None:
        # Belt and braces: with no compute device type, nothing can be offloaded
        # whatever the scene asks for.
        preferences.preferences.compute_device_type = "NONE"
    if hasattr(scene.cycles, "denoising_use_gpu"):
        scene.cycles.denoising_use_gpu = False
    scene.render.threads_mode = "FIXED"
    scene.render.threads = int(threads)
    device = {
        "engine": scene.render.engine,
        "device": scene.cycles.device,
        "compute_device_type": preferences.preferences.compute_device_type if preferences else None,
        "threads_mode": scene.render.threads_mode,
        "threads": scene.render.threads,
    }
    print("[REBAKE] cycles device={device} compute_device_type={compute_device_type} "
          "threads={threads}".format(**device), flush=True)
    return device


def load_mesh(path: Path, role: str):
    """Bring one file's single mesh into the current scene and return it."""
    before = set(bpy.data.objects)
    suffix = path.suffix.lower()
    if suffix == ".blend":
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            target.objects = list(source.objects)
        for obj in target.objects:
            if obj is not None and obj.type == "MESH":
                bpy.context.scene.collection.objects.link(obj)
    elif suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    else:
        raise RuntimeError("The {0} mesh must be .blend, .glb or .gltf, not {1}".format(
            role, suffix or "a file without an extension"))
    meshes = [obj for obj in set(bpy.data.objects) - before
              if obj.type == "MESH" and obj.name in bpy.context.scene.objects]
    if len(meshes) != 1:
        raise RuntimeError("The {0} file must hold exactly one mesh object; {1} has {2}. "
                           "Assemblies are re-baked part by part.".format(
                               role, path.name, len(meshes)))
    obj = meshes[0]
    # An appended object may arrive parented to something that was not brought
    # along; bake in world space with its world transform kept.
    matrix = obj.matrix_world.copy()
    obj.parent = None
    obj.matrix_world = matrix
    return obj


def world_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector([min(c[i] for c in corners) for i in range(3)])
    high = Vector([max(c[i] for c in corners) for i in range(3)])
    return low, high


def same_place(dense, reduced) -> dict:
    """Two meshes a bake can pair: the same object, in the same place."""
    dense_low, dense_high = world_bounds(dense)
    reduced_low, reduced_high = world_bounds(reduced)
    diagonal = (dense_high - dense_low).length
    centre_offset = ((dense_low + dense_high) * 0.5 - (reduced_low + reduced_high) * 0.5).length
    size_ratio = (reduced_high - reduced_low).length / max(diagonal, 1e-9)
    return {
        "diagonal_m": round(diagonal, 5),
        "centre_offset_m": round(centre_offset, 6),
        "size_ratio": round(size_ratio, 5),
        "ok": centre_offset <= 0.02 * diagonal and abs(size_ratio - 1.0) <= 0.02,
    }


def surface_gap(dense, reduced, samples=6000) -> dict:
    """How far the two surfaces sit apart, both ways, in metres.

    Rays have to cross exactly this gap: shorter misses, longer lands on the
    next part over.
    """
    def one_way(origin, target):
        mesh = origin.data
        step = max(1, len(mesh.vertices) // samples)
        inverse = target.matrix_world.inverted()
        distances = []
        for index in range(0, len(mesh.vertices), step):
            point = origin.matrix_world @ mesh.vertices[index].co
            found, location, _, _ = target.closest_point_on_mesh(inverse @ point)
            if found:
                distances.append(((target.matrix_world @ location) - point).length)
        return np.array(distances or [0.0], dtype=np.float64)

    forward = one_way(reduced, dense)
    backward = one_way(dense, reduced)
    both = np.concatenate([forward, backward])
    return {
        "samples": int(len(both)),
        "p99_m": round(float(np.percentile(both, 99)), 6),
        "max_m": round(float(both.max()), 6),
    }


def principled(material):
    if material is None or not material.use_nodes:
        return None
    output = material.node_tree.get_output_node("ALL") or next(
        (node for node in material.node_tree.nodes if node.type == "OUTPUT_MATERIAL"), None)
    if output is None or not output.inputs["Surface"].is_linked:
        return None
    node = output.inputs["Surface"].links[0].from_node
    return node if node.type == "BSDF_PRINCIPLED" else None


def upstream_nodes(socket, seen=None):
    seen = seen if seen is not None else set()
    for link in socket.links:
        node = link.from_node
        if node in seen:
            continue
        seen.add(node)
        for item in node.inputs:
            if item.is_linked:
                upstream_nodes(item, seen)
    return seen


def image_uv_layer(node) -> str:
    """Which UV layer an image node reads: a name, '' for the default, or '?'."""
    vector = node.inputs.get("Vector")
    if vector is None or not vector.is_linked:
        return ""
    source = vector.links[0].from_node
    while source.type == "MAPPING" and source.inputs["Vector"].is_linked:
        source = source.inputs["Vector"].links[0].from_node
    if source.type == "UVMAP":
        return source.uv_map
    if source.type == "TEX_COORD" and vector.links[0].from_socket.name == "UV":
        return ""
    return "?"


def classify_slots(obj) -> list[dict]:
    """Which material slots carry painted atlas paint, and which cannot smear."""
    mesh = obj.data
    primary = next((layer for layer in mesh.uv_layers if layer.active_render), None)
    primary_name = primary.name if primary is not None else None
    uv = None
    if primary is not None:
        uv = np.empty(len(mesh.loops) * 2, dtype=np.float64)
        primary.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
    material_index = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("material_index", material_index)
    loop_start = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("loop_start", loop_start)
    loop_total = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("loop_total", loop_total)
    loop_face = np.repeat(np.arange(len(mesh.polygons)), loop_total)

    slots = []
    for index, slot in enumerate(obj.material_slots):
        material = slot.material
        faces = int((material_index == index).sum())
        entry = {"slot": index, "material": material.name if material else None, "faces": faces}
        bsdf = principled(material)
        if faces == 0:
            entry.update(treatment="kept", reason="no face uses it")
        elif bsdf is None:
            entry.update(treatment="refused",
                         reason="its surface is not a Principled BSDF, which glTF cannot carry "
                                "and this bake cannot read")
        else:
            output = material.node_tree.get_output_node("ALL")
            used = upstream_nodes(output.inputs["Surface"]) if output else set()
            images = [node for node in used if node.type == "TEX_IMAGE" and node.image]
            layers = {image_uv_layer(node) for node in images}
            reads_primary = bool(layers & {"", primary_name})
            outside = 0.0
            if uv is not None and reads_primary:
                face_loops = np.isin(loop_face, np.flatnonzero(material_index == index))
                coords = uv[face_loops]
                outside = float(((coords < -0.01) | (coords > 1.01)).any(axis=1).mean())
            if not images:
                entry.update(treatment="kept",
                             reason="a flat material: nothing painted on it can slide")
            elif not reads_primary:
                entry.update(treatment="kept",
                             reason="its textures read {0}, not the painted atlas".format(
                                 ", ".join(sorted(layer or "the default layer" for layer in layers))))
            elif outside > 0.05:
                entry.update(treatment="kept",
                             reason="its texture tiles ({0:.0%} of its UVs lie outside the unit "
                                    "square): a tiling texture that slides still reads the "
                                    "same".format(outside))
            else:
                entry.update(treatment="rebaked", reason="painted through the atlas")
        slots.append(entry)
    return slots


# --- what each re-baked material says, channel by channel -----------------------

def clip_pattern(bsdf):
    """Blender's glTF alpha-clip idiom: Alpha = 1 - (x < cutoff). Returns (x socket, cutoff)."""
    alpha = bsdf.inputs["Alpha"]
    if not alpha.is_linked:
        return None
    subtract = alpha.links[0].from_node
    if subtract.type != "MATH" or subtract.operation != "SUBTRACT":
        return None
    if subtract.inputs[0].is_linked or abs(subtract.inputs[0].default_value - 1.0) > 1e-6:
        return None
    if not subtract.inputs[1].is_linked:
        return None
    less = subtract.inputs[1].links[0].from_node
    if less.type != "MATH" or less.operation != "LESS_THAN" or not less.inputs[0].is_linked:
        return None
    return less.inputs[0].links[0].from_socket, float(less.inputs[1].default_value)


def occlusion_socket(material):
    for node in material.node_tree.nodes:
        # Appending one file into another renames a clashing group to
        # "glTF Material Output.001"; the exporter's convention is the name
        # before any such suffix.
        if node.type == "GROUP" and node.node_tree and \
                node.node_tree.name.split(".")[0] in GLTF_OUTPUT_GROUPS:
            socket = node.inputs.get("Occlusion")
            if socket is not None and socket.is_linked:
                return socket
    return None


def channel_sources(material) -> dict:
    """Where each glTF channel of one material comes from: a socket or a constant."""
    bsdf = principled(material)

    def read(name, scalar=True):
        socket = bsdf.inputs[name]
        if socket.is_linked:
            return {"socket": socket.links[0].from_socket}
        value = socket.default_value
        return {"constant": float(value) if scalar else tuple(value)[:3]}

    sources = {
        "base_color": read("Base Color", scalar=False),
        "roughness": read("Roughness"),
        "metallic": read("Metallic"),
        "transmission": read("Transmission Weight"),
        "emission": read("Emission Color", scalar=False),
    }
    clip = clip_pattern(bsdf)
    if clip is not None:
        sources["alpha"] = {"socket": clip[0], "cutoff": clip[1]}
    else:
        sources["alpha"] = read("Alpha")
    occlusion = occlusion_socket(material)
    sources["occlusion"] = {"socket": occlusion.links[0].from_socket} if occlusion else {"constant": 1.0}
    return sources


def channel_entries(material) -> dict:
    """``channel_sources`` in the plain terms ``rebake_rules.plan_channels`` reads."""
    entries = {}
    for channel, source in channel_sources(material).items():
        if "socket" in source:
            entries[channel] = {"linked": True, "cutoff": source.get("cutoff")}
        else:
            entries[channel] = {"constant": source["constant"]}
    return entries


def emit_graph(material, channel):
    """Route one channel of one dense material to its own output, as emission.

    The material's active output is rewired rather than replaced: Blender does
    not reliably let a script move which output is active, and a bake through
    the untouched BSDF of an unlit scene comes back black everywhere.
    ``restore_surface`` puts the BSDF back.
    """
    tree = material.node_tree
    sources = channel_sources(material)
    output = tree.get_output_node("ALL")
    emission = tree.nodes.new("ShaderNodeEmission")
    emission.label = "RAC rebake " + channel
    emission.inputs["Strength"].default_value = 1.0
    if channel == "mask":
        emission.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        return output
    tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    if channel == "metallic_roughness":
        combine = tree.nodes.new("ShaderNodeCombineColor")
        combine.inputs[0].default_value = 0.0
        for index, name in ((1, "roughness"), (2, "metallic")):
            entry = sources[name]
            if "socket" in entry:
                tree.links.new(entry["socket"], combine.inputs[index])
            else:
                combine.inputs[index].default_value = entry["constant"]
        tree.links.new(combine.outputs["Color"], emission.inputs["Color"])
    else:
        entry = sources[channel]
        if "socket" in entry:
            tree.links.new(entry["socket"], emission.inputs["Color"])
        else:
            value = entry["constant"]
            if isinstance(value, tuple):
                emission.inputs["Color"].default_value = (*value, 1.0)
            else:
                emission.inputs["Color"].default_value = (value, value, value, 1.0)
    return output


def restore_surface(material, bsdf_socket):
    """Undo ``emit_graph``: the BSDF drives the surface again, nothing extra remains."""
    tree = material.node_tree
    output = tree.get_output_node("ALL")
    tree.links.new(bsdf_socket, output.inputs["Surface"])
    for node in list(tree.nodes):
        if node.type == "EMISSION" and node.label.startswith("RAC rebake"):
            tree.nodes.remove(node)
        elif node.type == "COMBINE_COLOR" and not node.outputs["Color"].is_linked:
            tree.nodes.remove(node)


# --- UV health --------------------------------------------------------------------

def triangles_of(obj, face_mask, uv_name):
    mesh = obj.data
    mesh.calc_loop_triangles()
    count = len(mesh.loop_triangles)
    loops = np.empty(count * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get("loops", loops)
    polygons = np.empty(count, dtype=np.int64)
    mesh.loop_triangles.foreach_get("polygon_index", polygons)
    keep = face_mask[polygons]
    loops = loops.reshape(-1, 3)[keep]
    uv = np.empty(len(mesh.loops) * 2, dtype=np.float64)
    mesh.uv_layers[uv_name].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    vertex_of_loop = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", vertex_of_loop)
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return uv[loops], co[vertex_of_loop[loops]]


def coverage_overlap(tri_uv, raster=512):
    """Share of covered texels that more than one triangle claims, and the sheet's fill."""
    counts = rasterize(tri_uv, raster)
    covered = int((counts >= 1).sum())
    return (float((counts >= 2).sum()) / covered) if covered else 0.0, covered / float(raster * raster)


def rasterize(tri_uv, raster):
    """How many triangles claim each texel centre (row 0 is the bottom, as in Blender)."""
    counts = np.zeros((raster, raster), dtype=np.int32)
    pixels = tri_uv * raster
    lows = np.floor(pixels.min(axis=1)).astype(np.int64)
    highs = np.ceil(pixels.max(axis=1)).astype(np.int64)
    lows = np.clip(lows, 0, raster - 1)
    highs = np.clip(highs, 0, raster)
    a, b, c = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    denominator = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    usable = np.abs(denominator) > 1e-12
    span = np.maximum(highs - lows, 0)
    # Small triangles in one vectorised sweep; the few large ones one at a time.
    small = usable & (span[:, 0] <= 4) & (span[:, 1] <= 4)
    grid = np.stack(np.meshgrid(np.arange(4), np.arange(4), indexing="xy"), axis=-1).reshape(-1, 2)

    def mark(indices, offsets):
        px = lows[indices, None, 0] + offsets[None, :, 0]
        py = lows[indices, None, 1] + offsets[None, :, 1]
        cx, cy = px + 0.5, py + 0.5
        aa, bb, cc, dd = a[indices], b[indices], c[indices], denominator[indices]
        w1 = ((bb[:, None, 1] - cc[:, None, 1]) * (cx - cc[:, None, 0])
              + (cc[:, None, 0] - bb[:, None, 0]) * (cy - cc[:, None, 1])) / dd[:, None]
        w2 = ((cc[:, None, 1] - aa[:, None, 1]) * (cx - cc[:, None, 0])
              + (aa[:, None, 0] - cc[:, None, 0]) * (cy - cc[:, None, 1])) / dd[:, None]
        w3 = 1.0 - w1 - w2
        inside = (w1 > 1e-6) & (w2 > 1e-6) & (w3 > 1e-6) & (px < raster) & (py < raster)
        np.add.at(counts, (py[inside], px[inside]), 1)

    indices = np.flatnonzero(small)
    for start in range(0, len(indices), 20000):
        mark(indices[start:start + 20000], grid)
    for index in np.flatnonzero(usable & ~small):
        width, height = int(span[index, 0]) + 1, int(span[index, 1]) + 1
        offsets = np.stack(np.meshgrid(np.arange(width), np.arange(height), indexing="xy"),
                           axis=-1).reshape(-1, 2)
        mark(np.array([index]), offsets)
    return counts


def uv_health(obj, face_mask, uv_name) -> dict:
    tri_uv, tri_co = triangles_of(obj, face_mask, uv_name)
    if len(tri_uv) == 0:
        return {"triangles": 0}
    e1 = tri_uv[:, 1] - tri_uv[:, 0]
    e2 = tri_uv[:, 2] - tri_uv[:, 0]
    signed = 0.5 * (e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0])
    area = 0.5 * np.linalg.norm(np.cross(tri_co[:, 1] - tri_co[:, 0], tri_co[:, 2] - tri_co[:, 0]),
                                axis=1)
    total = float(area.sum()) or 1.0
    majority = 1.0 if float(area[signed > 0].sum()) >= float(area[signed < 0].sum()) else -1.0
    flipped = float(area[np.sign(signed) == -majority].sum()) / total
    density = np.abs(signed) / np.maximum(area, 1e-15)
    reference = float(np.abs(signed).sum()) / total
    ratio = density / max(reference, 1e-15)
    distorted = float(area[(ratio < 0.25) | (ratio > 4.0)].sum()) / total
    outside = float(((tri_uv < -0.001) | (tri_uv > 1.001)).any(axis=(1, 2)).mean())
    inside = ~((tri_uv < -0.001) | (tri_uv > 1.001)).any(axis=(1, 2))
    overlap, fill = coverage_overlap(np.clip(tri_uv[inside], 0.0, 1.0))
    return {
        "triangles": int(len(tri_uv)),
        "overlap_share": round(overlap, 5),
        "flipped_share": round(flipped, 5),
        "distorted_share": round(distorted, 5),
        "outside_share": round(outside, 5),
        "atlas_fill": round(fill, 4),
    }


def unwrap_fresh(obj, face_mask, uv_name) -> dict:
    """Unwrap only the painted faces, in place on the atlas layer."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.data.uv_layers.active = obj.data.uv_layers[uv_name]
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    for face in bm.faces:
        face.select_set(bool(face_mask[face.index]))
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.mesh.select_mode(type="FACE")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.002,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"method": "smart_project 66 degrees, then pack_islands margin 0.004",
            "faces": int(face_mask.sum())}


# --- baking -----------------------------------------------------------------------

def new_image(name, size, colour, alpha=True):
    image = bpy.data.images.new(name, size, size, alpha=alpha, float_buffer=False)
    image.generated_color = (0.0, 0.0, 0.0, 0.0)
    image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return image


def bake_into(image, low, dense, bake_type, bake_materials, scratch_materials, rays, samples,
              margin):
    """One selected-to-active bake into one image, written only by painted faces."""
    scene = bpy.context.scene
    scene.cycles.samples = samples
    targets = []
    for material in bake_materials:
        tree = material.node_tree
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        targets.append((tree, node))
    # Every other material on the reduced mesh still needs an active image or
    # Blender refuses the bake; its faces write into a scratch image instead.
    scratch = bpy.data.images.new("RAC_rebake_scratch", 64, 64, alpha=True)
    for material in scratch_materials:
        tree = material.node_tree
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = scratch
        targets.append((tree, node))
    for tree, node in targets:
        for other in tree.nodes:
            other.select = False
        node.select = True
        tree.nodes.active = node

    bake = scene.render.bake
    bake.use_selected_to_active = True
    bake.use_cage = False
    bake.cage_extrusion = rays["cage_extrusion_m"]
    bake.max_ray_distance = rays["max_ray_distance_m"]
    bake.margin = margin
    if hasattr(bake, "margin_type"):
        bake.margin_type = "ADJACENT_FACES"
    bake.target = "IMAGE_TEXTURES"
    if bake_type == "NORMAL":
        bake.normal_space = "TANGENT"
        bake.normal_r, bake.normal_g, bake.normal_b = "POS_X", "POS_Y", "POS_Z"

    bpy.ops.object.select_all(action="DESELECT")
    dense.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    started = time.monotonic()
    bpy.ops.object.bake(type=bake_type, use_clear=True, margin=margin,
                        use_selected_to_active=True, cage_extrusion=rays["cage_extrusion_m"],
                        max_ray_distance=rays["max_ray_distance_m"])
    seconds = time.monotonic() - started
    for tree, node in targets:
        tree.nodes.remove(node)
    bpy.data.images.remove(scratch)
    return seconds


def pixels_of(image):
    width, height = image.size
    return np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)


def resample_mask(mask, size):
    """Nearest-neighbour: a coverage mask at one resolution, read at another."""
    rows = (np.arange(size) * mask.shape[0] // size).astype(np.int64)
    cols = (np.arange(size) * mask.shape[1] // size).astype(np.int64)
    return mask[np.ix_(rows, cols)]


def settle(image, pixels, written, normal=False) -> dict:
    """Fill what the bake never wrote, flatten implausible normals, write back.

    A bake's alpha cannot say which texels it wrote: a normal map comes back
    opaque everywhere, and the margin makes opaque the misses it reaches.
    ``written`` comes from a separate pass that baked plain white with the same
    margin: anything still black there was neither reached nor covered by the
    margin, and is grown over from its neighbours rather than shipped as black.
    """
    pixels[..., 3] = resample_mask(written, pixels.shape[0]).astype(np.float32)
    share = float(pixels[..., 3].mean())
    filled = fill_unbaked(pixels)
    repaired = sanitise_normal_map(pixels) if normal else 0
    image.pixels.foreach_set(pixels.reshape(-1))
    image.update()
    return {"written_share": round(share, 4), "texels_filled": int(filled),
            "normal_texels_flattened": int(repaired)}


def save_png(image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    # Keep the pixels inside the .blend and the GLB rather than a path that
    # moves with the folder.
    image.pack()


# --- the runtime material -----------------------------------------------------------

def copy_constants(source_bsdf, target_bsdf):
    for socket in source_bsdf.inputs:
        if socket.is_linked or not hasattr(socket, "default_value"):
            continue
        target = target_bsdf.inputs.get(socket.name)
        if target is None or target.is_linked:
            continue
        try:
            value = socket.default_value
            target.default_value = tuple(value) if hasattr(value, "__len__") else value
        except (TypeError, AttributeError):
            pass


def gltf_output_group():
    for name in GLTF_OUTPUT_GROUPS:
        group = bpy.data.node_groups.get(name)
        if group is not None:
            return group
    group = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
    group.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return group


def build_material(primary, images, plan, uv_name):
    """A glTF-shaped material reading only the re-baked maps."""
    material = bpy.data.materials.new(primary.name)
    material.use_nodes = True
    for attribute in ("blend_method", "surface_render_method", "use_backface_culling",
                      "alpha_threshold"):
        if hasattr(primary, attribute) and hasattr(material, attribute):
            try:
                setattr(material, attribute, getattr(primary, attribute))
            except (TypeError, AttributeError):
                pass
    tree = material.node_tree
    bsdf = next(node for node in tree.nodes if node.type == "BSDF_PRINCIPLED")
    copy_constants(principled(primary), bsdf)
    uvmap = tree.nodes.new("ShaderNodeUVMap")
    uvmap.uv_map = uv_name

    def texture(image):
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        tree.links.new(uvmap.outputs["UV"], node.inputs["Vector"])
        return node

    base = texture(images["base_color"])
    tree.links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    if plan["alpha"]["baked"]:
        cutoff = plan["alpha"].get("cutoff")
        if cutoff is None:
            tree.links.new(base.outputs["Alpha"], bsdf.inputs["Alpha"])
        else:
            # The same idiom the source used, so the exporter writes MASK
            # with the same cutoff instead of a blended edge.
            less = tree.nodes.new("ShaderNodeMath")
            less.operation = "LESS_THAN"
            less.inputs[1].default_value = cutoff
            subtract = tree.nodes.new("ShaderNodeMath")
            subtract.operation = "SUBTRACT"
            subtract.inputs[0].default_value = 1.0
            tree.links.new(base.outputs["Alpha"], less.inputs[0])
            tree.links.new(less.outputs["Value"], subtract.inputs[1])
            tree.links.new(subtract.outputs["Value"], bsdf.inputs["Alpha"])
    else:
        bsdf.inputs["Alpha"].default_value = plan["alpha"]["constant"]
    if "metallic_roughness" in images:
        node = texture(images["metallic_roughness"])
        separate = tree.nodes.new("ShaderNodeSeparateColor")
        tree.links.new(node.outputs["Color"], separate.inputs["Color"])
        tree.links.new(separate.outputs["Green"], bsdf.inputs["Roughness"])
        tree.links.new(separate.outputs["Blue"], bsdf.inputs["Metallic"])
    else:
        bsdf.inputs["Roughness"].default_value = plan["roughness"]["constant"]
        bsdf.inputs["Metallic"].default_value = plan["metallic"]["constant"]
    for channel, socket_name in (("transmission", "Transmission Weight"),):
        if channel in images:
            node = texture(images[channel])
            separate = tree.nodes.new("ShaderNodeSeparateColor")
            tree.links.new(node.outputs["Color"], separate.inputs["Color"])
            tree.links.new(separate.outputs["Red"], bsdf.inputs[socket_name])
        else:
            bsdf.inputs[socket_name].default_value = plan[channel]["constant"]
    if "emission" in images:
        node = texture(images["emission"])
        tree.links.new(node.outputs["Color"], bsdf.inputs["Emission Color"])
    else:
        bsdf.inputs["Emission Color"].default_value = (*plan["emission"]["constant"], 1.0)
    if "occlusion" in images:
        node = texture(images["occlusion"])
        separate = tree.nodes.new("ShaderNodeSeparateColor")
        tree.links.new(node.outputs["Color"], separate.inputs["Color"])
        group = tree.nodes.new("ShaderNodeGroup")
        group.node_tree = gltf_output_group()
        tree.links.new(separate.outputs["Red"], group.inputs["Occlusion"])
    normal = texture(images["normal"])
    normal_map = tree.nodes.new("ShaderNodeNormalMap")
    normal_map.space = "TANGENT"
    normal_map.uv_map = uv_name
    tree.links.new(normal.outputs["Color"], normal_map.inputs["Color"])
    tree.links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def topology(obj) -> dict:
    mesh = obj.data
    mesh.calc_loop_triangles()
    return {"vertices": len(mesh.vertices), "polygons": len(mesh.polygons),
            "triangles": len(mesh.loop_triangles)}


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    dense_path, reduced_path = args.dense.resolve(), args.reduced.resolve()
    out_dir, report_path = args.out_dir.resolve(), args.report.resolve()
    for path, role in ((dense_path, "dense"), (reduced_path, "reduced")):
        if not path.is_file():
            print("[REBAKE] FAILED: the {0} mesh does not exist: {1}".format(role, path))
            return 1
    if report_path.exists() or (out_dir / "rebaked.glb").exists():
        print("[REBAKE] FAILED: refusing to overwrite an earlier bake in {0}".format(out_dir))
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    device = use_cpu(scene, args.threads)
    try:
        low = load_mesh(reduced_path, "reduced")
        low.name = "RAC_Reduced"
        dense = load_mesh(dense_path, "dense")
        dense.name = "RAC_Dense"
    except RuntimeError as problem:
        print("[REBAKE] FAILED: {0}".format(problem))
        return 1

    placement = same_place(dense, low)
    if not placement["ok"]:
        print("[REBAKE] FAILED: the reduced and dense meshes are not the same object in the same "
              "place (centre {0:.4f} m apart, size ratio {1:.3f}); a bake between them would "
              "transfer paint onto the wrong surface".format(
                  placement["centre_offset_m"], placement["size_ratio"]))
        return 1

    slots = classify_slots(low)
    refused = [slot for slot in slots if slot["treatment"] == "refused"]
    if refused:
        print("[REBAKE] FAILED: material {0}: {1}".format(refused[0]["material"],
                                                          refused[0]["reason"]))
        return 1
    rebaked = [slot for slot in slots if slot["treatment"] == "rebaked"]
    if not rebaked:
        print("[REBAKE] FAILED: nothing on this mesh is painted through an atlas, so there is "
              "nothing to re-bake; the reduction can be used as it is")
        return 1

    # The dense materials that matter are the ones on the same slots, which a
    # reduction keeps in order.
    dense_slots = list(dense.material_slots)
    dense_materials = []
    for slot in rebaked:
        index = slot["slot"]
        material = dense_slots[index].material if index < len(dense_slots) else None
        if material is None or principled(material) is None:
            print("[REBAKE] FAILED: the dense mesh has no Principled material on slot {0} to "
                  "bake from".format(index))
            return 1
        dense_materials.append(material)
    primary = max(zip(rebaked, dense_materials), key=lambda pair: pair[0]["faces"])[1]
    primary_name = primary.name
    plan = plan_channels([channel_entries(material) for material in dense_materials])
    print("[REBAKE] channels: {0}".format(
        {name: ("baked" if entry["baked"] else entry["constant"]) for name, entry in plan.items()}),
        flush=True)

    mesh = low.data
    uv_name = next((layer.name for layer in mesh.uv_layers if layer.active_render), None)
    face_material = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("material_index", face_material)
    painted = np.isin(face_material, [slot["slot"] for slot in rebaked])

    # Source atlas health on the same slots, so only what the reduction did
    # is held against it.
    dense_mesh = dense.data
    dense_uv = next((layer.name for layer in dense_mesh.uv_layers if layer.active_render), None)
    dense_face_material = np.empty(len(dense_mesh.polygons), dtype=np.int64)
    dense_mesh.polygons.foreach_get("material_index", dense_face_material)
    dense_painted = np.isin(dense_face_material, [slot["slot"] for slot in rebaked])
    source_health = uv_health(dense, dense_painted, dense_uv) if dense_uv else {}

    layout = {"requested": args.uv_layout, "source": source_health}
    if uv_name is None:
        mesh.uv_layers.new(name="UVMap")
        uv_name = "UVMap"
        layout["reduced"] = {"triangles": 0, "note": "the reduced mesh had no UV layer"}
        use_fresh = True
        layout["reasons"] = ["the reduced mesh has no UV layer"]
    else:
        layout["reduced"] = uv_health(low, painted, uv_name)
        healthy, reasons = uv_verdict(layout["reduced"], source_health)
        layout["reasons"] = reasons
        use_fresh = args.uv_layout == "fresh" or (args.uv_layout == "auto" and not healthy)
    if use_fresh:
        layout["unwrap"] = unwrap_fresh(low, painted, uv_name)
        layout["after_unwrap"] = uv_health(low, painted, uv_name)
        layout["used"] = "fresh"
    else:
        layout["used"] = "kept"
    print("[REBAKE] UV layout: {0} ({1})".format(
        layout["used"], "; ".join(layout["reasons"]) or "the reduced atlas is still usable"),
        flush=True)
    for layer in mesh.uv_layers:
        layer.active = layer.name == uv_name

    gap = surface_gap(dense, low)
    rays = ray_settings(gap["p99_m"], placement["diagonal_m"])
    print("[REBAKE] surface gap p99 {0:.4f} m max {1:.4f} m; extrusion {2:.4f} m, rays {3:.4f} m"
          .format(gap["p99_m"], gap["max_m"], rays["cage_extrusion_m"],
                  rays["max_ray_distance_m"]), flush=True)

    # Each re-baked slot on the reduced mesh gets one target material; every
    # other slot writes into scratch.
    low_rebaked = [low.material_slots[slot["slot"]].material for slot in rebaked]
    low_kept = [low.material_slots[slot["slot"]].material for slot in slots
                if slot["treatment"] == "kept" and low.material_slots[slot["slot"]].material]
    target_materials = list(dict.fromkeys(low_rebaked))

    def source_size(channel, fallback):
        """The largest image that feeds a channel: the bake keeps its resolution."""
        sizes = []
        for material in dense_materials:
            socket = channel_sources(material)[channel].get("socket")
            if socket is None:
                continue
            nodes = {socket.node} | upstream_nodes_from_node(socket.node)
            sizes += [max(node.image.size) for node in nodes
                      if node.type == "TEX_IMAGE" and node.image and max(node.image.size) > 0]
        return max(sizes) if sizes else fallback

    base_size = source_size("base_color", 2048)
    jobs = [("base_color", base_size, True)]
    if plan["alpha"]["baked"]:
        jobs.append(("alpha", base_size, False))
    if plan["roughness"]["baked"] or plan["metallic"]["baked"]:
        jobs.append(("metallic_roughness", max(source_size("roughness", 0),
                                               source_size("metallic", 0)) or 1024, False))
    for channel in ("transmission", "occlusion"):
        if plan[channel]["baked"]:
            jobs.append((channel, source_size(channel, 1024), False))
    if plan["emission"]["baked"]:
        jobs.append(("emission", source_size("emission", 1024), True))

    label = args.asset_label or reduced_path.stem
    maps_dir = out_dir / "maps"
    images, bakes = {}, {}
    margin = 16

    dense_all = [material for material in dict.fromkeys(
        slot.material for slot in dense.material_slots if slot.material)
        if principled(material) is not None]
    bsdf_sockets = {material.name: principled(material).outputs[0] for material in dense_all}

    def emit_bake(channel, size, colour, bake_margin=margin):
        for material in dense_all:
            emit_graph(material, channel)
        image = new_image("T_{0}_{1}".format(label, "".join(
            part.title() for part in channel.split("_"))), size, colour=colour)
        try:
            seconds = bake_into(image, low, dense, "EMIT", target_materials, low_kept, rays, 1,
                                bake_margin)
        finally:
            for material in dense_all:
                restore_surface(material, bsdf_sockets[material.name])
        return image, seconds

    # Which texels a ray actually reached, at the largest size any map uses,
    # baked twice. Without a margin it is what the rays reached. With the maps'
    # margin it is what every map will have written -- the margin also covers
    # the misses within its width -- and the rest is what the fill repairs. A
    # mask baked with the margin alone counts those covered misses as reached.
    coverage_size = max([size for _, size, _ in jobs] + [args.normal_resolution])
    masks, seconds = {}, 0.0
    for name, bake_margin in (("reached", 0), ("written", margin)):
        mask_image, spent = emit_bake("mask", coverage_size, colour=False,
                                      bake_margin=bake_margin)
        masks[name] = pixels_of(mask_image)[..., 0] > 0.5
        bpy.data.images.remove(mask_image)
        seconds += spent
    written = masks["written"]
    # Reached is only meaningful inside the painted islands; the rest of the
    # sheet is gutter, which the margin and the fill take care of.
    tri_uv, _ = triangles_of(low, painted, uv_name)
    island_size = min(coverage_size, 1024)
    islands = rasterize(np.clip(tri_uv, 0.0, 1.0), island_size) > 0
    shares = painted_shares(islands, resample_mask(masks["reached"], island_size),
                            resample_mask(written, island_size))
    bakes["coverage"] = {"resolution": coverage_size, "margin_px": margin,
                         "seconds": round(seconds, 1),
                         "sheet_reached_share": round(float(masks["reached"].mean()), 4),
                         "sheet_written_share": round(float(written.mean()), 4),
                         **shares}
    print("[REBAKE] coverage passes at {0} in {1:.1f}s: rays reached {2} of the painted "
          "surface, {3} with the margin".format(
              coverage_size, seconds,
              *("{0:.2%}".format(value) if value is not None else "none"
                for value in (shares["painted_surface_reached_share"],
                              shares["painted_surface_written_share"]))), flush=True)

    # Normal before the colour channels, with every dense material exactly as
    # authored: the normal pass reads their normal maps and bump as well as
    # their geometry.
    normal_image = new_image("T_{0}_Normal".format(label), args.normal_resolution, colour=False)
    seconds = bake_into(normal_image, low, dense, "NORMAL", target_materials, low_kept, rays,
                        max(1, args.samples), margin)
    bakes["normal"] = {"resolution": args.normal_resolution, "seconds": round(seconds, 1),
                       **settle(normal_image, pixels_of(normal_image), written, normal=True)}
    images["normal"] = normal_image
    print("[REBAKE] baked normal at {0} in {1:.1f}s".format(args.normal_resolution, seconds),
          flush=True)

    for channel, size, colour in jobs:
        image, seconds = emit_bake(channel, size, colour)
        bakes[channel] = {"resolution": size, "seconds": round(seconds, 1),
                          **settle(image, pixels_of(image), written)}
        images[channel] = image
        print("[REBAKE] baked {0} at {1} in {2:.1f}s".format(channel, size, seconds), flush=True)

    if "alpha" in images:
        # Alpha travels in the base colour's own alpha channel, which is where
        # glTF reads it.
        base_pixels = pixels_of(images["base_color"])
        base_pixels[..., 3] = pixels_of(images["alpha"])[..., 0]
        images["base_color"].pixels.foreach_set(base_pixels.reshape(-1))
        images["base_color"].update()
        bpy.data.images.remove(images.pop("alpha"))

    for channel, image in images.items():
        save_png(image, maps_dir / "{0}.png".format(image.name))

    # The delivered material keeps the name it had, so an engine or studio
    # matching materials by name finds the same one it was given before.
    delivered_name = low_rebaked[0].name
    runtime = build_material(primary, images, plan, uv_name)
    for slot in rebaked:
        low.material_slots[slot["slot"]].material = runtime

    # The dense mesh has served its purpose; nothing of it is delivered.
    dense_topology = topology(dense)
    dense_data = dense.data
    bpy.data.objects.remove(dense, do_unlink=True)
    bpy.data.meshes.remove(dense_data)
    for material in list(bpy.data.materials):
        if material.users == 0:
            bpy.data.materials.remove(material)
    runtime.name = delivered_name

    output_blend = out_dir / "rebaked.blend"
    output_glb = out_dir / "rebaked.glb"
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    bpy.ops.export_scene.gltf(
        filepath=str(output_glb), export_format="GLB", use_selection=True,
        export_materials="EXPORT", export_tangents=True, export_image_format="AUTO")

    report = {
        "schema": "reference-asset-compiler.rebaked-maps.v1",
        "status": "baked",
        "device": device,
        "dense": {"path": str(dense_path), "sha256": sha256_file(dense_path),
                  "topology": dense_topology},
        "reduced": {"path": str(reduced_path), "sha256": sha256_file(reduced_path),
                    "topology": topology(low)},
        "placement": placement,
        "materials": slots,
        "primary_material": primary_name,
        "channels": plan,
        "uv_layout": layout,
        "surface_gap": gap,
        "rays": rays,
        "bakes": bakes,
        "samples": {"normal": max(1, args.samples), "emit": 1},
        "margin_px": margin,
        "maps": {channel: {"file": str(maps_dir / "{0}.png".format(image.name)),
                           "sha256": sha256_file(maps_dir / "{0}.png".format(image.name)),
                           "size": list(image.size),
                           "colorspace": image.colorspace_settings.name}
                 for channel, image in images.items()},
        "output": {"blend": str(output_blend), "blend_sha256": sha256_file(output_blend),
                   "glb": str(output_glb), "glb_sha256": sha256_file(output_glb)},
        "seconds": round(time.monotonic() - started, 1),
        "requires_appearance_gate": True,
        "production_grade": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("RAC_REBAKE_OK report={0}".format(report_path), flush=True)
    return 0


def upstream_nodes_from_node(node):
    found = set()
    for item in node.inputs:
        if item.is_linked:
            found |= upstream_nodes(item)
    return found


if __name__ == "__main__":
    raise SystemExit(main())
