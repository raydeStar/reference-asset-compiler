"""Regression proof on real game-rig artifacts: preserved identity and moving hands."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from review_character_seams import apply_idle


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mesh_fingerprint(obj):
    payload = {"position": [list(v.co) for v in obj.data.vertices],
               "faces": [list(p.vertices) for p in obj.data.polygons],
               "uvs": [[list(d.uv) for d in layer.data] for layer in obj.data.uv_layers],
               "weights": [[(obj.vertex_groups[g.group].name, g.weight) for g in v.groups]
                           for v in obj.data.vertices],
               "transform": [list(row) for row in obj.matrix_world],
               "shapes": {key.name: [list(v.co) for v in key.data] for key in obj.data.shape_keys.key_blocks}
                         if obj.data.shape_keys else {}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def inspect(path, manny_dir, poses):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    skeleton = {b.name: {"matrix": [list(row) for row in b.matrix_local],
                         "parent": b.parent.name if b.parent else None} for b in rig.data.bones}
    meshes = {o.name: mesh_fingerprint(o) for o in bpy.data.objects
              if o.type == "MESH" and not o.name.endswith("Outfit_And_Hands")}
    hands = [o for o in bpy.data.objects if o.type == "MESH" and o.name.endswith(("_hand_l", "_hand_r"))]
    if poses and len(hands) != 2:
        raise ValueError("Expected exactly two template hands for the deformation check")
    rest = {o.name: np.array([o.matrix_world @ v.co for v in o.data.vertices]) for o in hands}
    results = []
    for animation, index in poses:
        info = apply_idle(rig, manny_dir, animation, index)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for hand in hands:
            evaluated = hand.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            points = np.array([evaluated.matrix_world @ v.co for v in mesh.vertices])
            edges = np.array([e.vertices[:] for e in hand.data.edges])
            original = np.linalg.norm(rest[hand.name][edges[:, 0]] - rest[hand.name][edges[:, 1]], axis=1)
            posed = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
            ratios = posed[original > 0.0005] / original[original > 0.0005]
            results.append({"animation": animation, "time": info["time"], "hand": hand.name,
                            "edge_stretch_p99": float(np.quantile(ratios, 0.99)),
                            "edge_stretch_max": float(ratios.max()),
                            "edge_compression_p01": float(np.quantile(ratios, 0.01))})
            evaluated.to_mesh_clear()
    return {"sha256": sha(path), "skeleton": skeleton, "protected_meshes": meshes, "poses": results}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("original", type=Path)
    parser.add_argument("reference_axes", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--manny-dir", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.out.exists():
        raise FileExistsError("Verification evidence is append-only, sir.")
    poses = [("MM_Idle", 0), ("MM_Attack_01", 0), ("MM_Attack_01", 1),
             ("MF_Unarmed_Jog_Fwd", 0), ("MF_Unarmed_Jog_Fwd", 1), ("MM_Jump", 0)]
    reference = inspect(args.reference_axes.resolve(), args.manny_dir, [])
    original = inspect(args.original.resolve(), args.manny_dir, poses)
    candidate = inspect(args.candidate.resolve(), args.manny_dir, poses)
    ref_bones, bones = reference["skeleton"], candidate["skeleton"]
    axis_error = max(float(np.max(np.abs(np.array(bones[n]["matrix"])[:3, :3] -
                                             np.array(ref_bones[n]["matrix"])[:3, :3]))) for n in ref_bones)
    checks = {
        "identity_meshes_uvs_shapes_weights_unchanged": original["protected_meshes"] == candidate["protected_meshes"],
        "same_bone_names_and_parents": {n: b["parent"] for n, b in ref_bones.items()} ==
                                       {n: b["parent"] for n, b in bones.items()},
        "export_axes_preserved": axis_error < 5e-5,
        "all_sampled_hand_p99_stretch_below_2": all(p["edge_stretch_p99"] < 2 for p in candidate["poses"]),
        "all_sampled_hand_max_stretch_below_5": all(p["edge_stretch_max"] < 5 for p in candidate["poses"]),
    }
    report = {"inputs": {k: {"path": str(getattr(args, k).resolve()), "sha256": sha(getattr(args, k))}
                         for k in ("original", "reference_axes", "candidate")},
              "script_sha256": sha(__file__), "blender": bpy.app.version_string,
              "pose_helper_sha256": sha(Path(__file__).with_name("review_character_seams.py")),
              "manny_reference_sha256": sha(args.manny_dir / "manny_refpose.json"),
              "manny_poses_sha256": sha(args.manny_dir / "manny_anim_poses.json"),
              "maximum_axis_component_error": axis_error, "checks": checks,
              "original_poses": original["poses"], "candidate_poses": candidate["poses"],
              "passed": all(checks.values()), "production_ready": False,
              "limits": "Sampled native deformation; visual and Unreal runtime acceptance remain separate."}
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("HAND CHECK: " + json.dumps(checks) + "; the fingers must earn their gloves, sir.")
    if not report["passed"]:
        raise RuntimeError("Character hand regression check failed; inspect the retained receipt")


if __name__ == "__main__":
    main()
