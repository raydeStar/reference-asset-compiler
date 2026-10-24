# SPDX-License-Identifier: MIT
"""Measure sampled hand/body triangle intersections using complete native skin weights.

Select one combined outfit/hand mesh explicitly. Arm-weighted sleeve surfaces
are excluded from the body set; this is a bounded test, not whole-body collision.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "anim"))
from skin_geometry import matrix, skin_data, deform
import clip_retarget as cr
import transition_clips as tc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["source", "packet", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--mesh", required=True)
    p.add_argument("--clips", default="MM_Idle,MF_Unarmed_Walk_Fwd")
    p.add_argument("--step", type=int, default=3)
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    assert 1 <= a.step <= 10 and not a.output.exists()
    packet = json.loads(a.packet.read_text())
    assert (
        hashlib.sha256(a.source.read_bytes()).hexdigest()
        == packet["provenance"]["character_blend_sha256"]
    )
    bpy.ops.wm.open_mainfile(filepath=str(a.source.resolve()))
    rig = cr.TargetRig(next(o for o in bpy.context.scene.objects if o.type == "ARMATURE"))
    obj = bpy.data.objects[a.mesh]
    data = skin_data(obj, rig.index)
    inverse = np.linalg.inv(rig.rest)
    hands = {
        s: {"hand_" + s} | {b.name for b in rig.obj.data.bones["hand_" + s].children_recursive}
        for s in "lr"
    }
    arms = {n for n in rig.names if n.startswith(("clavicle", "upperarm", "lowerarm"))} | set.union(
        *hands.values()
    )
    group_names = {g.index: g.name for g in obj.vertex_groups}
    selection = {}
    for s, bones in hands.items():
        selection[s] = {
            v.index
            for v in obj.data.vertices
            if sum(g.weight for g in v.groups if group_names[g.group] in bones) > 0.5
        }
    selection["body"] = {
        v.index
        for v in obj.data.vertices
        if sum(g.weight for g in v.groups if group_names[g.group] in arms) < 0.1
    }
    faces = {
        s: [
            list(poly.vertices)
            for poly in obj.data.polygons
            if all(v in ids for v in poly.vertices)
        ]
        for s, ids in selection.items()
    }
    assert all(faces.values()), "explicit hand and body surfaces required"
    rows = []
    for name in a.clips.split(","):
        c = packet["clips"][name]
        for f in sorted(set(range(0, c["frames"], a.step)) | {c["frames"] - 1}):
            world = tc.fk(rig, np.array([matrix(c["tracks"][n][f]) for n in rig.names]))
            points = deform(data, world @ inverse).tolist()
            body = BVHTree.FromPolygons(points, faces["body"])
            rows.append(
                {
                    "clip": name,
                    "frame": f,
                    "intersections": {
                        s: len(BVHTree.FromPolygons(points, faces[s]).overlap(body)) for s in "lr"
                    },
                }
            )
    result = {
        "source_sha256": hashlib.sha256(a.source.read_bytes()).hexdigest(),
        "packet_sha256": hashlib.sha256(a.packet.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "mesh": a.mesh,
        "face_counts": {k: len(v) for k, v in faces.items()},
        "frames": rows,
        "sampled_clearance_passed": not any(sum(r["intersections"].values()) for r in rows),
        "human_approved": False,
        "scope": "Selected native skinned hand versus non-arm body triangles. No cloth simulation, sleeves, containment or continuous-collision claim.",
    }
    a.output.write_text(json.dumps(result, indent=2))
    print(
        "HAND_CLEARANCE",
        result["sampled_clearance_passed"],
        "-- the sleeves retain their own counsel.",
    )


if __name__ == "__main__":
    main()
