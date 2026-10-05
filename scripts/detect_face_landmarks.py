"""Detect 2D face landmarks in a reference image with InsightFace (buffalo_l).

The conform stage places a character's eyes, brows, nose and mouth from the
approved image rather than from the acquisition, which can fuse a lid or
drift a mouth. This reads the image and writes the 106-point 2D landmarks
(and the 68-point 3D set and head pose) for the most prominent face, in
pixels. Uses locally installed models only; it never downloads.

Run it with an interpreter that has insightface and onnxruntime (on this
workstation, ComfyUI's embedded Python):

  <python> scripts/detect_face_landmarks.py <image> <out.json> \
      --models <dir containing models/buffalo_l> [--overlay out.png]
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

# InsightFace 2d106det index ranges (insightface/alignment/coordinate_reg).
REGIONS_106 = {
    "jaw": list(range(0, 33)),
    "left_eye": list(range(33, 43)),     # image-left eye (the subject's right)
    "left_brow": list(range(43, 52)),
    "mouth": list(range(52, 72)),
    "right_eye": list(range(87, 97)),    # image-right eye (the subject's left)
    "right_brow": list(range(97, 106)),
    "nose": list(range(72, 87)),
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("image")
    p.add_argument("out")
    p.add_argument("--models", required=True)
    p.add_argument("--overlay")
    p.add_argument("--det-size", type=int, default=640)
    a = p.parse_args()

    import cv2
    from insightface.app import FaceAnalysis

    root = Path(a.models)
    if not (root / "models" / "buffalo_l").is_dir():
        raise SystemExit("buffalo_l models not found under " + str(root) + "; refusing to download")
    app = FaceAnalysis(name="buffalo_l", root=str(root),
                       allowed_modules=["detection", "landmark_2d_106", "landmark_3d_68"],
                       providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(a.det_size, a.det_size))
    img = cv2.imread(a.image)
    faces = app.get(img)
    if not faces:
        raise SystemExit("no face detected in " + a.image)
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    lm = face.landmark_2d_106.astype(float)
    out = {
        "schema": "reference-asset-compiler.face-landmarks.v1",
        "image": str(Path(a.image).resolve()),
        "image_sha256": hashlib.sha256(Path(a.image).read_bytes()).hexdigest(),
        "size": [int(img.shape[1]), int(img.shape[0])],
        "detector": "insightface buffalo_l 2d106det + 1k3d68",
        "score": float(face.det_score),
        "bbox": [float(v) for v in face.bbox],
        "landmarks_106": lm.tolist(),
        "landmarks_3d_68": face.landmark_3d_68.astype(float).tolist(),
        "pose_pitch_yaw_roll": [float(v) for v in face.pose] if face.pose is not None else None,
        "regions_106": REGIONS_106,
    }
    Path(a.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    if a.overlay:
        vis = img.copy()
        colours = [(0, 255, 255), (0, 255, 0), (255, 128, 0), (0, 0, 255), (255, 0, 255),
                   (255, 255, 0), (128, 255, 128)]
        for (name, idx), col in zip(REGIONS_106.items(), colours):
            for k in idx:
                x, y = lm[k]
                cv2.circle(vis, (int(round(x)), int(round(y))), 2, col, -1)
                cv2.putText(vis, str(k), (int(x) + 3, int(y) - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.28,
                            col, 1)
        cv2.imwrite(a.overlay, vis)
    print("face", round(float(face.det_score), 3), "bbox", np.round(face.bbox).tolist(),
          "pose", out["pose_pitch_yaw_roll"])


if __name__ == "__main__":
    main()
