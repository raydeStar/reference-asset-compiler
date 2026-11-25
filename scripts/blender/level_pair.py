"""Level a generated model and its own simplified exports with one transform.

Pixal3D keeps the reference picture's camera tilt, so its meshes come out
leaning. Levelling each file on its own would tilt the dense mesh and the game
mesh by slightly different amounts, and a normal bake from one onto the other
would then miss by millimetres everywhere. The transform is worked out once,
from the first (dense) mesh, and applied to every file:

- principal axes become X (the length), Y (the breadth) and Z (up, the open
  side of a boat or bowl up: the wider end of the short axis);
- `--up` says which principal axis is up: the shortest (the default: a boat,
  a bench, a crate), the longest (a lantern, a ladder, a column standing), or
  the middle one (a wall panel or a sign standing on its edge). `--flip` turns
  the result upside down when the fixed views show it standing on its head;
- the model's longest principal axis is scaled to the size asked for, or with
  `--height` its height, the way a size given as a landmark on a person means;
- the model is centred on X and Y and stood on the floor (lowest point at 0).

Each mesh is welded where its export split vertices along texture seams, and
its small holes are filled: Pixal3D leaves missing triangles and slivers in
both its dense mesh and its own simplifications (the PR-04.2 crate's game
meshes had 9 to 58 open edges, visible near corners: specks, fins on edges
shared by three faces, and slits). `mend` below closes them in each game mesh (not the dense
mesh, which is only baked from); a hole is filled
only when it is small and has at most `--fill-holes` edges (64; 0 turns mending
off), and a larger opening is left, since it may be meant (a shade's free edge). Its materials and UVs are dropped (the game mesh is unwrapped and painted
afterwards), and it is saved as a .blend, which `uv-unwrap` and `bake-shape`
open directly. A JSON report records the transform and each file's extent.

Usage:
  blender -b --factory-startup --python scripts/blender/level_pair.py -- \\
      <length m> <report.json> <dense.glb> <dense.blend> [<low.glb> <low.blend>]... \\
      [--up shortest|middle|longest] [--flip] [--height] [--fill-holes 64]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from reference_asset_compiler.prop_quality import game_mesh_check


def components(bm):
    """The faces of a mesh in connected groups."""
    remaining, groups = set(bm.faces), []
    while remaining:
        seed = remaining.pop()
        group, stack = [seed], [seed]
        while stack:
            for edge in stack.pop().edges:
                for neighbour in edge.link_faces:
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        group.append(neighbour)
                        stack.append(neighbour)
        groups.append(group)
    return groups


def open_loops(bm):
    """The open edges of a mesh, in connected loops."""
    seen, loops = set(), []
    for edge in bm.edges:
        if not edge.is_boundary or edge in seen:
            continue
        loop, stack = [], [edge]
        while stack:
            item = stack.pop()
            if item in seen:
                continue
            seen.add(item)
            loop.append(item)
            for vertex in item.verts:
                stack.extend(other for other in vertex.link_edges if other.is_boundary and other not in seen)
        loops.append(loop)
    return loops


def wind_like_neighbours(bm, faces):
    for face in faces:
        for loop in face.loops:
            neighbour = next((other for other in loop.edge.link_loops if other.face is not face), None)
            if neighbour is not None:
                if neighbour.vert == loop.vert:
                    bmesh.ops.reverse_faces(bm, faces=[face])
                break


def mend(bm, size, limit):
    """Close the small holes Pixal3D leaves, and count what is left.

    In order: specks (loose bits under a hundred-thousandth of the surface)
    are dropped; zero-area faces dissolved; on an edge shared by more than two
    faces the smallest extra faces (fins) are dropped; open vertices closer
    than a thousandth of the model's size are welded, which zips cracks; then
    each open loop of at most `limit` edges is filled when it is small (its
    area under half a percent of the surface, or its perimeter under 15 % of
    the model's size), up to three passes. A larger opening is left open: it
    may be meant.
    """
    before = sum(1 for edge in bm.edges if edge.is_boundary)
    nonmanifold_before = sum(1 for edge in bm.edges if len(edge.link_faces) > 2)
    record = {"open_edges_before": before, "nonmanifold_edges_before": nonmanifold_before,
              "specks_dropped": 0, "fins_dropped": 0, "holes_filled": 0}
    if limit <= 0 or (before == 0 and nonmanifold_before == 0):
        record.update(open_edges_after=before, nonmanifold_edges_after=nonmanifold_before)
        return record
    surface = sum(face.calc_area() for face in bm.faces)
    specks = [face for group in components(bm) if sum(f.calc_area() for f in group) < surface * 1e-5
              for face in group]
    if specks:
        bmesh.ops.delete(bm, geom=specks, context="FACES")
    bmesh.ops.delete(bm, geom=[vertex for vertex in bm.verts if not vertex.link_faces], context="VERTS")
    bmesh.ops.dissolve_degenerate(bm, dist=size * 1e-5, edges=bm.edges[:])
    fins = set()
    for edge in bm.edges:
        if len(edge.link_faces) > 2:
            ranked = sorted(edge.link_faces, key=lambda face: face.calc_area())
            fins.update(ranked[:len(ranked) - 2])
    if fins:
        bmesh.ops.delete(bm, geom=list(fins), context="FACES")
    edge_verts = list({vertex for edge in bm.edges if edge.is_boundary for vertex in edge.verts})
    if edge_verts:
        bmesh.ops.remove_doubles(bm, verts=edge_verts, dist=size * 1e-3)
    filled = 0
    for _ in range(3):
        made = []
        for loop in open_loops(bm):
            if len(loop) > limit or not all(edge.is_valid for edge in loop):
                continue
            verts = list({vertex for edge in loop for vertex in edge.verts})
            centre = sum((vertex.co for vertex in verts), verts[0].co * 0) / len(verts)
            area = sum((edge.verts[0].co - centre).cross(edge.verts[1].co - centre).length / 2 for edge in loop)
            if area >= surface * 0.005 and sum(edge.calc_length() for edge in loop) >= size * 0.15:
                continue
            faces = bmesh.ops.holes_fill(bm, edges=loop, sides=0)["faces"]
            if not faces:
                try:
                    faces = bmesh.ops.contextual_create(bm, geom=loop)["faces"]
                except (RuntimeError, ValueError):
                    faces = []
            made += faces
        if not made:
            break
        wind_like_neighbours(bm, made)
        bmesh.ops.triangulate(bm, faces=[face for face in made if face.is_valid])
        filled += len(made)
    record.update(specks_dropped=len(specks), fins_dropped=len(fins), holes_filled=filled,
                  open_edges_after=sum(1 for edge in bm.edges if edge.is_boundary),
                  nonmanifold_edges_after=sum(1 for edge in bm.edges if len(edge.link_faces) > 2))
    return record


def load(path, sides=64):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError("{0} holds no mesh".format(path))
    bpy.ops.object.select_all(action="DESELECT")
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=max(obj.dimensions) * 1e-6)
    welded = before - len(bm.verts)
    mended = mend(bm, max(obj.dimensions), sides)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    for other in [item for item in bpy.data.objects if item.type != "MESH"]:
        bpy.data.objects.remove(other, do_unlink=True)
    obj.data.materials.clear()
    while obj.data.uv_layers:
        obj.data.uv_layers.remove(obj.data.uv_layers[0])
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj, welded, mended


UP_AXIS = {"shortest": (0, 1, 2), "middle": (0, 2, 1), "longest": (1, 2, 0)}
"""For each choice of up, which principal axes (longest first) become X, Y and Z."""


def box_axes(mesh, points):
    """Six broad, opposing planes give a box a steadier frame than vertex density."""
    normals = np.empty((len(mesh.polygons), 3), dtype=np.float32)
    areas = np.empty(len(normals), dtype=np.float32)
    mesh.polygons.foreach_get("normal", normals.ravel())
    mesh.polygons.foreach_get("area", areas)
    # A small normal histogram supplies candidates. Measure their support
    # against the original normals so bevels and noisy corners have little say.
    bins = np.clip(np.rint((normals + 1) * 8).astype(int), 0, 16)
    weights = np.bincount(bins @ np.array([289, 17, 1]), weights=areas, minlength=17**3)
    order = np.argsort(weights)[::-1]
    axes = []
    for index in order:
        if weights[index] == 0:
            break
        direction = np.array(np.unravel_index(index, (17, 17, 17)), dtype=float) / 8 - 1
        norm = np.linalg.norm(direction)
        if norm == 0:
            continue
        direction /= norm
        if any(abs(axis @ direction) > 0.18 for axis in axes):
            continue
        dots = normals @ direction
        near = np.abs(dots) > 0.98
        refined = (normals[near] * (areas[near] * np.sign(dots[near]))[:, None]).sum(axis=0)
        if np.linalg.norm(refined) < 1e-8:
            continue
        axes.append(refined / np.linalg.norm(refined))
        if len(axes) == 2:
            break
    if len(axes) < 2:
        return None
    x, y = axes
    z = np.cross(x, y)
    z /= np.linalg.norm(z)
    frame = np.array([x, np.cross(z, x), z])
    total = areas.sum()
    support = 0
    for axis in frame:
        projection = normals @ axis
        front, back = areas[projection > 0.98].sum(), areas[projection < -0.98].sum()
        if min(front, back) < 0.025 * total:
            return None
        support += front + back
    if support < 0.72 * total:
        return None
    return frame[np.argsort(np.ptp(points @ frame.T, axis=0))[::-1]]


def levelling_transform(points, length, up="shortest", flip=False, size_is="longest", rows=None):
    """Principal axes to X/Y/Z, open side up, longest axis (or the height) to `length`, centred, on the floor."""
    centre = points.mean(axis=0)
    if rows is None:
        _, _, rows = np.linalg.svd(points - centre, full_matrices=False)
    axes = rows[list(UP_AXIS[up])].copy()
    if np.linalg.det(axes) < 0:
        axes[2] *= -1
    local = (points - centre) @ axes.T
    height = local[:, 2]
    low, high = np.percentile(height, 5), np.percentile(height, 95)
    if np.ptp(local[height <= low, 1]) > np.ptp(local[height >= high, 1]):
        axes[2] *= -1
        axes[1] *= -1
    if flip:
        axes[2] *= -1
        axes[1] *= -1
    rotate = np.eye(4)
    rotate[:3, :3] = axes
    shift = np.eye(4)
    shift[:3, 3] = -centre
    turned = (np.c_[points, np.ones(len(points))] @ (rotate @ shift).T)[:, :3]
    extents = np.ptp(turned, axis=0)
    span = {"height": extents[2], "width": extents[0], "longest": max(extents)}[size_is]
    if not np.isfinite(span) or span <= 0:
        raise ValueError("The oriented mesh has no measurable " + size_is)
    scale = length / span
    turned *= scale
    place = np.eye(4)
    place[:3, 3] = [-(turned[:, 0].min() + turned[:, 0].max()) / 2,
                    -(turned[:, 1].min() + turned[:, 1].max()) / 2, -turned[:, 2].min()]
    size = np.eye(4) * scale
    size[3, 3] = 1.0
    return place @ size @ rotate @ shift


def main(argv) -> int:
    argv = list(argv)
    up, flip, size_is, sides = "shortest", False, "longest", 64
    topology = "legacy"
    if "--topology" in argv:
        at = argv.index("--topology")
        topology = argv[at + 1]
        if topology not in ("closed", "open"):
            raise ValueError("Topology must be closed or open")
        del argv[at:at + 2]
    if "--fill-holes" in argv:
        at = argv.index("--fill-holes")
        try:
            sides = int(argv[at + 1])
        except (IndexError, ValueError):
            sides = -1
        del argv[at:at + 2]
        if sides < 0:
            print("[LEVEL] FAILED: --fill-holes is how many edges a hole may have to be filled, 0 for none")
            return 1
    if "--height" in argv:
        argv.remove("--height")
        size_is = "height"
    if "--width" in argv:
        if size_is == "height":
            raise ValueError("Specify one sizing axis")
        argv.remove("--width")
        size_is = "width"
    if "--flip" in argv:
        argv.remove("--flip")
        flip = True
    if "--up" in argv:
        at = argv.index("--up")
        up = argv[at + 1] if at + 1 < len(argv) else ""
        del argv[at:at + 2]
        if up not in UP_AXIS:
            print("[LEVEL] FAILED: --up is shortest, middle or longest")
            return 1
    length, report_path = float(argv[0]), argv[1]
    pairs = list(zip(argv[2::2], argv[3::2]))
    if not pairs:
        print("[LEVEL] FAILED: expected <length> <report.json> <dense.glb> <dense.blend> [...]")
        return 1
    transform, records, alignment = None, [], "principal axes"
    for source, output in pairs:
        # The first file is the dense mesh: it is only baked from, the bake
        # copes with its holes, and mending a million faces takes minutes.
        obj, welded, mended = load(source, sides if records and topology != "open" else 0)
        points = np.array([vertex.co for vertex in obj.data.vertices], dtype=np.float64)
        if transform is None:
            rows = box_axes(obj.data, points) if topology == "closed" else None
            if rows is not None:
                alignment = "six opposing planes"
            transform = levelling_transform(points, length, up, flip, size_is, rows)
        obj.data.transform(Matrix(transform.tolist()))
        obj.data.update()
        obj.name = "GEO_" + bpy.path.display_name_from_filepath(output)
        bpy.ops.wm.save_as_mainfile(filepath=output)
        levelled = np.array([vertex.co for vertex in obj.data.vertices])
        records.append({"source": source, "output": output, "seam_copies_welded": int(welded), **mended,
                        "triangles": int(sum(len(p.vertices) - 2 for p in obj.data.polygons)),
                        "min_m": levelled.min(axis=0).round(4).tolist(),
                        "max_m": levelled.max(axis=0).round(4).tolist()})
        print("[LEVEL] {0}: {1} triangles, {2} seam copies welded, {3} holes filled, {4} open edges left".format(
            output, records[-1]["triangles"], welded, mended["holes_filled"], mended["open_edges_after"]))
    checks = [game_mesh_check(record, length, size_is, topology) for record in records[1:]] if topology != "legacy" else []
    with open(report_path, "w", encoding="utf-8") as stream:
        json.dump({"schema": "reference-asset-compiler.level-pair.v1", "length_m": length, "size_is": "longest side" if size_is == "longest" else size_is, "topology": topology, "up": up, "flip": flip, "fill_holes_up_to_edges": 0 if topology == "open" else sides,
                   "transform": np.round(transform, 8).tolist(), "alignment": alignment,
                   "files": records, "game_mesh_checks": checks}, stream, indent=2)
    for check in checks:
        if not check["ok"]:
            print("[LEVEL] FAILED: " + "; ".join(check["reasons"]))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []))
