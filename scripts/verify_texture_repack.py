"""Compare PBR samples at corresponding surface points across two UV layouts."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def samples(path, uv):
    image = np.asarray(Image.open(path).convert("RGB"))
    weights = np.array([[1/3,1/3,1/3],[.6,.2,.2],[.2,.6,.2],[.2,.2,.6]])
    points = np.einsum("sj,tjk->tsk", weights, uv).reshape(-1,2)
    x = points[:,0]*image.shape[1]-.5
    y = (1-points[:,1])*image.shape[0]-.5
    return np.column_stack([ndimage.map_coordinates(image[...,c].astype(float),
                             [y,x], order=1, mode="nearest") for c in range(3)])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise ValueError("Keep previous surface comparisons")
    old = np.load(args.before / "uv-regions.npz")
    new = np.load(args.after / "uv-regions.npz")
    if old["position"].shape != new["position"].shape:
        raise ValueError("Triangle correspondence changed")
    delta = float(np.max(np.abs(old["position"] - new["position"])))
    if delta > 1e-6:
        raise ValueError("Surface correspondence changed")
    manifests = [json.loads((p/"retopo.json").read_text()) for p in (args.before,args.after)]
    results, hashes = {}, {}
    for channel in ("BaseColor","Metallic","Roughness"):
        paths = [p/m["baked"][channel] for p,m in zip((args.before,args.after),manifests)]
        values = [samples(p,d["uv"]) for p,d in zip(paths,(old,new))]
        difference = np.abs(values[0]-values[1])
        results[channel] = {"mean_absolute_8bit_error": float(difference.mean()),
                            "p95_absolute_8bit_error": float(np.percentile(difference,95)),
                            "p99_absolute_8bit_error": float(np.percentile(difference,99))}
        hashes.update({str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    report = {"schema": "reference-asset-compiler.surface-texture-comparison.v1",
              "maximum_triangle_position_delta_m":delta, "samples_per_triangle":4,
              "triangle_count":len(old["uv"]), "channels":results, "texture_hashes":hashes,
              "note":"Resampling error diagnostic, not a visual or production approval"}
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(results,indent=2))


if __name__ == "__main__":
    main()
