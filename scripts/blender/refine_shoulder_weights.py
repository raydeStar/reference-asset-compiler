"""Keep a T-pose scan's arm weights on the arm, in a UE5 rig blend (reference_asset_compiler.shoulder_weights).

  blender -b <Name>_UE5.blend --factory-startup --python refine_shoulder_weights.py -- \
      --save-blend <out.blend> --receipt <out.json> [--inboard-m 0.03] [--outboard-m 0.07]
      [--under-armpit-m 0.05] [--armpit-blend-m 0.05] [--clavicle-from-m 0.08]
      [--layer-radius-m 0.015] [--layer-iterations 2] [--mesh NAME]

Applies to the armature's largest mesh (the outfit and hands) unless --mesh
names one. Every other mesh and every other weight is kept. The input blend is
never saved over. The receipt has the armpit heights found and the weight moved.

Then the torso (inboard of both shoulder joints less `--inboard-m`, between
the spine_01 and neck_01 joints' heights) is smoothed across its layers
(smooth_across_layers; `--layer-radius-m 0` skips it).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from reference_asset_compiler.shoulder_weights import refine, smooth_across_layers  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    p = argparse.ArgumentParser()
    p.add_argument("--save-blend", required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--inboard-m", type=float, default=0.03)
    p.add_argument("--outboard-m", type=float, default=0.07)
    p.add_argument("--under-armpit-m", type=float, default=0.05)
    p.add_argument("--armpit-blend-m", type=float, default=0.05)
    p.add_argument("--clavicle-from-m", type=float, default=0.08)
    p.add_argument("--layer-radius-m", type=float, default=0.015)
    p.add_argument("--layer-iterations", type=int, default=2)
    p.add_argument("--mesh")
    a = p.parse_args(argv)

    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent == arm]
    ob = bpy.data.objects[a.mesh] if a.mesh else max(meshes, key=lambda o: len(o.data.vertices))
    bones = [g.name for g in ob.vertex_groups]
    n = len(ob.data.vertices)
    w = np.zeros((n, len(bones)))
    for v in ob.data.vertices:
        for g in v.groups:
            w[v.index, g.group] = g.weight
    co = np.empty(n * 3)
    ob.data.vertices.foreach_get("co", co)
    m = np.array(ob.matrix_world)
    pos = co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
    mw = arm.matrix_world
    shoulders = {s: list(mw @ arm.data.bones[f"upperarm_{s}"].head_local) for s in ("l", "r")
                 if f"upperarm_{s}" in arm.data.bones}
    new, report = refine(w, bones, pos, shoulders, a.inboard_m, a.outboard_m, a.under_armpit_m, a.armpit_blend_m,
                         a.clavicle_from_m)
    if a.layer_radius_m > 0:
        bone_z = {b: (mw @ arm.data.bones[b].head_local).z for b in ("spine_01", "neck_01")}
        inboard = min(abs(v[0]) for v in shoulders.values()) - a.inboard_m
        torso = (np.abs(pos[:, 0]) < inboard) & (pos[:, 2] > bone_z["spine_01"]) & (pos[:, 2] < bone_z["neck_01"])
        new, layers = smooth_across_layers(new, pos, torso, a.layer_radius_m, a.layer_iterations)
        report.update(layers)
    changed = np.abs(new - w).max(1) > 1e-6
    for vi in np.flatnonzero(changed):
        for gi in range(len(bones)):
            if w[vi, gi] > 0 or new[vi, gi] > 0:
                if new[vi, gi] > 1e-6:
                    ob.vertex_groups[gi].add([int(vi)], float(new[vi, gi]), "REPLACE")
                else:
                    ob.vertex_groups[gi].remove([int(vi)])
    out = Path(a.save_blend)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out), copy=True)
    report.update({"stage": "refine_shoulder_weights", "mesh": ob.name, "vertices_changed": int(changed.sum()),
                   "params": {k: getattr(a, k) for k in ("inboard_m", "outboard_m", "under_armpit_m", "armpit_blend_m",
                                                               "clavicle_from_m", "layer_radius_m", "layer_iterations")},
                   "input_blend": bpy.data.filepath, "output_blend": str(out),
                   "output_sha256": hashlib.sha256(out.read_bytes()).hexdigest()})
    Path(a.receipt).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("SHOULDER_WEIGHTS " + json.dumps(report))


if __name__ == "__main__":
    main()
