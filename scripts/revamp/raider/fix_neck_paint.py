"""Repaint the lower neck of the baked face: the painted head ended in a ragged painted edge at the neck, which
the bake carried onto the throat as a jagged light line, and the neck that now reaches into the collar has no
paint below that edge. Skin triangles below a clean line (a little above the painted edge) take the colour of
the band just above it, blurred, with a soft blend across the line.

  python fix_neck_paint.py <bake_dir>     (ComfyUI Python: numpy, PIL, OpenCV)
Reads face_skin.png, skin-tris.npy, neck.json; writes face_skin.png (the original kept as face_skin.orig.png).
"""
import sys, json, shutil
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

d = Path(sys.argv[1]); img_p = d / "face_skin.png"
if not (d / "face_skin.orig.png").exists(): shutil.copyfile(img_p, d / "face_skin.orig.png")
im = np.asarray(Image.open(d / "face_skin.orig.png").convert("RGB")).astype(np.float32)
H, W = im.shape[:2]
T = np.load(d / "skin-tris.npy"); zmin = json.load(open(d / "neck.json"))["scan_min_z"]
def mask(sel):
    m = Image.new("L", (W, H), 0); dr = ImageDraw.Draw(m)
    for t in T[sel]: dr.polygon([(t[0] * W, (1 - t[1]) * H), (t[2] * W, (1 - t[3]) * H), (t[4] * W, (1 - t[5]) * H)], fill=255)
    return np.asarray(m) > 0
z = T[:, 6]; painted = im.sum(2) >= 15
# the clean line: the lowest height above which the bake is (nearly) all painted. Below it the painted head's
# neck was ragged or missing and the bake left gaps and a jagged edge.
CLEAN = None
for lo in np.arange(z.min(), z.max(), 0.01):
    mm = mask((z >= lo) & (z < lo + 0.02))
    if mm.sum() > 500 and painted[mm].mean() > 0.92: CLEAN = float(lo); break
CLEAN = CLEAN if CLEAN is not None else zmin + 0.06
# the painted head's ragged edge also runs inside the painted area, right under the chin: the line goes no lower
# than just below the chin (MediaPipe landmark 152)
chin = json.load(open(d / "neck.json")).get("chin_z")
if chin is not None: CLEAN = max(CLEAN, float(chin) - 0.012)
BLEND = 0.012
below = mask(z < CLEAN); blend = mask((z >= CLEAN) & (z < CLEAN + BLEND))
band = mask((z >= CLEAN - 0.08) & (z < CLEAN)) & painted          # painted neck skin only, never the gaps
skin = np.median(im[band], axis=0) if band.any() else np.array([150, 95, 70], np.float32)
import cv2
def gblur(a, r=40):   # Pillow cannot blur float images; OpenCV can
    return cv2.GaussianBlur(np.ascontiguousarray(a, dtype=np.float32), (0, 0), r)
seed = np.zeros_like(im); seed[band] = im[band]; wgt = band.astype(np.float32)
numr = np.stack([gblur(seed[..., k], 60) for k in range(3)], -1); den = gblur(wgt, 60)[..., None]
field = np.where(den > 1e-3, numr / np.maximum(den, 1e-3), skin)
out = im.copy()
out[below] = field[below]
out[blend] = 0.5 * im[blend] + 0.5 * field[blend]
print("NECK clean line z", round(CLEAN, 3))
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(img_p)
print("NECK_PAINT_OK repainted texels", int(below.sum()), "blend", int(blend.sum()), "skin", skin.round(1).tolist())
