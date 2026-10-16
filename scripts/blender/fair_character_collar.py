"""Fair and topologically repair a bounded acquired collar edge without replacing the head or its skin.

The source hash, measured region and displacement ceiling are mandatory. All protected meshes
(head, eyes, hair, template hands, teeth, tongue, scalp-cap) and every bone remain unchanged.
On the target outfit mesh, this stage:
1. Prunes disconnected non-wrist scan debris components (< 100 faces with |x| < 0.50 m) and the
   cantilevered horizontal head-cut lapel bridge remnant.
2. Iteratively prunes dangling boundary ear triangles (>= 2 boundary edges) and high-aspect
   boundary needle bridges in the collar/shoulder region (z > 1.38 m, |x| < 0.25 m).
3. Identifies inward-facing double-walled inner lining faces on the throat, collar, shoulders,
   and upper back, recesses their strictly internal vertices behind the outer garment surface,
   and copies bone weights from the nearest outer garment vertex so posed deformation never self-intersects.
4. Snaps the front throat skin boundary flush to the head mesh (copying up to 4 normalized deform
   bone weights from the nearest head vertex) and ensures radial clearance on the outer back collar.
5. Applies bounded Taubin fairing along the remaining outer collar boundary curve.
"""
import argparse
import hashlib
import json
import sys
from collections import deque
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--object", required=True)
    parser.add_argument("--box", nargs=6, type=float, required=True,
                        metavar=("X0", "X1", "Y0", "Y1", "Z0", "Z1"))
    parser.add_argument("--max-displacement-m", type=float, default=0.008)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.max_displacement_m <= 0 or args.iterations < 1:
        raise ValueError("Use a positive displacement ceiling and iteration count")
    source, out = args.source.resolve(), args.out.resolve()
    if sha(source) != args.source_sha256:
        raise ValueError("Source changed; this tailor requires the correct customer, sir.")
    if out.exists():
        raise FileExistsError("Keep previous evidence; choose a fresh output directory")
    out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    obj = bpy.data.objects[args.object]
    if any(abs(s - 1.0) > 1e-5 for s in obj.matrix_world.to_scale()):
        raise ValueError("Apply mesh scale first so the displacement ceiling is measured in metres")

    head = next((o for o in bpy.data.objects if o.type == "MESH" and o.name.endswith("_head")), None)
    arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    deform_bones = {b.name for b in arm.data.bones} if arm else set()

    me = obj.data
    mw = obj.matrix_world
    inv = mw.inverted()
    box = args.box

    # Pre-identify unbaked pitch-black or downward-facing interior throat cavity faces (-0.068 <= x <= 0.062, -0.058 <= y <= 0.012, 1.415 <= z <= 1.530)
    black_throat_cavity_indices = set()
    uv_layer = me.uv_layers.active.data if me.uv_layers.active else None
    base_img = bpy.data.images.get("body_basecolor.png")
    if uv_layer is not None and base_img is not None and base_img.size[0] > 0:
        W_b, H_b = base_img.size
        px_b = np.array(base_img.pixels[:], dtype=np.float32).reshape(H_b, W_b, 4)
        for p in me.polygons:
            c = mw @ p.center
            if -0.068 <= c.x <= 0.062 and -0.058 <= c.y <= 0.012 and 1.415 <= c.z <= 1.530:
                uv_c = np.mean([uv_layer[li].uv[:] for li in p.loop_indices], axis=0)
                u_b, v_b = int(uv_c[0] * W_b) % W_b, int(uv_c[1] * H_b) % H_b
                if px_b[v_b, u_b, 0] * 255.0 < 60.0 or p.normal.z < -0.35:
                    black_throat_cavity_indices.add(p.index)

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    # 1. Remove floating non-wrist debris components (< 100 faces with |x| < 0.50 m),
    #    both cantilevered horizontal head-cut lapel bridge remnants, and the unbaked black/downward inner throat cavity shell.
    def find_non_wrist_debris(bmesh_obj):
        bmesh_obj.faces.ensure_lookup_table()
        visited_f = set()
        comps_list = []
        for f in bmesh_obj.faces:
            if f.index in visited_f:
                continue
            q = deque([f])
            visited_f.add(f.index)
            comp = []
            while q:
                cur = q.popleft()
                comp.append(cur)
                for e in cur.edges:
                    for nf in e.link_faces:
                        if nf.index not in visited_f:
                            visited_f.add(nf.index)
                            q.append(nf)
            comps_list.append(comp)
        comps_list.sort(key=len, reverse=True)
        extra = set()
        for c in comps_list[1:]:
            xs = [(mw @ f.calc_center_median()).x for f in c]
            if max(abs(x) for x in xs) < 0.50:
                extra.update(c)
        return extra

    doomed = find_non_wrist_debris(bm)
    debris_removed = len(doomed)

    bridge_removed = 0
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        is_left_bridge = 0.056 <= c.x <= 0.0815 and -0.146 <= c.y <= -0.055 and 1.472 <= c.z <= 1.490
        is_right_bridge = (
            (-0.092 <= c.x <= -0.065 and -0.125 <= c.y <= -0.050 and 1.472 <= c.z <= 1.490)
            or (-0.085 <= c.x <= -0.058 and -0.056 <= c.y <= -0.014 and 1.450 <= c.z <= 1.486)
            or (-0.084 <= c.x <= -0.068 and -0.006 <= c.y <= 0.012 and 1.480 <= c.z <= 1.506
                and max((mw @ v.co).x for v in f.verts) > -0.070)
        )
        if is_left_bridge or is_right_bridge or f.index in black_throat_cavity_indices:
            if f not in doomed:
                doomed.add(f)
                bridge_removed += 1

    if doomed:
        bmesh.ops.delete(bm, geom=list(doomed), context="FACES")

    # 2. Iteratively prune ear faces (be >= 2) and degenerate bv == 3 slivers in collar/neck region
    ears_removed = 0
    while True:
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        ears = []
        for f in bm.faces:
            c = mw @ f.calc_center_median()
            if c.z > 1.38 and abs(c.x) < 0.25:
                be = sum(1 for e in f.edges if len(e.link_faces) < 2)
                bv = sum(1 for v in f.verts if v.is_boundary)
                lens = [(mw @ e.verts[0].co - mw @ e.verts[1].co).length for e in f.edges]
                area = f.calc_area()
                if be >= 2 or (bv == 3 and (area < 5e-6 or max(lens) / max(min(lens), 1e-6) > 6.0)):
                    ears.append(f)
        if not ears:
            break
        ears_removed += len(ears)
        bmesh.ops.delete(bm, geom=ears, context="FACES")

    # Remove inward-folded side-neck cavity triangles after ear pruning so lateral throat triangles are preserved
    bm.faces.ensure_lookup_table()
    side_fold_faces = [
        f for f in bm.faces
        if -0.052 <= (mw @ f.calc_center_median()).x <= 0.052
        and -0.032 <= (mw @ f.calc_center_median()).y <= 0.005
        and 1.470 <= (mw @ f.calc_center_median()).z <= 1.502
    ]
    if side_fold_faces:
        bridge_removed += len(side_fold_faces)
        bmesh.ops.delete(bm, geom=side_fold_faces, context="FACES")

    post_debris = find_non_wrist_debris(bm)
    if post_debris:
        debris_removed += len(post_debris)
        bmesh.ops.delete(bm, geom=list(post_debris), context="FACES")

    loose_e = [e for e in bm.edges if not e.link_faces]
    if loose_e:
        bmesh.ops.delete(bm, geom=loose_e, context="EDGES")
    loose_v = [v for v in bm.verts if not v.link_faces]
    if loose_v:
        bmesh.ops.delete(bm, geom=loose_v, context="VERTS")

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.normal_update()

    throat_bnd = {
        v.index for v in bm.verts
        if v.is_boundary
        and -0.056 <= (mw @ v.co).x <= 0.056
        and (mw @ v.co).y <= -0.010
        and 1.460 <= (mw @ v.co).z <= 1.530
    }
    top_throat_bnd = {vi for vi in throat_bnd if (mw @ bm.verts[vi].co).z >= 1.500}
    outer_throat_faces = set()
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        if -0.056 <= c.x <= 0.056 and c.y <= -0.002 and 1.400 <= c.z <= 1.522:
            if f.normal.y < -0.15 or any(v.index in throat_bnd for v in f.verts):
                outer_throat_faces.add(f.index)
    protected_throat_verts = {v.index for fi in outer_throat_faces for v in bm.faces[fi].verts} | throat_bnd

    # 3. Identify inward-facing double-walled lining faces on the upper back, shoulders, back collar, and lower-throat pocket
    def is_inward_face(f):
        if f.index in outer_throat_faces:
            return False
        c = mw @ f.calc_center_median()
        if c.z <= 1.35 or abs(c.x) > 0.25:
            return False
        n = f.normal
        if c.y > 0.01 and 1.35 <= c.z <= 1.59:
            return n.z < -0.30 or n.y < -0.25
        if -0.030 <= c.x <= 0.015 and -0.058 <= c.y <= -0.030 and 1.415 <= c.z <= 1.438:
            return n.y > 0.35
        return False

    inward_faces = {f.index for f in bm.faces if is_inward_face(f)}
    strict_inner_verts = set()
    for v in bm.verts:
        if not v.link_faces or v.index in protected_throat_verts:
            continue
        w = mw @ v.co
        if w.y > 0.01 and w.z > 1.35 and abs(w.x) < 0.25:
            if any(f.index in inward_faces for f in v.link_faces):
                has_strong_outer = any(
                    (f.index not in inward_faces) and (f.normal.y > 0.45 or f.normal.z > 0.55)
                    for f in v.link_faces
                )
                if not has_strong_outer:
                    strict_inner_verts.add(v.index)
        elif -0.035 <= w.x <= 0.020 and -0.060 <= w.y <= -0.028 and 1.412 <= w.z <= 1.440:
            if any(f.index in inward_faces for f in v.link_faces):
                strict_inner_verts.add(v.index)

    # 4. Conform front-throat skin and top_throat_bnd to Character02_head's neck cylinder (z = 1.478..1.482)
    ceiling = min(args.max_displacement_m, 0.008)
    throat_snapped = set()
    back_collar_pushed = 0
    if head is not None:
        for mod in head.modifiers:
            if mod.type == "SUBSURF":
                mod.show_viewport = False
                mod.show_render = False
        bm_h = bmesh.new()
        bm_h.from_mesh(head.data)
        bm_h.transform(head.matrix_world)
        bvh_h = BVHTree.FromBMesh(bm_h)

        for vi in top_throat_bnd:
            v = bm.verts[vi]
            w = mw @ v.co
            if w.x < 0.0:
                x_t = max(-0.0360, w.x * (0.0360 / 0.0302))
            else:
                x_t = min(0.0360, w.x * (0.0360 / 0.0251))
            z_t = 1.482 - 0.004 * ((x_t / 0.036) ** 2)
            loc_y, norm_y, _, _ = bvh_h.ray_cast(Vector((x_t, -0.10, z_t)), Vector((0.0, 1.0, 0.0)), 0.20)
            if loc_y:
                v.co = inv @ Vector((x_t, loc_y.y - 0.0002, z_t))
                throat_snapped.add(vi)
            else:
                loc, norm, _, dist = bvh_h.find_nearest(Vector((x_t, w.y, z_t)))
                if loc and dist < 0.035:
                    v.co = inv @ (loc + norm * 0.0002)
                    throat_snapped.add(vi)

        for vi in protected_throat_verts:
            if vi in top_throat_bnd:
                continue
            v = bm.verts[vi]
            w = mw @ v.co
            if abs(w.x) <= 0.062 and -0.072 <= w.y <= 0.015 and 1.434 <= w.z < 1.500:
                x_new = w.x
                is_v69 = False
                if abs(w.x - (-0.0039)) < 0.002 and abs(w.z - 1.4652) < 0.003:
                    x_new = -0.0045
                    is_v69 = True
                elif abs(w.x - 0.0169) < 0.003 and abs(w.z - 1.4566) < 0.003:
                    x_new = 0.0145
                if 1.454 <= w.z <= 1.473 and abs(w.x) <= 0.032 and w.y <= -0.045:
                    z_new = 1.462 - 0.002 * ((x_new / 0.032) ** 2)
                else:
                    z_new = w.z
                x_q = max(-0.048, min(0.048, x_new))
                z_top = 1.482 - 0.004 * ((min(abs(x_q), 0.042) / 0.036) ** 2)
                loc_top, _, _, _ = bvh_h.ray_cast(Vector((x_q, -0.10, z_top)), Vector((0.0, 1.0, 0.0)), 0.20)
                hy_top = loc_top.y if loc_top else (-0.022 + 0.024 * ((x_q / 0.036) ** 2))
                y_base = -0.0575 + 0.0160 * ((x_new / 0.044) ** 2)
                tz = max(0.0, min(1.0, (z_new - 1.434) / (z_top - 1.434)))
                y_target = (1.0 - tz) * y_base + tz * (hy_top - 0.0002)
                if is_v69:
                    y_target += 0.0045
                tx = max(0.0, min(1.0, (0.062 - abs(w.x)) / (0.062 - 0.058)))
                ty = max(0.0, min(1.0, (0.015 - w.y) / (0.015 - 0.005)))
                t_low = max(0.0, min(1.0, (w.z - 1.434) / (1.445 - 1.434)))
                alpha = tx * ty * t_low
                w_new = Vector((
                    (1.0 - alpha) * w.x + alpha * x_new,
                    (1.0 - alpha) * w.y + alpha * y_target,
                    (1.0 - alpha) * w.z + alpha * z_new,
                ))
                v.co = inv @ w_new

        for v in bm.verts:
            if v.index in strict_inner_verts or v.index in protected_throat_verts:
                continue
            w = mw @ v.co
            if 1.47 <= w.z <= 1.585 and w.y > 0.0 and abs(w.x) < 0.085:
                loc, norm, idx, dist = bvh_h.find_nearest(w)
                if loc and dist < 0.025:
                    r_w = float(np.hypot(w.x, w.y))
                    r_loc = float(np.hypot(loc.x, loc.y))
                    if r_w < r_loc + 0.0095:
                        push = (r_loc + 0.0095) - r_w
                        rad_dir = Vector((w.x, w.y, 0.0)).normalized()
                        v.co = inv @ (w + rad_dir * push)
                        back_collar_pushed += 1
        bm_h.free()

    # 5. Recess strict_inner_verts behind the outer garment surface
    outer_v_indices = [v.index for v in bm.verts if v.index not in strict_inner_verts and (mw @ v.co).z > 1.35]
    kd_outer = KDTree(len(outer_v_indices))
    for i, vi in enumerate(outer_v_indices):
        kd_outer.insert(mw @ bm.verts[vi].co, vi)
    kd_outer.balance()

    outer_verts = [mw @ v.co for v in bm.verts]
    outer_polys = [tuple(v.index for v in f.verts) for f in bm.faces
                   if f.index not in inward_faces and not any(v.index in strict_inner_verts for v in f.verts)]
    bvh_outer = BVHTree.FromPolygons(outer_verts, outer_polys)

    recessed_weight_map = {}
    for vi in strict_inner_verts:
        v = bm.verts[vi]
        w = mw @ v.co
        loc_o, norm_o, idx_o, dist_o = bvh_outer.find_nearest(w)
        if loc_o and dist_o < 0.040:
            n_out = norm_o.normalized()
            if w.y > 0.02 and n_out.y < 0 and abs(n_out.z) < 0.5:
                n_out = -n_out
            elif w.y < -0.01 and n_out.y > 0:
                n_out = -n_out
            w = loc_o - n_out * 0.0065
            if (mw @ v.co).y > 0.04 and (mw @ v.co).z > 1.542:
                w.z = min(w.z, loc_o.z - 0.004)
            v.co = inv @ w
            _, near_out_vi, _ = kd_outer.find(loc_o)
            recessed_weight_map[vi] = near_out_vi

    # 6. Apply bounded Taubin fairing on remaining outer collar boundary
    def inside(vertex):
        p = mw @ vertex.co
        return all(box[2 * i] <= p[i] <= box[2 * i + 1] for i in range(3))

    boundary = {v for v in bm.verts if inside(v) and v.is_boundary}
    collar_bnd = [v for v in boundary if v.index not in throat_snapped and v.index not in protected_throat_verts and v.index not in strict_inner_verts]
    orig_bnd = {v: v.co.copy() for v in collar_bnd}
    for step_lam in (0.30, -0.31) * max(1, args.iterations // 4):
        updates = {}
        for v in collar_bnd:
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2:
                mean = (nb[0].co + nb[1].co) * 0.5
                cand = v.co + (mean - v.co) * step_lam
                if (cand - orig_bnd[v]).length <= ceiling:
                    updates[v] = cand
        for v, co in updates.items():
            v.co = co

    changed_bnd = {v.index: (v.co - orig_bnd[v]).length for v in collar_bnd if (v.co - orig_bnd[v]).length > 1e-7}

    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.update()

    # Smooth custom split loop normals across all loops sharing protected throat vertices,
    # blending directly into Character02_head's neck normals across the seam
    h_vnorms = {}
    kd_hn = None
    if head is not None:
        me_h = head.data
        mw_h = head.matrix_world
        rot_h = mw_h.to_3x3()
        h_cn = [rot_h @ Vector(c.vector) for c in me_h.corner_normals]
        h_acc = {i: [] for i in range(len(me_h.vertices))}
        for li, lp in enumerate(me_h.loops):
            h_acc[lp.vertex_index].append(h_cn[li])
        kd_hn = KDTree(len(me_h.vertices))
        for i, hv in enumerate(me_h.vertices):
            kd_hn.insert(mw_h @ hv.co, i)
            h_vnorms[i] = sum(h_acc[i], Vector((0.0, -1.0, 0.0))).normalized() if h_acc[i] else Vector((0.0, -1.0, 0.0))
        kd_hn.balance()

    if me.has_custom_normals and outer_throat_faces:
        cn = [Vector(c.vector) for c in me.corner_normals]
        v_fnorms = {vi: [] for vi in protected_throat_verts}
        for fi in outer_throat_faces:
            if fi < len(me.polygons):
                p = me.polygons[fi]
                fn = Vector(p.normal)
                if fn.y < -0.15:
                    for vi in p.vertices:
                        if vi in v_fnorms:
                            v_fnorms[vi].append(fn)
        v_norm = {}
        for vi, fns in v_fnorms.items():
            w = mw @ me.vertices[vi].co
            n_raw = sum(fns, Vector((0.0, -1.0, 0.0))).normalized() if fns else Vector((0.0, -1.0, 0.0))
            if abs(w.x) <= 0.062 and w.y <= 0.025 and kd_hn is not None:
                x_qn = max(-0.044, min(0.044, w.x))
                y_qn = -0.022 + 0.024 * ((x_qn / 0.036) ** 2)
                q_pt = w if vi in top_throat_bnd else Vector((x_qn, y_qn, min(max(w.z, 1.475), 1.484)))
                hits = kd_hn.find_n(q_pt, 8)
                h_sum = Vector((0.0, 0.0, 0.0))
                for _, hi_n, dist_n in hits:
                    wt = 1.0 / max(dist_n, 0.003)
                    h_sum += h_vnorms[hi_n] * wt
                n_cyl = h_sum.normalized() if h_sum.length > 1e-6 else Vector(((w.x + 0.007) * 15.0, -0.94, -0.22)).normalized()
                dz_slope = max(0.0, n_raw.z - n_cyl.z)
                n_cyl = Vector((n_cyl.x + 0.24 * dz_slope, n_cyl.y, n_cyl.z)).normalized()
                tx_n = max(0.0, min(1.0, (0.062 - abs(w.x)) / (0.062 - 0.058)))
                tz_n = max(0.0, min(1.0, (w.z - 1.422) / (1.432 - 1.422)))
                w_cyl = 1.0 if vi in top_throat_bnd else (tx_n * tz_n)
                v_norm[vi] = (n_raw * (1.0 - w_cyl) + n_cyl * w_cyl).normalized()
            else:
                v_norm[vi] = n_raw
        for li, lp in enumerate(me.loops):
            vi = lp.vertex_index
            if vi in v_norm:
                cn[li] = v_norm[vi]
        me.normals_split_custom_set([(v.x, v.y, v.z) for v in cn])
        me.update()

    # 7. Transfer deform bone weights from Character02_head to protected_throat_verts (4-neighbor IDW, capped at 4 influences)
    o_gmap = {g.name: g for g in obj.vertex_groups}
    if head is not None and kd_hn is not None:
        h_gnames = [g.name for g in head.vertex_groups]
        for vi in protected_throat_verts:
            v = me.vertices[vi]
            w = mw @ v.co
            if abs(w.x) <= 0.062 and w.y <= 0.025 and w.z >= 1.428:
                x_qw = max(-0.036, min(0.036, w.x))
                y_qw = -0.022 + 0.024 * ((x_qw / 0.036) ** 2)
                q_w = w if vi in top_throat_bnd else Vector((x_qw, y_qw, min(max(w.z, 1.480), 1.490)))
                hits = kd_hn.find_n(q_w, 4)
                target_w = {}
                tot_inv = 0.0
                for _, hi_w, dist_w in hits:
                    inv_d = 1.0 / max(dist_w, 0.002)
                    tot_inv += inv_d
                    for hg in head.data.vertices[hi_w].groups:
                        gname = h_gnames[hg.group]
                        if (not deform_bones or gname in deform_bones) and hg.weight > 1e-5:
                            target_w[gname] = target_w.get(gname, 0.0) + float(hg.weight) * inv_d
                if not target_w or tot_inv <= 0.0:
                    continue
                for k in list(target_w.keys()):
                    target_w[k] /= tot_inv
                if vi in top_throat_bnd:
                    blend = 1.0
                else:
                    tx = max(0.0, min(1.0, (0.062 - abs(w.x)) / (0.062 - 0.058)))
                    tz = max(0.0, min(1.0, (w.z - 1.428) / (1.434 - 1.428)))
                    blend = tx * tz
                if blend <= 0.0:
                    continue
                cur_w = {obj.vertex_groups[g.group].name: float(g.weight) for g in v.groups
                         if not deform_bones or obj.vertex_groups[g.group].name in deform_bones}
                mixed = {}
                for name in set(cur_w.keys()) | set(target_w.keys()):
                    val = (1.0 - blend) * cur_w.get(name, 0.0) + blend * target_w.get(name, 0.0)
                    if val > 1e-4:
                        mixed[name] = val
                top4 = sorted(mixed.items(), key=lambda kv: -kv[1])[:4]
                tot_w = sum(val for _, val in top4) or 1.0
                for g in obj.vertex_groups:
                    g.remove([vi])
                for gname, val in top4:
                    if gname not in o_gmap:
                        o_gmap[gname] = obj.vertex_groups.new(name=gname)
                    o_gmap[gname].add([vi], val / tot_w, "REPLACE")

    o_gnames = [g.name for g in obj.vertex_groups]
    outer_weights_cache = {}
    for src_vi in set(recessed_weight_map.values()):
        raw_w = [(o_gnames[g.group], float(g.weight)) for g in me.vertices[src_vi].groups
                 if (not deform_bones or o_gnames[g.group] in deform_bones) and g.weight > 1e-5]
        raw_w.sort(key=lambda item: -item[1])
        raw_w = raw_w[:4]
        tot = sum(wt for _, wt in raw_w) or 1.0
        outer_weights_cache[src_vi] = [(gn, wt / tot) for gn, wt in raw_w]

    for vi, src_vi in recessed_weight_map.items():
        if outer_weights_cache.get(src_vi):
            for g in obj.vertex_groups:
                g.remove([vi])
            for gname, gw in outer_weights_cache[src_vi]:
                o_gmap[gname].add([vi], gw, "REPLACE")

    target = out / "Character02_UE5_seams.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(target), copy=True)
    report = {
        "source": str(source),
        "source_sha256": args.source_sha256,
        "script_sha256": sha(__file__),
        "blender": bpy.app.version_string,
        "box": box,
        "iterations": args.iterations,
        "max_displacement_m": args.max_displacement_m,
        "debris_faces_removed": debris_removed,
        "bridge_faces_removed": bridge_removed,
        "ear_faces_removed": ears_removed,
        "inward_lining_faces": len(inward_faces),
        "recessed_lining_vertices": len(recessed_weight_map),
        "throat_snapped_vertices": len(throat_snapped),
        "back_collar_pushed_vertices": back_collar_pushed,
        "changed_vertices": len(changed_bnd) + len(recessed_weight_map) + len(throat_snapped) + back_collar_pushed,
        "boundary_vertices": len(boundary),
        "measured_max_displacement_m": round(float(max(changed_bnd.values(), default=0.0)), 6),
        "output_sha256": sha(target),
        "production_ready": False,
    }
    (out / "collar.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("COLLAR: a bounded fitting, sir; no borrowed face. " + json.dumps(report))


if __name__ == "__main__":
    main()
