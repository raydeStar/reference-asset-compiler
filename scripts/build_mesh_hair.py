"""Mesh hair for a character, from a conformed scan of a head: classify, cut, carry over, reduce, bake.

Runs the mesh-hair stages in order (docs/CHARACTER_MESH_HAIR.md) and writes a
receipt. The scan must already be conformed (conform_head_template.py, with
--acquisition-landmarks), and its arrays must be export_mesh_arrays.py of the
same GLB turned by the same --yaw-deg.

Usage:
  python scripts/build_mesh_hair.py --template T.npz --scan scan.glb --scan-conform conform.npz \
      --scan-receipt conform.json --head finish/head.npz --out DIR --blender BLENDER \
      [--yaw-deg 180] [--triangles 60000] [--texture-size 2048] [--cage 0.015]

--head is the character's own head (the one the build uses); the hair is
carried onto it from the scan's conform. Writes DIR/hair-mesh.npz,
hair-mesh-basecolor.png, hair-mesh-normal.png (the bundle's inputs of those
names) and DIR/mesh-hair.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


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
    a = p.parse_args(argv)
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
    run([py, HERE / "transfer_mesh_hair.py", work / "hair-full.npz", a.scan_conform, a.head, work / "hair-on-head.npz"])
    run([py, HERE / "reduce_mesh_hair.py", work / "hair-on-head.npz", work / "hair-low.npz",
         "--triangles", a.triangles])
    run(blender + [HERE / "blender/bake_mesh_hair.py", "--", work / "hair-on-head.npz",
                   work / "hair-full-basecolor.png", work / "hair-low.npz", out,
                   "--size", a.texture_size, "--cage", a.cage])
    receipt = {"stage": "build_mesh_hair", "scan": str(a.scan), "scan_sha256": sha(a.scan),
               "scan_conform_sha256": sha(a.scan_conform), "head": str(a.head), "head_sha256": sha(a.head),
               "yaw_deg": a.yaw_deg, "triangles": a.triangles, "texture_size": a.texture_size, "cage_m": a.cage,
               "outputs": {name: sha(out / name) for name in
                           ("hair-mesh.npz", "hair-mesh-basecolor.png", "hair-mesh-normal.png")},
               "steps": steps}
    (out / "mesh-hair.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "seconds": round(sum(s["seconds"] for s in steps), 1)}))


if __name__ == "__main__":
    main()
