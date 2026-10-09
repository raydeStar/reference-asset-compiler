"""fit_head_placement.py: the template head's scale and location from face landmarks, no render.

A synthetic head (an open tube, so its neck ring is the lowest open edge) gets
landmarks bound to known surface points, is placed with a known scale and
location, and its landmarks are projected into a source frame and written as a
DWPose file detected on an upscaled crop. The fit must give the placement back.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import fit_head_placement as fhp  # noqa: E402

CAMERA = {"image_px": [1000, 1000], "px_per_m": 500.0, "front_origin_px": [500.0, 520.0]}
LIFT = 0.9
AROUND, RINGS = 16, 7


def tube(centre_y=-0.02):
    """Quads around z 1.45..1.75, open at both ends: polygons as loops/starts/totals."""
    verts = [(0.08 * math.cos(2 * math.pi * k / AROUND), centre_y + 0.08 * math.sin(2 * math.pi * k / AROUND), z)
             for z in np.linspace(1.45, 1.75, RINGS) for k in range(AROUND)]
    loops = [i for r in range(RINGS - 1) for k in range(AROUND)
             for i in (r * AROUND + k, r * AROUND + (k + 1) % AROUND,
                       (r + 1) * AROUND + (k + 1) % AROUND, (r + 1) * AROUND + k)]
    polys = (RINGS - 1) * AROUND
    return {"verts": np.array(verts), "loops": np.array(loops), "loop_starts": np.arange(polys) * 4,
            "loop_totals": np.full(polys, 4), "keep_polys": np.arange(polys)}


def binding(head, rng):
    """Landmarks on the front half of the tube; the jaw (0-16) left unbound, like a missed detection."""
    count = len(head["verts"])
    vertices, bary = [], []
    for i in range(70):
        if i < 17:
            vertices.append(None)
            bary.append(None)
            continue
        ring = rng.integers(1, RINGS - 1)
        k = rng.integers(AROUND // 2 + 1, AROUND - 1)          # y < 0: the face side
        vertices.append([int(ring * AROUND + k), int(ring * AROUND + k + 1), int((ring + 1) * AROUND + k)])
        w = rng.random(3)
        bary.append((w / w.sum()).tolist())
    return {"template_vertices": count, "template_sha256": "synthetic", "vertices": vertices, "barycentric": bary}


def write_case(tmp_path, scale, location, noise_px=0.0, seed=1):
    rng = np.random.default_rng(seed)
    head = tube()
    np.savez(tmp_path / "head.npz", **head)
    bound = binding(head, rng)
    (tmp_path / "binding.json").write_text(json.dumps(bound))
    points = fhp.head_points(head["verts"], bound)
    pixels = fhp.project(np.nan_to_num(points), scale, location, CAMERA, LIFT)
    pixels += rng.normal(0.0, noise_px, pixels.shape)
    box, up = (400, 0, 600, 200), 5.0                       # detected on a 5x upscaled crop
    crop = (pixels[:68] - np.array(box[:2])) * up
    (tmp_path / "landmarks.json").write_text(json.dumps({"size": [1000, 1000], "landmarks_68": crop.tolist()}))
    return head, box


def run(tmp_path, box, *extra):
    return fhp.main(["--head", str(tmp_path / "head.npz"), "--binding", str(tmp_path / "binding.json"),
                     "--source-camera", "500", "1000", "1000", "500", "520", "--body-lift", str(LIFT),
                     "--reference-landmarks", str(tmp_path / "landmarks.json"),
                     "--reference-crop", *map(str, box), "--landmarks", "features", "--out", str(tmp_path / "out"),
                     *extra])


def test_the_fit_gives_the_placement_back(tmp_path):
    # The eye centres (68, 69) are means of the eye outlines in the picture, not
    # bound points, so this fit uses 27..67, all bound points.
    _, box = write_case(tmp_path, 0.9, (0.005, 0.0, 0.15))
    assert run(tmp_path, box) == 0
    placement = json.loads((tmp_path / "out/placement.json").read_text())
    assert placement["scale"] == pytest.approx(0.9, abs=1e-9)
    assert placement["location"][0] == pytest.approx(0.005, abs=1e-9)
    assert placement["location"][2] == pytest.approx(0.15, abs=1e-9)
    assert placement["rms_error_px"] < 1e-6
    # Depth from the neck: the tube's ring is centred on y = -0.02, put over y = 0.
    assert placement["location"][1] == pytest.approx(0.9 * 0.02, abs=1e-9)
    assert placement["landmark_indices"] == list(range(27, 68))


def test_depth_can_be_set_and_another_placement_compared(tmp_path):
    _, box = write_case(tmp_path, 0.9, (0.005, 0.0, 0.15))
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"scale": 0.9, "location": [0.005, 0.03, 0.16]}))
    assert run(tmp_path, box, "--location-y", "0.03", "--compare", str(other)) == 0
    placement = json.loads((tmp_path / "out/placement.json").read_text())
    assert placement["location"][1] == 0.03
    shift = placement["compared_with"]
    assert shift["location_change_mm"] == pytest.approx([0.0, 0.0, -10.0], abs=1e-6)
    assert shift["landmark_shift_xz_mm"]["max"] == pytest.approx(10.0, abs=1e-6)
    assert shift["landmark_shift_px"]["mean"] == pytest.approx(5.0, abs=1e-6)


def test_noisy_landmarks_fit_close_and_a_bad_fit_is_refused(tmp_path):
    _, box = write_case(tmp_path, 0.9, (0.005, 0.0, 0.15), noise_px=0.5, seed=3)
    assert run(tmp_path, box) == 0
    placement = json.loads((tmp_path / "out/placement.json").read_text())
    assert placement["scale"] == pytest.approx(0.9, rel=0.02)
    assert 0.2 < placement["rms_error_px"] < 1.0
    assert run(tmp_path, box, "--max-rms-px", "0.1") == 1


def test_a_head_from_another_template_is_refused(tmp_path):
    _, box = write_case(tmp_path, 0.9, (0.0, 0.0, 0.15))
    bound = json.loads((tmp_path / "binding.json").read_text())
    bound["template_vertices"] += 1
    (tmp_path / "binding.json").write_text(json.dumps(bound))
    with pytest.raises(SystemExit, match="Bind the template"):
        run(tmp_path, box)


def test_the_default_crop_frames_the_head_above_the_origin():
    camera = {"image_px": [1536, 1024], "px_per_m": 538.89, "front_origin_px": [765.5, 500.0]}
    # A 1.8 m figure centred on the origin: its top is 0.9 m above it.
    x0, y0, x1, y1 = fhp.default_crop(camera, 0.899942875, 1.8)
    assert (x0 + x1) / 2 == pytest.approx(765.5, abs=1)
    assert y0 == round(500 - 0.9 * 538.89 - 0.02 * 538.89)
    assert y1 - y0 == pytest.approx(0.31 * 538.89, abs=1)


def test_template_landmarks_bind_to_the_surface_under_them(tmp_path):
    # A flat face-on grid: every landmark pixel binds to the point under it.
    n = 11
    xs = np.linspace(-0.5, 0.5, n)
    verts = np.array([(x, 0.0, z) for z in xs for x in xs])
    quads = [(r * n + c, r * n + c + 1, (r + 1) * n + c + 1, (r + 1) * n + c) for r in range(n - 1) for c in range(n - 1)]
    bones = np.array(["head", "neck_01"])
    np.savez(tmp_path / "template.npz", verts=verts, loops=np.array(quads).ravel(),
             loop_starts=np.arange(len(quads)) * 4, loop_totals=np.full(len(quads), 4),
             weights=np.tile([1.0, 0.0], (len(verts), 1)).astype(np.float32), bone_names=bones,
             vg__body=np.arange(len(verts)))
    camera = {"resolution": 100, "ortho_scale": 1.0, "centre": [0, -1, 0], "right": [1, 0, 0],
              "up": [0, 0, 1], "forward": [0, 1, 0]}
    (tmp_path / "camera.json").write_text(json.dumps(camera))
    rng = np.random.default_rng(0)
    pixels = rng.uniform(10, 90, (68, 2))
    (tmp_path / "landmarks.json").write_text(json.dumps({"size": [100, 100], "landmarks_68": pixels.tolist()}))
    bound = fhp.bind_template(tmp_path / "template.npz", tmp_path / "landmarks.json", tmp_path / "camera.json")
    points = fhp.head_points(verts, bound)
    expected = np.c_[(pixels[:, 0] - 50) / 100, np.zeros(68), (50 - pixels[:, 1]) / 100]
    assert np.allclose(points[:68], expected, atol=1e-9)
