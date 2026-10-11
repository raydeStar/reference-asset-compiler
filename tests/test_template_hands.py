"""template_hands fits the template's hand onto a rig's joints, finds where a sleeve's cuff ends, and reads a skin tone."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.template_hands import (  # noqa: E402
    cuff_end, fit, frame, hand_vertices, landmarks, palm_normal, place, polygon_normals, polygons_within, skin_tone)

BONES = ["lowerarm_l", "hand_l", "index_01_l", "middle_01_l", "pinky_01_l"]
INDEX = {b: i for i, b in enumerate(BONES)}


def left_hand():
    """A left forearm and hand along +x, palm down, index toward -y (the front): points on a line with
    weights fading forearm -> hand at x=0, three knuckle clusters at x=0.1."""
    pts, w = [], []
    for x in np.linspace(-0.12, 0.08, 21):
        for y in (-0.03, 0.0, 0.03):
            pts.append((x, y, 0.0))
            t = np.clip((x + 0.02) / 0.04, 0, 1)
            w.append([1 - t, t, 0, 0, 0])
    for col, y in ((2, -0.03), (3, 0.0), (4, 0.03)):
        for dx in (0.095, 0.1, 0.105):
            pts.append((dx, y, 0.0))
            w.append([0, 0.2, 0, 0, 0][:col] + [0.8] + [0] * (4 - col))
    return np.array(pts, float), np.array(w, float)


def test_frame_is_orthonormal_and_the_left_normal_leaves_the_palm():
    f = frame([1, 0, 0.1], [0, -1, 0])
    assert np.allclose(f.T @ f, np.eye(3)) and np.isclose(np.linalg.det(f), 1.0)
    marks = {"wrist": np.zeros(3), "middle": np.array([0.1, 0, 0]), "index": np.array([0.1, -0.03, 0]),
             "pinky": np.array([0.1, 0.03, 0])}
    assert np.allclose(palm_normal(marks, "l"), [0, 0, -1])          # a T-posed left palm faces down
    mirrored = {k: v * [-1, 1, 1] for k, v in marks.items()}
    assert np.allclose(palm_normal(mirrored, "r"), [0, 0, -1])        # and so does the mirrored right one


def test_landmarks_and_hand_vertices():
    verts, weights = left_hand()
    marks = landmarks(verts, weights, INDEX, "l")
    assert abs(marks["wrist"][0]) < 0.011 and np.allclose(marks["middle"], [0.1, 0, 0])
    mask = hand_vertices(verts, weights, INDEX, "l", hand_weight=0.3, wrist_back_m=0.05)
    assert mask[verts[:, 0] > 0.0].all()                               # the hand
    assert mask[(verts[:, 0] > -0.04) & (verts[:, 0] <= 0)].all()      # the forearm lining behind the wrist
    assert not mask[verts[:, 0] < -0.07].any()                         # not the rest of the forearm


def test_fit_carries_the_template_landmarks_onto_the_rig():
    tm = {"wrist": np.array([0.5, 0.0, 1.0]), "middle": np.array([0.55, -0.02, 0.92]),
          "index": np.array([0.54, -0.05, 0.93]), "pinky": np.array([0.56, 0.02, 0.91])}
    angle = np.radians(50)
    turn = np.array([[np.cos(angle), 0, np.sin(angle)], [0, 1, 0], [-np.sin(angle), 0, np.cos(angle)]])
    gm = {k: (v - tm["wrist"]) @ turn.T * 1.2 + np.array([0.67, 0.03, 1.39]) for k, v in tm.items()}
    rot, scale = fit(tm, gm)
    assert np.isclose(scale, 1.2) and np.allclose(rot, turn)
    moved = place(np.stack(list(tm.values())), tm, gm, rot, scale)
    assert np.allclose(moved, np.stack(list(gm.values())))


def test_cuff_end_reads_the_back_of_the_hand_not_a_hanging_thumb():
    """A sleeve (a tube 6.5 cm round) to the wrist, then a flat hand whose thumb hangs 7 cm below the palm."""
    ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    sleeve = [(x, 0.065 * np.cos(a), 0.065 * np.sin(a)) for x in np.arange(-0.1, 0.0, 0.004) for a in ang]
    hand = [(x, y, z) for x in np.arange(0.002, 0.16, 0.004) for y in (-0.04, 0, 0.04) for z in (-0.015, 0.015)]
    thumb = [(x, -0.04, z) for x in np.arange(0.01, 0.08, 0.004) for z in (-0.03, -0.05, -0.07)]
    pts = np.array(sleeve + hand + thumb)
    near = np.linalg.norm(pts[:, 1:], axis=1) < 0.1
    end, height = cuff_end(pts[:, 0], pts[:, 2], near)     # +z is the back of the hand; the thumb hangs to -z
    assert abs(height - 0.065) < 0.003
    assert -0.005 <= end <= 0.005


def test_skin_tone_ignores_brows_and_highlights():
    rng = np.random.default_rng(0)
    skin = np.array([0.67, 0.38, 0.18]) + rng.normal(0, 0.01, (400, 3))
    texels = np.vstack([skin, np.full((80, 3), 0.05), np.full((60, 3), 0.98)])
    assert np.allclose(skin_tone(texels), [0.67, 0.38, 0.18], atol=0.01)


def test_polygons_within_and_normals():
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [2, 0, 0]], float)
    loops, starts, totals = np.array([0, 1, 2, 3, 1, 4, 2]), np.array([0, 4]), np.array([4, 3])
    assert polygons_within(np.array([1, 1, 1, 1, 0], bool), loops, starts, totals).tolist() == [True, False]
    assert np.allclose(polygon_normals(verts, loops, starts, totals), [[0, 0, 1], [0, 0, 1]])
