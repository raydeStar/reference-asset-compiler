"""Detect whole-body keypoints (COCO-WholeBody, 133 points) with DWPose, open source.

Same open model and direct-PyTorch route as detect_face_landmarks_dwpose.py
(dw-ll_ucoco_384, Apache-2.0); here the person box is the non-background
bounding box of a clean render. Body joints, both hands (21 each) and the
68 face points are written with scores.

Usage (any Python with torch, numpy, Pillow):
  python scripts/detect_body_landmarks_dwpose.py <image> <out.json> --model <...torchscript.pt> [--overlay out.png]
"""
import argparse, json, hashlib
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
INPUT_W, INPUT_H = 288, 384
MEAN = np.array([123.675, 116.28, 103.53]); STD = np.array([58.395, 57.12, 57.375])
NAMES = ['nose','l_eye','r_eye','l_ear','r_ear','l_shoulder','r_shoulder','l_elbow','r_elbow','l_wrist','r_wrist',
         'l_hip','r_hip','l_knee','r_knee','l_ankle','r_ankle','l_bigtoe','l_smalltoe','l_heel','r_bigtoe','r_smalltoe','r_heel']
def person_box(img, bg_tol=18):
    a = np.asarray(img.convert('RGB'), np.int16)
    bg = np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), 0)
    mask = np.abs(a - bg).sum(2) > bg_tol
    ys, xs = np.nonzero(mask)
    return xs.min(), ys.min(), xs.max(), ys.max()
def run(model, img, box, pad):
    import torch
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw, bh = (x1 - x0) * (1 + pad), (y1 - y0) * (1 + pad)
    if bw / bh > INPUT_W / INPUT_H: bh = bw * INPUT_H / INPUT_W
    else: bw = bh * INPUT_W / INPUT_H
    sx, sy = INPUT_W / bw, INPUT_H / bh
    inv = (1 / sx, 0, cx - bw / 2, 0, 1 / sy, cy - bh / 2)
    crop = img.convert('RGB').transform((INPUT_W, INPUT_H), Image.AFFINE, inv, resample=Image.BILINEAR, fillcolor=(0, 0, 0))
    t = (np.asarray(crop, np.float64) - MEAN) / STD
    t = torch.from_numpy(t.transpose(2, 0, 1)[None].astype(np.float32))
    with torch.no_grad():
        sxx, syy = model(t.repeat(5, 1, 1, 1))
    sxx, syy = sxx[0].numpy(), syy[0].numpy()
    kx = sxx.argmax(1) / 2.0; ky = syy.argmax(1) / 2.0
    score = np.minimum(sxx.max(1), syy.max(1))
    pts = np.stack([kx / sx + cx - bw / 2, ky / sy + cy - bh / 2], 1)
    return pts, score
def main():
    p = argparse.ArgumentParser()
    p.add_argument('image'); p.add_argument('out'); p.add_argument('--model', required=True)
    p.add_argument('--overlay'); p.add_argument('--pad', type=float, default=0.15)
    p.add_argument('--box', type=float, nargs=4)
    a = p.parse_args()
    import torch
    img = Image.open(a.image)
    box = a.box or person_box(img)
    model = torch.jit.load(a.model, map_location='cpu').eval()
    pts, score = run(model, img, box, a.pad)
    out = {'image': str(Path(a.image).resolve()), 'size': img.size, 'box': [float(v) for v in box],
           'model_sha256': hashlib.sha256(Path(a.model).read_bytes()).hexdigest(),
           'body': {n: [float(pts[i, 0]), float(pts[i, 1]), float(score[i])] for i, n in enumerate(NAMES)},
           'left_hand': [[float(pts[i, 0]), float(pts[i, 1]), float(score[i])] for i in range(91, 112)],
           'right_hand': [[float(pts[i, 0]), float(pts[i, 1]), float(score[i])] for i in range(112, 133)],
           'face': [[float(pts[i, 0]), float(pts[i, 1]), float(score[i])] for i in range(23, 91)]}
    Path(a.out).write_text(json.dumps(out, indent=1))
    if a.overlay:
        vis = img.convert('RGB').copy(); d = ImageDraw.Draw(vis); r = max(3, img.size[0] // 300)
        for i in range(133):
            px, py = pts[i]; col = (0, 255, 0) if i < 23 else (255, 255, 0) if i >= 91 else (0, 200, 255)
            d.ellipse((px - r, py - r, px + r, py + r), fill=col)
            if i < 23: d.text((px + r, py - 3 * r), NAMES[i], fill=(255, 0, 255))
        vis.save(a.overlay)
    for n in NAMES: print(n, [round(v, 1) for v in out['body'][n]])
if __name__ == '__main__': main()
