"""Conform an existing retopology to its AI-acquired source, preserving connectivity."""
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from reduce_regional_autoremesher import object_topology


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source, candidate, destination = map(Path, sys.argv[sys.argv.index("--") + 1:])
    source, candidate, destination = source.resolve(), candidate.resolve(), destination.resolve()
    if destination.exists():
        raise RuntimeError("A surface projection must use a new candidate directory")
    destination.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    dense = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    vertices, faces = [], []
    for obj in dense:
        offset = len(vertices)
        vertices.extend(obj.matrix_world @ v.co for v in obj.data.vertices)
        faces.extend(tuple(i + offset for i in p.vertices) for p in obj.data.polygons)
    target = BVHTree.FromPolygons(vertices, faces)
    # Load native quads, not GLB's triangulated display transport.
    with bpy.data.libraries.load(str(candidate), link=False) as (available, selected):
        selected.objects = [name for name in available.objects if name.startswith("GEO_RAC_")]
    if len(selected.objects) != 1:
        raise RuntimeError("One unambiguous native retopology candidate is required")
    obj = selected.objects[0]
    bpy.context.collection.objects.link(obj)
    for other in list(bpy.context.scene.objects):
        if other != obj:
            bpy.data.objects.remove(other, do_unlink=True)
    before = object_topology(obj)
    connectivity = [tuple(p.vertices) for p in obj.data.polygons]
    inverse = obj.matrix_world.inverted()
    distances = []
    height = max(v.z for v in vertices) - min(v.z for v in vertices)
    limit = height * .035
    for vert in obj.data.vertices:
        world = obj.matrix_world @ vert.co
        nearest, normal, index, distance = target.find_nearest(world)
        if nearest is None or distance > limit:
            raise RuntimeError("Retopology exceeds the bounded source-projection envelope")
        distances.append(distance)
        vert.co = inverse @ nearest
    obj.data.update()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(obj.data)
    bm.free()
    after = object_topology(obj)
    if before != after or [tuple(p.vertices) for p in obj.data.polygons] != connectivity:
        raise RuntimeError("Source projection changed topology or winding; retain diagnostic only")
    if after["triangles"] > 20000 or after["vertices"] > 15000 or after["quad_fraction"] < .8:
        raise RuntimeError("Projected topology fails the character budget")
    obj.name = "GEO_RAC_ProjectedCandidate"
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    native = destination / "projected.blend"
    transport = destination / "projected.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    bpy.ops.export_scene.gltf(filepath=str(transport), export_format="GLB",
                              use_selection=True, export_materials="NONE")
    distances.sort()
    report = {"schema": "reference-asset-compiler.production-retopology-candidate.v1",
        "status": "mechanical_pass", "backend": "AutoRemesher then bounded source-surface projection",
        "source": {"path": str(source), "sha256": digest(source)},
        "retopology_parent": {"path": str(candidate), "sha256": digest(candidate)},
        "output": {"path": str(native), "sha256": digest(native), **after},
        "transport": {"path": str(transport), "sha256": digest(transport)},
        "projection": {"maximum_displacement_m": max(distances),
                       "p95_displacement_m": distances[int(.95 * (len(distances) - 1))],
                       "maximum_allowed_m": limit, "connectivity_unchanged": True},
        "failures": [], "production_grade": False, "requires_fixed_view_review": True}
    (destination / "reduction-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("SURFACE_PROJECTION_READY -- the topology follows the evidence, not my imagination.")


if __name__ == "__main__":
    main()
