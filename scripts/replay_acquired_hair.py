"""Replay fitting, dense clearance, shell cleanup and baking of reviewed AI hair.

CPU only. A reviewed extracted mesh is an input, not an inferred segmentation.
The output is a component awaiting visual review; this never promotes an asset.
Usage: python scripts/replay_acquired_hair.py recipe.json --out NEW --blender B
Use --plan to verify lineage and settings without writing or running Blender.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix

HERE = Path(__file__).resolve().parent
REQUIRED = {
    "scan", "acquisition_receipt", "conditioning_image", "selection_receipt",
    "extraction_receipt", "extracted_hair", "basecolor", "scan_conform",
    "scan_receipt", "head", "binding", "scan_landmarks", "scan_camera",
}
DEFAULTS = {
    "clearance_m": .0015, "clearance_smoothing_iterations": 24,
    "radius_m": .004, "erosion_m": .003, "voxel_m": .0008,
    "shell_smoothing_iterations": 3, "triangles": 26000,
    "texture_size": 2048, "cage_m": .006,
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_recipe(path):
    path = Path(path).resolve()
    recipe = json.loads(path.read_text(encoding="utf-8-sig"))
    if recipe.get("schema") != "reference-asset-compiler.acquired-hair-recipe.v1":
        raise ValueError("Expected acquired-hair-recipe.v1")
    if set(recipe.get("inputs", {})) != REQUIRED:
        raise ValueError("The recipe needs the complete, explicit acquisition input set")
    files = {}
    for name, item in recipe["inputs"].items():
        resolved = (path.parent / item["path"]).resolve()
        if sha(resolved) != item["sha256"]:
            raise ValueError(f"Stale {name} input: {resolved.name}")
        files[name] = resolved
    acquisition = json.loads(files["acquisition_receipt"].read_text(encoding="utf-8"))
    if (acquisition.get("schema") != "reference-asset-compiler.geometry-candidate.v1"
            or acquisition.get("ok") is not True
            or acquisition.get("candidate_sha256") != sha(files["scan"])
            or acquisition.get("image_sha256") != sha(files["conditioning_image"])):
        raise ValueError("Acquisition receipt must bind the AI geometry to the conditioning image")
    extraction = json.loads(files["extraction_receipt"].read_text(encoding="utf-8"))
    if extraction.get("source_sha256") != sha(files["scan"]):
        raise ValueError("Extraction must identify the same acquired scan")
    if not recipe.get("extraction_review") or not recipe.get("component_scope"):
        raise ValueError("Record the reviewed extraction and component scope")
    supplied = recipe.get("settings", {})
    if set(supplied) - set(DEFAULTS):
        raise ValueError("Unknown hair cleanup settings")
    settings = DEFAULTS | supplied
    if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v)
               for v in settings.values()):
        raise ValueError("Hair settings must be finite numbers")
    if not (0 <= settings["clearance_m"] <= .01
            and 0 < settings["erosion_m"] < settings["radius_m"] <= .02
            and 0 < settings["voxel_m"] <= settings["radius_m"]
            and 0 < settings["cage_m"] <= .05):
        raise ValueError("Cleanup distances are outside the bounded metre ranges")
    for key, lo, hi in [("clearance_smoothing_iterations", 0, 100),
                        ("shell_smoothing_iterations", 0, 10), ("triangles", 1000, 200000),
                        ("texture_size", 256, 8192)]:
        if int(settings[key]) != settings[key] or not lo <= settings[key] <= hi:
            raise ValueError(f"Invalid {key}")
    return recipe, files, settings


def smooth_displacements(verts, tris, displacement, iterations):
    """Diffuse clearance displacement, keeping disconnected pieces independent.

    This smooths a fitted surface; it does not certify collision clearance.
    Final clearance and silhouette still require visual inspection.
    """
    if not iterations:
        return displacement.copy()
    t = np.asarray(tris, np.int64)
    i = np.concatenate([t[:, 0], t[:, 1], t[:, 2], t[:, 1], t[:, 2], t[:, 0]])
    j = np.concatenate([t[:, 1], t[:, 2], t[:, 0], t[:, 0], t[:, 1], t[:, 2]])
    adjacency = coo_matrix((np.ones(len(i)), (i, j)), shape=(len(verts), len(verts))).tocsr()
    adjacency.data[:] = 1
    degree = np.asarray(adjacency.sum(1)).ravel()
    result = displacement.copy()
    active = degree > 0
    for _ in range(iterations):
        average = (adjacency @ result)[active] / degree[active, None]
        result[active] = .5 * result[active] + .5 * average
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("recipe", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--blender")
    p.add_argument("--plan", action="store_true")
    args = p.parse_args(argv)
    recipe, files, settings = load_recipe(args.recipe)
    if args.plan:
        print(json.dumps({"inputs_verified": len(files), "settings": settings,
                          "visual_acceptance": "not performed", "production_ready": False}, indent=2))
        return
    if not args.out or not args.blender:
        p.error("--out and --blender are required unless --plan is used")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "recipe.json").write_text(json.dumps(recipe, indent=2), encoding="utf-8")
    steps = []

    def run(command):
        command = list(map(str, command))
        started = time.monotonic()
        result = subprocess.run(command, capture_output=True, text=True)
        record = {"command": command, "seconds": round(time.monotonic() - started, 2),
                  "returncode": result.returncode}
        steps.append(record)
        (out / f"step-{len(steps)}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        (out / "steps.json").write_text(json.dumps(steps, indent=2), encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"Hair stage {len(steps)} failed; retained log, no automatic retry")

    run([sys.executable, HERE / "transfer_mesh_hair.py", files["extracted_hair"],
         files["scan_conform"], files["head"], out / "placed.npz", "--place-by-face",
         "--scan-landmarks", files["scan_landmarks"], "--scan-camera", files["scan_camera"],
         "--scan-receipt", files["scan_receipt"], "--binding", files["binding"]])
    from keep_hair_clear import head_skin, keep_clear

    hair = dict(np.load(out / "placed.npz"))
    points = hair["verts"].astype(float)
    skin, normals = head_skin(np.load(files["head"]))
    cleared, _ = keep_clear(points, skin, normals, settings["clearance_m"])
    delta = smooth_displacements(points, hair["tris"], cleared - points,
                                 int(settings["clearance_smoothing_iterations"]))
    hair["verts"] = (points + delta).astype("f")
    np.savez_compressed(out / "high-clear.npz", **hair)
    np.savez_compressed(out / "shell-input.npz", verts=hair["verts"], cap_points=np.empty((0, 3)))
    blender = [args.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python"]
    run(blender + [HERE / "blender/build_hair_shell.py", "--", out / "shell-input.npz",
                   out / "shell.glb", out / "shell.npz", "--radius", settings["radius_m"],
                   "--erode", settings["erosion_m"], "--voxel", settings["voxel_m"],
                   "--smooth", settings["shell_smoothing_iterations"], "--triangles", settings["triangles"],
                   "--stride", "1"])
    run(blender + [HERE / "blender/bake_mesh_hair.py", "--", out / "high-clear.npz", files["basecolor"],
                   out / "shell.npz", out, "--size", settings["texture_size"], "--cage", settings["cage_m"]])
    from reduce_mesh_hair import count_warning

    shipped = len(np.load(out / "hair-mesh.npz")["tris"])
    warning = count_warning(settings["triangles"], shipped, "the shipped hair")
    report = {"schema": "reference-asset-compiler.acquired-hair-replay.v1",
              "recipe_sha256": sha(args.recipe), "inputs": {k: sha(v) for k, v in files.items()},
              "settings": settings, "triangles_shipped": shipped, "warnings": [warning] if warning else [],
              "steps": steps, "outputs": {name: sha(out / name) for name in
                  ("hair-mesh.npz", "hair-mesh-basecolor.png", "hair-mesh-normal.png")},
              "visual_acceptance": "pending", "production_ready": False, "character_replaced": False}
    (out / "replay.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "triangles": shipped, "warnings": report["warnings"]}))
    print("The hair is replayed; the mirror still gets the final word.")


if __name__ == "__main__":
    main()
