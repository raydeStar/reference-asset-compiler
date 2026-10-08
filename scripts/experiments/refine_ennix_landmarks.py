"""Fit the retained open hands and centreline instead of inheriting Manny's curl.

The source body is a T pose with flat, separated fingers. The generic template
has slightly bent phalanges and an asymmetric sash biases its torso median.
This derivative measures the actual hand surface; no geometry is changed.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument("landmarks")
    p.add_argument("body")
    p.add_argument("out")
    a = p.parse_args()
    record = json.loads(Path(a.landmarks).read_text())
    joints = record["joints"]
    verts = np.load(a.body)["verts"].copy()
    verts[:, 2] += 0.899942875
    old_midline = record["midline_x"]
    for name, pos in joints.items():
        if name.startswith(("spine", "neck", "head", "pelvis", "clavicle", "upperarm_")) and "twist" not in name:
            pos[0] -= old_midline
    measurements = {}
    for side, sign in (("l", 1), ("r", -1)):
        hand = verts[verts[:, 0] * sign > 0.84]
        # The four separated fingers occupy these nonoverlapping y bands.
        # Sampling their centres prevents the template's curled tips falling
        # below the mesh. Even a butler must count the fingers after fitting.
        for digit, lo, hi, knuckle in (("index", -0.002, 0.043, 0.944),
                                      ("middle", 0.043, 0.077, 0.946),
                                      ("ring", 0.077, 0.110, 0.938),
                                      ("pinky", 0.110, 0.150, 0.923)):
            cloud = hand[(hand[:, 1] > lo) & (hand[:, 1] < hi) & (hand[:, 0] * sign > knuckle)]
            tip = float(np.quantile(cloud[:, 0] * sign, 0.997)) - 0.004
            positions = []
            for label, fraction in (("01", 0), ("02", 0.45), ("03", 0.76), ("tip", 1)):
                x = knuckle + (tip - knuckle) * fraction
                strip = cloud[np.abs(cloud[:, 0] * sign - x) < 0.010]
                if len(strip) < 5:
                    raise ValueError(f"Cannot locate {digit}_{label}_{side} in the acquired hand")
                pos = [sign * x, float(np.median(strip[:, 1])), float((strip[:, 2].min() + strip[:, 2].max()) / 2)]
                joints[f"{digit}_{label}_{side}"] = pos
                positions.append(pos)
            wrist = np.array(joints["hand_" + side])
            first = np.array(positions[0])
            joints[f"{digit}_metacarpal_{side}"] = (wrist * 0.55 + first * 0.45).tolist()
            measurements[digit + "_" + side] = {"surface_vertices": len(cloud), "tip_x": sign * tip}
        thumb = hand[(hand[:, 1] < 0) & (hand[:, 0] * sign > 0.88)]
        thumb_tip_x = float(np.quantile(thumb[:, 0] * sign, 0.99)) - 0.004
        for label, fraction in (("01", 0), ("02", 0.42), ("03", 0.74), ("tip", 1)):
            x = 0.887 + (thumb_tip_x - 0.887) * fraction
            strip = thumb[np.abs(thumb[:, 0] * sign - x) < 0.012]
            joints[f"thumb_{label}_{side}"] = [sign * x, float(np.median(strip[:, 1])), float(np.mean(strip[:, 2]))]
        # Recompute twists after correcting the shoulder centreline.
        for parent, end in (("upperarm", "lowerarm"), ("lowerarm", "hand")):
            start, stop = np.array(joints[parent + "_" + side]), np.array(joints[end + "_" + side])
            for label, fraction in (("01", 1 / 3), ("02", 2 / 3)):
                joints[f"{parent}_twist_{label}_{side}"] = (start + (stop - start) * fraction).tolist()
    record["midline_x"] = 0.0
    record["ennix_refinement"] = {
        "input_landmarks_sha256": hashlib.sha256(Path(a.landmarks).read_bytes()).hexdigest(),
        "body_sha256": hashlib.sha256(Path(a.body).read_bytes()).hexdigest(),
        "centreline_correction_m": old_midline,
        "method": "Flat finger joints fitted to measured mesh cross-sections; torso aligned to the original symmetry plane",
        "fingers": measurements,
        "human_review": "pending",
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2))
    print("The fingers are accounted for, sir; their movements still need inspection.")


if __name__ == "__main__":
    main()
