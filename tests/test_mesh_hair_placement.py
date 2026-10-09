"""Mesh hair placed by the face (transfer_mesh_hair.py --place-by-face) and kept clear of the skin (keep_hair_clear.py).

A synthetic scan carries the upper-face landmarks where a known similarity
says the character's are; the hair must move by exactly that similarity. The
landmarks are found on the scan as the conform found its seed: pixels of a
front render, bound to the scan in its own units, read back in template metres.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import keep_hair_clear as clear  # noqa: E402
import transfer_mesh_hair as transfer  # noqa: E402
from reference_asset_compiler import template_conform as tc  # noqa: E402

CAMERA = {"view": "front", "resolution": 1024, "ortho_scale": 1.0, "centre": [0.0, 0.0, 0.0],
          "right": [1.0, 0.0, 0.0], "up": [0.0, 0.0, 1.0], "forward": [0.0, 1.0, 0.0]}
# The conform: scan units ~= 2.0 * template metres @ R.T + t (a turn of 10 degrees about z).
ANGLE = np.radians(10)
ALIGN_R = np.array([[np.cos(ANGLE), -np.sin(ANGLE), 0], [np.sin(ANGLE), np.cos(ANGLE), 0], [0, 0, 1]])
ALIGNMENT = {"scale_template_to_acquisition": 2.0, "rotation": ALIGN_R.tolist(), "translation": [0.0, 0.1, -3.4]}
# The placement the scan's face should get onto the character's: 0.9 scale, 3 degrees about x, down 1 cm.
TURN = np.radians(3)
PLACE_R = np.array([[1, 0, 0], [0, np.cos(TURN), -np.sin(TURN)], [0, np.sin(TURN), np.cos(TURN)]])
PLACE = (0.9, PLACE_R, np.array([0.002, -0.004, -0.01]))


def character(n=70):
    """A head (a ring of points at face height, plus helpers) and a binding putting landmark i on vertex i."""
    rng = np.random.default_rng(3)
    face = np.c_[rng.uniform(-0.06, 0.06, n), rng.uniform(-0.12, -0.09, n), rng.uniform(1.62, 1.74, n)]
    verts = np.vstack([face, [[0.03, -0.1, 1.69], [-0.03, -0.1, 1.69]]])
    binding = {"template_vertices": len(verts), "vertices": [[i, i, i] for i in range(n)],
               "barycentric": [[1.0, 0.0, 0.0]] * n}
    binding["vertices"][3] = binding["barycentric"][3] = None          # an unbound landmark, as in the real binding
    return verts, binding


def scan_for(head_landmarks):
    """A scan (template metres, as the conform NPZ keeps it) with a small camera-facing triangle at each landmark
    the placement should carry onto the head's, and the pixels where the front render sees them."""
    s, r, t = PLACE
    marks = (head_landmarks - t) @ r / s                              # inverse of the placement
    raw = tc.apply_similarity(marks, ALIGNMENT["scale_template_to_acquisition"], ALIGN_R,
                              np.array(ALIGNMENT["translation"]))
    verts, tris = [], []
    for p in raw:                                                     # triangles around each point, in scan units
        base = len(verts)
        verts += [p + [-0.0004, 0, -0.0004], p + [0.0004, 0, -0.0004], p + [0, 0, 0.0006]]   # small: none overlap
        tris.append([base, base + 1, base + 2])
    raw_verts = np.array(verts)
    acq_m = (raw_verts - np.array(ALIGNMENT["translation"])) @ ALIGN_R / ALIGNMENT["scale_template_to_acquisition"]
    pixels, _ = tc.camera_project(raw, CAMERA)
    return acq_m, np.array(tris), pixels, marks


def test_scan_landmarks_come_back_in_template_metres():
    head, _ = character()
    acq_m, tris, pixels, marks = scan_for(head[:70])
    points, found = transfer.scan_points(acq_m, tris, CAMERA, pixels, ALIGNMENT)
    assert found.all()
    assert np.allclose(points, marks, atol=1e-9)


def test_the_hair_moves_by_the_upper_faces_similarity():
    head, binding = character()
    acq_m, tris, pixels, _ = scan_for(head[:70])
    full_pixels = np.zeros((68, 2))
    full_pixels[:68] = pixels[:68]
    conform = {"acq_verts": acq_m, "acq_tris": tris}
    hair = np.random.default_rng(5).uniform([-0.1, -0.1, 1.7], [0.1, 0.1, 1.9], (50, 3))
    placed, report = transfer.place_by_face(hair, conform, {"alignment": ALIGNMENT}, {"verts": head}, full_pixels,
                                            CAMERA, binding)
    assert np.allclose(placed, tc.apply_similarity(hair, *PLACE), atol=1e-9)
    assert report["landmarks"] == list(transfer.UPPER_FACE)
    assert report["scale"] == pytest.approx(0.9) and report["rotation_deg"] == pytest.approx(3.0, abs=1e-3)
    assert report["residual_mm"]["max"] < 1e-6


def test_too_few_landmarks_on_the_scan_stop_the_placement():
    head, binding = character()
    acq_m, tris, pixels, _ = scan_for(head[:70])
    off = pixels[:68].copy()
    off[list(transfer.UPPER_FACE)[5:]] = -50.0                          # off the render: not on the scan
    with pytest.raises(ValueError, match="only 5 upper-face landmarks"):
        transfer.place_by_face(np.zeros((1, 3)), {"acq_verts": acq_m, "acq_tris": tris}, {"alignment": ALIGNMENT},
                               {"verts": head}, off, CAMERA, binding)


def test_a_head_of_another_template_is_refused():
    head, binding = character()
    with pytest.raises(ValueError, match="vertices"):
        transfer.head_points(head[:10], binding)


def test_hair_too_close_to_the_skin_is_pushed_out_to_the_clearance():
    skin = np.array([[x, y, 0.0] for x in np.linspace(-0.1, 0.1, 21) for y in np.linspace(-0.1, 0.1, 21)])
    normals = np.tile([0.0, 0.0, 1.0], (len(skin), 1))
    points = np.array([[0.0, 0.0, -0.01], [0.02, 0.0, 0.001], [0.0, 0.03, 0.005], [0.01, 0.01, 0.002]])
    out, moved = clear.keep_clear(points, skin, normals, 0.002)
    assert moved.tolist() == [True, True, False, False]
    assert np.allclose(out[:, 2], [0.002, 0.002, 0.005, 0.002])
    assert np.array_equal(out[:, :2], points[:, :2])


def sphere_head(tmp_path):
    """A conformed-head NPZ: a sphere of quads (all body), two eye vertices at its middle."""
    lats, lons = np.radians(np.arange(-80, 81, 10)), np.radians(np.arange(0, 360, 15))
    verts = [[0.1 * np.cos(t) * np.cos(p), 0.1 * np.cos(t) * np.sin(p), 1.7 + 0.1 * np.sin(t)] for t in lats for p in lons]
    n = len(lons)
    quads = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j)
             for i in range(len(lats) - 1) for j in range(n)]
    path = tmp_path / "head.npz"
    np.savez(path, verts=np.array(verts), loops=np.array(quads).ravel(), loop_starts=np.arange(0, 4 * len(quads), 4),
             loop_totals=np.full(len(quads), 4), vg__body=np.arange(len(verts)),
             **{"vg__helper-l-eye": np.array([n * 8 + 18])})
    return path


def test_the_clearance_stage_keeps_hair_outside_a_head(tmp_path):
    head = sphere_head(tmp_path)
    rng = np.random.default_rng(9)
    d = rng.normal(size=(200, 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    d[:, 2] = np.abs(d[:, 2])                                          # over the top half
    radius = rng.uniform(0.09, 0.13, 200)
    hair = tmp_path / "hair.npz"
    np.savez(hair, verts=(np.array([0, 0, 1.7]) + d * radius[:, None]).astype(np.float32), tris=np.zeros((0, 3)),
             loop_uv=np.zeros((0, 2)))
    out = tmp_path / "clear.npz"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/keep_hair_clear.py"), str(hair), str(head), str(out),
                             "--clearance", "0.003"], capture_output=True, text=True, check=True)
    report = json.loads(result.stdout.strip().splitlines()[-1])
    after = np.linalg.norm(np.load(out)["verts"] - [0, 0, 1.7], axis=1)
    # The sphere's faceting puts its surface up to ~1 mm inside the vertex radius.
    assert after.min() > 0.1 + 0.003 - 0.0015
    assert report["pushed"] == int((np.abs(after - radius) > 1e-6).sum()) > 0   # the report counts what moved
    assert np.allclose(after[radius > 0.11], radius[radius > 0.11], atol=1e-6)   # far hair is untouched
