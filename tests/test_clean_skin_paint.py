"""clean_skin_paint.py lifts a hair blot off skin and keeps the brows and the scalp."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import clean_skin_paint  # noqa: E402

SKIN = (70, 120, 190)   # BGR
HAIR = (20, 25, 35)


def template(tmp_path, n=8):
    """An n x n grid of quads filling UV space, at head height; the top row is scalp."""
    ij = np.stack(np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij"), -1).reshape(-1, 2)
    verts = np.c_[ij / n, np.full(len(ij), 1.6)]
    vid = lambda i, j: i * (n + 1) + j  # noqa: E731
    loops, starts = [], []
    for i in range(n):
        for j in range(n):
            starts.append(len(loops))
            loops += [vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)]
    loops = np.array(loops)
    uv = verts[loops, :2]
    scalp = np.unique(loops.reshape(-1, 4)[[k for k in range(n * n) if k % n == n - 1]])   # j = n-1: top row (v near 1)
    path = tmp_path / "template.npz"
    np.savez(path, verts=verts, loops=loops, loop_starts=np.array(starts), loop_totals=np.full(n * n, 4),
             loop_uv=uv, vg__body=np.arange(len(verts)), vg__scalp=scalp)
    return path


def test_blot_goes_brows_and_scalp_stay(tmp_path):
    size = 512
    tex = np.full((size, size, 3), SKIN, np.uint8)
    cv2.circle(tex, (256, 300), 10, HAIR, -1)                  # a hair blot on the cheek
    cv2.rectangle(tex, (100, 200), (160, 210), HAIR, -1)       # a brow
    cv2.rectangle(tex, (0, 0), (size, 30), HAIR, -1)           # the scalp's root colour (v near 1)
    cv2.imwrite(str(tmp_path / "tex.png"), tex)
    # Brow landmarks 17-21 bound to the vertices nearest the brow (one vertex each, weight 1).
    n = 8
    brow_uv = [(100 + 15 * k) / size for k in range(5)]
    v_of = lambda u, v: int(round(u * n)) * (n + 1) + int(round(v * n))  # noqa: E731
    vertices = [None] * 70
    bary = [None] * 70
    for k, u in enumerate(brow_uv):
        vv = 1 - 205 / size
        vertices[17 + k] = [v_of(u, vv)] * 3
        bary[17 + k] = [1.0, 0.0, 0.0]
    (tmp_path / "binding.json").write_text(json.dumps({"vertices": vertices, "barycentric": bary}), encoding="utf-8")
    out = tmp_path / "out.png"
    clean_skin_paint.main(["--template", str(template(tmp_path)), "--binding", str(tmp_path / "binding.json"),
                           "--texture", str(tmp_path / "tex.png"), "--out", str(out), "--work-size", "512",
                           "--blot-frac", "0.08", "--keep-margin-frac", "0.08", "--head-min-z", "1.4"])
    img = cv2.imread(str(out)).astype(int)
    assert np.abs(img[300, 256] - SKIN).max() < 30     # the blot is skin now
    assert img[205, 130].max() < 60                      # the brow keeps its colour
    assert img[10, 256].max() < 60                       # so does the scalp


def test_foreign_hue_on_skin_goes_eye_stays(tmp_path):
    size = 512
    tex = np.full((size, size, 3), SKIN, np.uint8)
    cv2.line(tex, (300, 300), (330, 330), (60, 170, 120), 4)      # BGR: a yellow-green streak on the cheek
    cv2.circle(tex, (192, 192), 10, (40, 160, 40), -1)           # an iris inside the eye outline
    cv2.imwrite(str(tmp_path / "tex.png"), tex)
    # The eye outline (landmarks 36-41) on grid vertices round the iris: vertex (i, j) sits at pixel
    # (64 i, 512 - 64 j) in this 8 x 8 template's UVs.
    vertices, bary = [None] * 70, [None] * 70
    for k, (i, j) in enumerate([(2, 5), (3, 6), (4, 5), (3, 4), (2, 5), (4, 5)]):
        vertices[36 + k] = [i * 9 + j] * 3
        bary[36 + k] = [1.0, 0.0, 0.0]
    (tmp_path / "binding.json").write_text(json.dumps({"vertices": vertices, "barycentric": bary}), encoding="utf-8")
    out = tmp_path / "out.png"
    clean_skin_paint.main(["--template", str(template(tmp_path)), "--binding", str(tmp_path / "binding.json"),
                           "--texture", str(tmp_path / "tex.png"), "--out", str(out), "--work-size", "512",
                           "--min-depth", "250", "--foreign-hue", "55", "300", "--head-min-z", "1.4"])
    img = cv2.imread(str(out)).astype(int)
    assert np.abs(img[315, 315] - SKIN).max() < 30     # the streak is skin now
    assert img[192, 192, 1] > img[192, 192, 2] + 60     # the iris keeps its green
