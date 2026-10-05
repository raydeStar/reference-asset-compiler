"""Turn acquired hair strands into a game hair shell.

Image-to-3D hair comes out as hundreds of separate tubes with gaps, floating
fragments and bridges: unpaintable, unskinnable and far over budget. A
painted character's hair reads as a mass of clumps. This builds that mass as
a signed-distance volume (Blender's OpenVDB grid nodes): every strand point
and every point of a cap lifted off the covered scalp becomes a sphere, the
union is re-distanced and eroded back (a morphological closing, so the gaps
between strands fill while the silhouette stays the acquisition's), smoothed,
meshed, reduced to a budget and unwrapped for the paint bake.

Usage:
  blender -b --factory-startup --python scripts/blender/build_hair_shell.py -- \
      <hair.npz> <out.glb> <out.npz> [--radius 0.008] [--erode 0.005]
      [--voxel 0.0025] [--triangles 24000]
"""

from __future__ import annotations

import argparse
import sys

import bpy
import numpy as np


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("hair")
    p.add_argument("out_glb")
    p.add_argument("out_npz")
    p.add_argument("--radius", type=float, default=0.008, help="sphere per strand point")
    p.add_argument("--erode", type=float, default=0.005, help="pulled back after the union")
    p.add_argument("--voxel", type=float, default=0.0025)
    p.add_argument("--smooth", type=int, default=3)
    p.add_argument("--triangles", type=int, default=24000)
    p.add_argument("--stride", type=int, default=2, help="use every n-th strand vertex")
    return p.parse_args(argv)


def apply(ob, mod):
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)


def run_nodes(ob, build):
    ng = bpy.data.node_groups.new("shell", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi = ng.nodes.new("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    ng.links.new(build(ng, gi.outputs[0]), go.inputs[0])
    mod = ob.modifiers.new("shell", "NODES")
    mod.node_group = ng
    apply(ob, mod)


def node(ng, kind, **inputs):
    n = ng.nodes.new(kind)
    for name, value in inputs.items():
        sock = n.inputs[name]
        if hasattr(value, "is_output"):
            ng.links.new(value, sock)
        else:
            sock.default_value = value
    return n


def bounds(ob):
    v = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    return v.min(0), v.max(0)


def main():
    a = _args()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    z = np.load(a.hair)
    pts = np.concatenate([z["verts"][:: a.stride], z["cap_points"]]).astype(np.float64)
    me = bpy.data.meshes.new("hair")
    me.vertices.add(len(pts))
    me.vertices.foreach_set("co", pts.ravel())
    me.update()
    ob = bpy.data.objects.new("hair", me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)

    # 1. Union of spheres: strands fuse wherever they are closer than 2 * radius.
    def union(ng, geo):
        p = node(ng, "GeometryNodeMeshToPoints", Mesh=geo)
        g = node(ng, "GeometryNodePointsToSDFGrid", Points=p.outputs[0], Radius=a.radius,
                 **{"Voxel Size": a.voxel})
        return node(ng, "GeometryNodeGridToMesh", Grid=g.outputs[0], Threshold=0.0).outputs[0]
    run_nodes(ob, union)
    lo1, hi1 = bounds(ob)

    # 2. Re-distance the union and erode it: gaps stay filled, the outside
    #    comes back toward the strands, then a light smoothing pass.
    def close(ng, geo, sign):
        g = node(ng, "GeometryNodeMeshToSDFGrid", Mesh=geo, **{"Voxel Size": a.voxel,
                                                               "Band Width": 6})
        g = node(ng, "GeometryNodeSDFGridOffset", Grid=g.outputs[0], Distance=sign * a.erode)
        g = node(ng, "GeometryNodeSDFGridMean", Grid=g.outputs[0], Width=1, Iterations=a.smooth)
        return node(ng, "GeometryNodeGridToMesh", Grid=g.outputs[0], Threshold=0.0).outputs[0]
    keep = ob.data.copy()
    run_nodes(ob, lambda ng, geo: close(ng, geo, -1.0))
    lo2, hi2 = bounds(ob)
    if (hi2 - lo2).sum() > (hi1 - lo1).sum():
        # The offset convention grew the surface; erode the other way.
        ob.data = keep
        run_nodes(ob, lambda ng, geo: close(ng, geo, 1.0))
        lo2, hi2 = bounds(ob)
    print("union extent", np.round(hi1 - lo1, 4), "closed extent", np.round(hi2 - lo2, 4))

    tris_now = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    if tris_now > a.triangles:
        m = ob.modifiers.new("budget", "DECIMATE")
        m.ratio = a.triangles / tris_now
        apply(ob, m)
    m = ob.modifiers.new("tri", "TRIANGULATE")
    apply(ob, m)

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")
    for poly in ob.data.polygons:
        poly.use_smooth = True

    me = ob.data
    v = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", v)
    loops = np.empty(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", loops)
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    np.savez_compressed(a.out_npz, verts=v.reshape(-1, 3), tris=loops.reshape(-1, 3),
                        loop_uv=uv.reshape(-1, 2))
    bpy.ops.export_scene.gltf(filepath=a.out_glb, export_format="GLB", use_selection=False)
    print("hair shell", len(me.vertices), "verts", len(me.polygons), "tris ->", a.out_glb)


main()
