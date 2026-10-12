"""Give a scanned character the template's hands: cut the scan's at the cuff, fit the template's, keep its finger weights.

  blender -b <Name>_UE5.blend --factory-startup --python transplant_template_hands.py -- \
      --template template.npz --save-blend <out.blend> --receipt <out.json>
      [--skin-texture <painted.png>] [--hand-weight 0.3] [--wrist-back-m 0.05] [--cut-beyond-m 0.003]
      [--cut-radius-m 0.1] [--cuff-ratio 0.8] [--outfit NAME] [--skin-object NAME]

The geometry is reference_asset_compiler.template_hands:

- Cut: the outfit's height over the back of the hand finds where the cuff
  ends (cuff_end). Bisect nearby faces at that end + `--cut-beyond-m`, keeping
  interpolated UVs and weights. Remove small detached pieces beyond the cuff.
  A negative offset trims inside the sleeve; tune it per character. Deleting
  only whole triangles left pointed flaps of the acquired wrist behind.
- Fit: the template hand (hand and finger weights past `--hand-weight`, and
  its forearm `--wrist-back-m` behind the wrist to line the sleeve; every
  polygon wholly inside) is turned, scaled and moved so its wrist, middle
  knuckle and index-to-pinky line land on the rig's hand_l/r, middle_01 and
  index_01-to-pinky_01 joints. The template is in an A-pose; the scan in
  whatever pose its rig was fitted.
- Weights: the template's own, by bone name (its bones carry the UE5 names).
  Four influences, normalized.
- Shading: the skin object's first material (the face's skin, whose texture
  atlas holds the template's hands) on the template's UVs. `--skin-texture`
  (paint_template_hands.py's output) replaces that material's texture.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from reference_asset_compiler.template_hands import (  # noqa: E402
    cuff_end, fit, hand_vertices, landmarks, place, polygons_within)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--template", required=True)
    p.add_argument("--save-blend", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--skin-texture")
    p.add_argument("--hand-weight", type=float, default=0.3)
    p.add_argument("--wrist-back-m", type=float, default=0.05)
    p.add_argument("--cut-beyond-m", type=float, default=0.003, help="cut this far past the cuff's end")
    p.add_argument("--cut-radius-m", type=float, default=0.1, help="only outfit within this of the hand's axis is cut")
    p.add_argument("--cuff-ratio", type=float, default=0.8, help="the sleeve ends where its height falls below this share")
    p.add_argument("--outfit")
    p.add_argument("--skin-object")
    a = p.parse_args(argv)

    t = np.load(a.template, allow_pickle=True)
    tv, tw, bones = t["verts"].astype(float), t["weights"].astype(float), [str(b) for b in t["bone_names"]]
    loops, starts, totals, luv = t["loops"], t["loop_starts"], t["loop_totals"], t["loop_uv"]
    bi = {b: i for i, b in enumerate(bones)}
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm]
    outfit = bpy.data.objects[a.outfit] if a.outfit else max(meshes, key=lambda o: len(o.data.vertices))
    skin_ob = bpy.data.objects[a.skin_object] if a.skin_object else next(o for o in meshes if o.name.endswith("_head"))
    skin_mat = skin_ob.material_slots[0].material
    prefix = skin_ob.name[:-len("_head")] if skin_ob.name.endswith("_head") else outfit.name.split("_")[0]
    mw = arm.matrix_world
    omw = np.array(outfit.matrix_world)

    def joint(name):
        return np.array(mw @ arm.data.bones[name].head_local)

    report = {"stage": "transplant_template_hands", "template": a.template, "sides": {}}
    exclude = np.zeros(len(tv), bool)
    for key in ("vg__JointCubes", "vg__HelperGeometry"):
        if key in t:
            exclude[t[key]] = True

    joints_by_side = {}
    for side in ("l", "r"):
        mt = landmarks(tv, tw, bi, side)
        mg = {k: joint(f"{b}_{side}") for k, b in (("wrist", "hand"), ("middle", "middle_01"), ("index", "index_01"),
                                                    ("pinky", "pinky_01"))}
        rot, scale = fit(mt, mg)
        side_joints = {}
        for fname, f_idx in [("thumb", 1), ("index", 2), ("middle", 3), ("ring", 4), ("pinky", 5)]:
            for k in range(1, 5):
                key = f"vg__joint-{side}-finger-{f_idx}-{k}"
                if key in t:
                    pt = tv[t[key]].mean(0)
                    tag = f"{fname}_0{k}_{side}" if k < 4 else f"{fname}_tip_{side}"
                    side_joints[tag] = place(pt, mt, mg, rot, scale)
        joints_by_side[side] = side_joints

        poly_ok = polygons_within(hand_vertices(tv, tw, bi, side, a.hand_weight, a.wrist_back_m, exclude_mask=exclude), loops, starts, totals)
        used = np.unique(np.concatenate([loops[s:s + n] for s, n, ok in zip(starts, totals, poly_ok) if ok]))
        remap = -np.ones(len(tv), np.int64)
        remap[used] = np.arange(len(used))
        faces = [remap[loops[s:s + n]].tolist() for s, n, ok in zip(starts, totals, poly_ok) if ok]
        me = bpy.data.meshes.new(f"hand_{side}")
        me.from_pydata(place(tv[used], mt, mg, rot, scale).tolist(), [], faces)
        uv = me.uv_layers.new(name="UVMap")
        face_loops = np.concatenate([np.arange(s, s + n) for s, n, ok in zip(starts, totals, poly_ok) if ok])
        uv.data.foreach_set("uv", luv[face_loops].astype(np.float32).ravel())
        me.validate()
        for poly in me.polygons:
            poly.use_smooth = True
        ob = bpy.data.objects.new(f"{prefix}_hand_{side}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(skin_mat)
        ob.parent = arm
        ob.modifiers.new("Armature", "ARMATURE").object = arm
        names = [b for b in bones if b in arm.data.bones]
        for b in names:
            ob.vertex_groups.new(name=b)
        wsub = tw[used][:, [bi[b] for b in names]]
        order = np.argsort(-wsub, axis=1)[:, :4]
        for vi in range(len(used)):
            cols = [c for c in order[vi] if wsub[vi, c] > 1e-4]
            tot = sum(wsub[vi, c] for c in cols) or 1.0
            for c in cols:
                ob.vertex_groups[names[c]].add([vi], float(wsub[vi, c] / tot), "REPLACE")

        # cut the scan's hand where its cuff ends
        axis = (mg["middle"] - mg["wrist"]) / np.linalg.norm(mg["middle"] - mg["wrist"])
        co = np.empty(len(outfit.data.vertices) * 3)
        outfit.data.vertices.foreach_get("co", co)
        d = co.reshape(-1, 3) @ omw[:3, :3].T + omw[:3, 3] - mg["wrist"]
        along = d @ axis
        near = np.linalg.norm(d - along[:, None] * axis, axis=1) < a.cut_radius_m
        palm = np.cross(axis, mg["index"] - mg["pinky"]) * (1.0 if side == "l" else -1.0)
        end, height = cuff_end(along, -(d @ (palm / np.linalg.norm(palm))), near, a.cuff_ratio)
        bm = bmesh.new()
        bm.from_mesh(outfit.data)
        # Trim intersecting triangles as well as whole faces. Keeping any face
        # with one vertex behind the cut left the old wrist as pointed flaps.
        cut_faces = [f for f in bm.faces if all(near[v.index] for v in f.verts)]
        cut_geom = set(cut_faces)
        for face in cut_faces:
            cut_geom.update(face.verts)
            cut_geom.update(face.edges)
        previous_faces = len(bm.faces)
        world_plane = Vector(mg["wrist"] + axis * (end + a.cut_beyond_m))
        local_plane = outfit.matrix_world.inverted() @ world_plane
        local_normal = outfit.matrix_world.to_3x3().transposed() @ Vector(axis)
        bmesh.ops.bisect_plane(bm, geom=list(cut_geom), dist=1e-7,
                              plane_co=local_plane, plane_no=local_normal.normalized(),
                              clear_outer=True, clear_inner=False)
        faces_cut = previous_faces - len(bm.faces)
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        # pieces of the scan's hand the cut left loose (a thumb tip hanging past the radius): no part in the sleeve
        loose, seen = [], set()
        for v0 in bm.verts:
            if v0 in seen:
                continue
            island, stack = [], [v0]
            seen.add(v0)
            while stack:
                v = stack.pop()
                island.append(v)
                for e in v.link_edges:
                    o = e.other_vert(v)
                    if o not in seen:
                        seen.add(o)
                        stack.append(o)
            # positions, not indices: the delete above left the indices stale
            if len(island) < 500 and all((omw[:3, :3] @ np.array(v.co) + omw[:3, 3] - mg["wrist"]) @ axis > end - 0.01
                                         for v in island):
                loose += island
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
        bm.to_mesh(outfit.data)
        bm.free()
        report["sides"][side] = {
            "template_vertices": int(len(used)), "faces": len(faces), "scale": round(scale, 4),
            "cuff_end_m": round(end, 4), "cuff_height_m": round(height, 4), "outfit_faces_cut": faces_cut,
            "cut_beyond_m": a.cut_beyond_m,
            "loose_vertices_removed": len(loose), "hand_length_m": round(float(np.linalg.norm(mg["middle"] - mg["wrist"])), 4)}

    # A cut vertex interpolates both endpoints' groups, potentially combining
    # more than four influences. Limit those new blends before Unreal can
    # silently choose its own tailoring. Untouched four-weight vertices stay.
    deform_groups = {g.index for g in outfit.vertex_groups if g.name in arm.data.bones}
    capped = 0
    for vertex in outfit.data.vertices:
        weights = [(g.group, g.weight) for g in vertex.groups
                   if g.group in deform_groups and g.weight > 0]
        if len(weights) <= 4:
            continue
        weights.sort(key=lambda item: (-item[1], item[0]))
        total = sum(weight for _, weight in weights[:4])
        for group, _ in weights[4:]:
            outfit.vertex_groups[group].remove([vertex.index])
        for group, weight in weights[:4]:
            outfit.vertex_groups[group].add([vertex.index], weight / total, "REPLACE")
        capped += 1
    report["cut_vertices_weights_capped"] = capped

    # Move joints without aiming the export bones down their anatomical segments.
    # Their axes encode Manny's animation convention, not Blender's display sticks.
    # Changing head/tail directly rotated fingers by 80-176 degrees: rather a
    # severe case of butterfingers, even for this household.
    original_frames = {b.name: b.matrix_local.copy() for b in arm.data.bones}
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for s in ("l", "r"):
        wrist = Vector(arm.data.edit_bones[f"hand_{s}"].head)
        for fname in ["thumb", "index", "middle", "ring", "pinky"]:
            metacarpal = f"{fname}_metacarpal_{s}"
            b01 = f"{fname}_01_{s}"
            b02 = f"{fname}_02_{s}"
            b03 = f"{fname}_03_{s}"
            btip = f"{fname}_tip_{s}"
            if metacarpal in arm.data.edit_bones and b01 in joints_by_side[s]:
                eb = arm.data.edit_bones[metacarpal]
                frame = original_frames[metacarpal].copy()
                frame.translation = wrist
                eb.matrix = frame
            for bcurr, bnext in [(b01, b02), (b02, b03), (b03, btip)]:
                if bcurr in arm.data.edit_bones and bcurr in joints_by_side[s] and bnext in joints_by_side[s]:
                    eb = arm.data.edit_bones[bcurr]
                    frame = original_frames[bcurr].copy()
                    frame.translation = mw.inverted() @ Vector(joints_by_side[s][bcurr])
                    eb.matrix = frame
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.update()
    frame_error = max(max(abs(b.matrix_local[row][col] - original_frames[b.name][row][col])
                          for row in range(3) for col in range(3)) for b in arm.data.bones)
    # Blender round-trips edit-bone direction/roll through float32; at a metre
    # from the origin the measured error is about 1.5e-5 (under 0.003 degrees).
    if frame_error > 5e-5:
        raise RuntimeError(f"Hand fitting changed the export bone axes: {frame_error}")
    report["maximum_bone_axis_component_delta"] = frame_error
    if a.skin_texture:
        node = next(n for n in skin_mat.node_tree.nodes if n.type == "TEX_IMAGE")
        node.image = bpy.data.images.load(str(Path(a.skin_texture).resolve()))
        report["skin_texture"] = a.skin_texture
    report["triangles"] = sum(len(pl.vertices) - 2 for o in bpy.data.objects if o.type == "MESH" for pl in o.data.polygons)
    out = Path(a.save_blend)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), copy=True)
    report["output_blend"] = str(out)
    report["output_sha256"] = hashlib.sha256(out.read_bytes()).hexdigest()
    Path(a.receipt).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("HANDS " + json.dumps(report))


if __name__ == "__main__":
    main()
