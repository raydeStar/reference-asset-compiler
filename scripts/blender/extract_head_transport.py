"""Cut the head and neck out of a UV authority for a head-detail paint pass.

A full-body Hunyuan3D-Paint run at 512 px gives the head about fifty pixels per
view. Painting the head faces alone, with their exact existing UVs, fills each
view with the head. Because the UVs are untouched, the head paint lands in the
same atlas rectangles as the body paint and `composite_head_paint.py` can blend
it back over the body maps.

No vertex is moved and no UV is changed: the only operation is deleting every
face that is not entirely above the cut height. Export axes match
`prepare_texture_uv_transport.py` so the painter sees the head the same way up.

Usage:
  blender -b --factory-startup --python-exit-code 1 --python \
      scripts/blender/extract_head_transport.py -- \
      <uv-authority.blend> <output-dir> --z-cut <height in authority units> \
      [--uv-layer UV_RAC_AI_Paint]

Outputs: head-transport.obj/.mtl, head-authority.blend, head-uv-polygons.json
(UV outline of every kept polygon, for masks) and head-extraction.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def uv_islands(mesh, layer):
    """Island id per polygon, joining polygons that share a vertex at the same UV."""
    parent = {}

    def find(a):
        while parent.setdefault(a, a) != a:
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    seen = {}
    for poly in mesh.polygons:
        for loop in poly.loop_indices:
            uv = layer.data[loop].uv
            key = (mesh.loops[loop].vertex_index, round(uv.x, 5), round(uv.y, 5))
            if key in seen:
                union(poly.index, seen[key])
            else:
                seen[key] = poly.index
    islands = {}
    for poly in mesh.polygons:
        islands.setdefault(find(poly.index), []).append(poly.index)
    return list(islands.values())


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    source = Path(argv[0]).resolve()
    output = Path(argv[1]).resolve()
    z_cut = arg(argv, "--z-cut", None, float)
    layer_name = arg(argv, "--uv-layer", "UV_RAC_AI_Paint")
    if z_cut is None:
        raise RuntimeError("--z-cut is required: the lowest height (authority units) a kept face may touch")
    if output.exists():
        raise RuntimeError("Head transport output must be a fresh directory: {0}".format(output))

    bpy.ops.wm.open_mainfile(filepath=str(source))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError("Expected one isolated mesh in the UV authority")
    obj = meshes[0]
    mesh = obj.data
    layer = mesh.uv_layers[layer_name]

    head = {p.index for p in mesh.polygons if min(mesh.vertices[v].co.z for v in p.vertices) > z_cut}
    if not head or len(head) == len(mesh.polygons):
        raise RuntimeError("The cut keeps {0} of {1} faces; choose a height inside the mesh".format(
            len(head), len(mesh.polygons)))
    outlines = [[[layer.data[loop].uv.x, layer.data[loop].uv.y] for loop in mesh.polygons[i].loop_indices]
                for i in sorted(head)]
    islands = uv_islands(mesh, layer)
    mixed = [(len(f), sum(1 for i in f if i in head)) for f in islands
             if 0 < sum(1 for i in f if i in head) < len(f)]
    head_only = sum(1 for f in islands if all(i in head for i in f))

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in head], context="FACES")
    head_mesh = bpy.data.meshes.new("HEAD")
    bm.to_mesh(head_mesh)
    bm.free()
    head_obj = bpy.data.objects.new("GEO_RAC_HeadTransport", head_mesh)
    bpy.context.scene.collection.objects.link(head_obj)
    for other in list(bpy.data.objects):
        if other is not head_obj:
            bpy.data.objects.remove(other, do_unlink=True)
    bpy.ops.object.select_all(action="DESELECT")
    head_obj.select_set(True)
    bpy.context.view_layer.objects.active = head_obj
    head_mesh.uv_layers[0].name = layer_name
    head_mesh.materials.append(bpy.data.materials.new("M_RAC_HeadTransport"))

    output.mkdir(parents=True)
    bpy.ops.wm.obj_export(filepath=str(output / "head-transport.obj"), export_selected_objects=True,
                          export_materials=True, export_uv=True, export_normals=True,
                          export_triangulated_mesh=True, forward_axis="NEGATIVE_Z", up_axis="Y")
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "head-authority.blend"))
    heights = [v.co.z for v in head_mesh.vertices]
    report = {
        "schema": "reference-asset-compiler.head-transport-extraction.v1",
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "uv_layer": layer_name,
        "z_cut_authority_units": z_cut,
        "source_polygons": len(mesh.polygons),
        "head_polygons": len(head),
        "head_vertices": len(head_mesh.vertices),
        "head_triangles": sum(len(p.vertices) - 2 for p in head_mesh.polygons),
        "head_z_range": [min(heights), max(heights)],
        "uv_islands_total": len(islands),
        "uv_islands_head_only": head_only,
        "uv_islands_mixed_head_body": mixed,
        "operation": "delete non-head faces only; vertices and UVs untouched; "
                     "export axes identical to texture-transport.obj",
    }
    (output / "head-extraction.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "head-uv-polygons.json").write_text(json.dumps(outlines))
    print("HEAD_EXTRACT_OK", json.dumps({k: v for k, v in report.items() if k != "source"}))


if __name__ == "__main__":
    main()
