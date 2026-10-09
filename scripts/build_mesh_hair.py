"""Mesh hair for a character, from a conformed scan of a head: classify, cut, carry over, reduce, bake.

Runs the mesh-hair stages in order (docs/CHARACTER_MESH_HAIR.md) and writes a
receipt. The scan must already be conformed (conform_head_template.py, with
--acquisition-landmarks), and its arrays must be export_mesh_arrays.py of the
same GLB turned by the same --yaw-deg.

Usage:
  python scripts/build_mesh_hair.py --template T.npz --scan scan.glb --scan-conform conform.npz \
      --scan-receipt conform.json --head finish/head.npz --out DIR --blender BLENDER \
      [--yaw-deg 180] [--triangles 30000] [--texture-size 2048] [--cage 0.015]
      [--scan-landmarks dw-acq-front.json --scan-camera acq-front-camera.json [--binding B.json]]

--head is the character's own head (the one the build uses); the hair is
carried onto it from the scan's conform: by the face when --scan-landmarks and
--scan-camera are given (the conform's seed landmarks on the scan's front
render; transfer_mesh_hair.py --place-by-face, then keep_hair_clear.py on the
reduced hair, --clearance), otherwise by following the skin. Writes DIR/hair-mesh.npz,
hair-mesh-basecolor.png, hair-mesh-normal.png (the bundle's inputs of those
names) and DIR/mesh-hair.json, whose triangles_shipped is the count in
hair-mesh.npz; a count more than 2% from --triangles is a WARNING (stderr and the
receipt's warnings).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from reduce_mesh_hair import count_warning  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("template", "scan", "scan-conform", "scan-receipt", "head", "out", "blender"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--yaw-deg", type=float, default=0.0)
    p.add_argument("--triangles", type=int, default=60000)
    p.add_argument("--texture-size", type=int, default=2048)
    p.add_argument("--cage", type=float, default=0.015)
    p.add_argument("--scan-landmarks", help="the face detector's JSON of the scan's front render: place the hair "
                   "by the face (transfer_mesh_hair.py --place-by-face)")
    p.add_argument("--scan-camera", help="that render's camera JSON")
    p.add_argument("--binding", help="the template's face landmark binding (default: transfer_mesh_hair.py's)")
    p.add_argument("--clearance", type=float, default=0.002,
                   help="metres face-placed hair keeps outside the skin (keep_hair_clear.py)")
    a = p.parse_args(argv)
    if bool(a.scan_landmarks) != bool(a.scan_camera):
        p.error("--scan-landmarks and --scan-camera go together")
    out = Path(a.out).resolve()
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    steps = []

    def run(cmd):
        t0 = time.time()
        result = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
        steps.append({"cmd": [str(c) for c in cmd][:4], "seconds": round(time.time() - t0, 1),
                      "tail": result.stdout.strip().splitlines()[-1:] if result.stdout else []})
        if result.returncode:
            sys.stderr.write(result.stdout[-2000:] + result.stderr[-2000:])
            raise SystemExit(f"step failed: {cmd[1] if len(cmd) > 1 else cmd[0]}")

    blender = [a.blender, "-b", "--factory-startup", "--python-exit-code", "1", "--python"]
    py = sys.executable
    run([py, HERE / "classify_scan_hair.py", a.template, a.scan_conform, work / "classified.npz"])
    run(blender + [HERE / "blender/cut_scan_hair.py", "--", Path(a.scan).resolve(), Path(a.scan_receipt).resolve(),
                   Path(a.scan_conform).resolve(), work / "classified.npz", work, "--yaw-deg", a.yaw_deg])
    place = (["--place-by-face", "--scan-landmarks", a.scan_landmarks, "--scan-camera", a.scan_camera,
              "--scan-receipt", a.scan_receipt, *(["--binding", a.binding] if a.binding else [])]
             if a.scan_landmarks else [])
    run([py, HERE / "transfer_mesh_hair.py", work / "hair-full.npz", a.scan_conform, a.head, work / "hair-on-head.npz",
         *place])
    placement = json.loads(steps[-1]["tail"][0]) if steps[-1]["tail"] else {}
    run([py, HERE / "reduce_mesh_hair.py", work / "hair-on-head.npz", work / "hair-low.npz",
         "--triangles", a.triangles])
    low, clear = work / "hair-low.npz", {}
    if a.scan_landmarks:
        # After the reduction: pushed vertex by vertex first, the collapse stops early.
        run([py, HERE / "keep_hair_clear.py", low, a.head, work / "hair-low-clear.npz", "--clearance", a.clearance])
        low, clear = work / "hair-low-clear.npz", json.loads(steps[-1]["tail"][0])
    run(blender + [HERE / "blender/bake_mesh_hair.py", "--", work / "hair-on-head.npz",
                   work / "hair-full-basecolor.png", low, out,
                   "--size", a.texture_size, "--cage", a.cage])
    shipped = int(len(np.load(out / "hair-mesh.npz")["tris"]))
    warning = count_warning(a.triangles, shipped, "the shipped hair")
    if warning:
        print("WARNING: " + warning, file=sys.stderr)
    receipt = {"stage": "build_mesh_hair", "scan": str(a.scan), "scan_sha256": sha(a.scan),
               "scan_conform_sha256": sha(a.scan_conform), "head": str(a.head), "head_sha256": sha(a.head),
               "yaw_deg": a.yaw_deg, "placement": {k: v for k, v in placement.items() if k != "vertices"},
               "clearance": {k: v for k, v in clear.items() if k != "vertices"},
               "scan_landmarks": str(a.scan_landmarks) if a.scan_landmarks else None,
               "triangles_requested": a.triangles, "triangles_shipped": shipped,
               "warnings": [warning] if warning else [], "texture_size": a.texture_size, "cage_m": a.cage,
               "outputs": {name: sha(out / name) for name in
                           ("hair-mesh.npz", "hair-mesh-basecolor.png", "hair-mesh-normal.png")},
               "steps": steps}
    (out / "mesh-hair.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "triangles_shipped": shipped, "warnings": receipt["warnings"],
                      "seconds": round(sum(s["seconds"] for s in steps), 1)}))


if __name__ == "__main__":
    main()
