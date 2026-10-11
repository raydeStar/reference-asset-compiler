"""shoulder_weights keeps a T-pose scan's arm weights on the arm: inboard to the clavicle, under the arm to the spine."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.shoulder_weights import armpit_height, refine, smooth_across_layers  # noqa: E402

BONES = ["spine_04", "spine_05", "clavicle_l", "upperarm_l", "upperarm_twist_01_l", "lowerarm_l"]
SHOULDER = np.array([0.16, 0.0, 1.41])


def figure():
    """A left arm along +x (a tube of points round z=1.41, radius 0.1 from x 0.16 to 0.5) over a torso slab
    reaching to x 0.2 (inside the shoulder joint + 8 cm, as a body is)."""
    xs = np.linspace(0.16, 0.5, 18)
    ring = [(np.cos(a) * 0.1, np.sin(a) * 0.1) for a in np.linspace(0, 2 * np.pi, 12, endpoint=False)]
    arm = np.array([[x, y, 1.41 + z] for x in xs for y, z in ring])
    torso = np.array([[x, y, z] for x in np.linspace(0.0, 0.2, 9) for y in (-0.12, 0.12) for z in np.linspace(1.0, 1.5, 11)])
    return np.vstack([arm, torso]), len(arm)


def test_armpit_is_the_sleeve_underside():
    pos, _ = figure()
    assert abs(armpit_height(pos, SHOULDER, 1.0) - 1.31) < 0.01


def test_inboard_goes_to_clavicle_under_arm_to_spine_and_outboard_stays():
    pos, n_arm = figure()
    w = np.zeros((len(pos), len(BONES)))
    w[:, 3] = 0.8                     # upper arm everywhere (the bleed a voxel solve leaves)
    w[:, 1] = 0.2
    new, report = refine(w, BONES, pos, {"l": SHOULDER})
    assert np.allclose(new.sum(1), 1.0)
    ua, cl, sp5 = 3, 2, 1
    far_arm = (np.arange(len(pos)) < n_arm) & (pos[:, 0] > 0.3)
    assert np.allclose(new[far_arm, ua], w[far_arm, ua])                  # the arm keeps the arm
    inboard = (pos[:, 0] > 0.11) & (pos[:, 0] < 0.13) & (pos[:, 2] > 1.4)
    assert new[inboard, ua].max() < 1e-6 and new[inboard, cl].min() > 0.7   # inboard by the joint: clavicle
    chest = (pos[:, 0] < 0.06) & (pos[:, 2] > 1.4)
    assert new[chest, ua].max() < 1e-6 and new[chest, cl].max() < 1e-6     # by the breastbone: the spine
    assert new[chest, sp5].min() > 0.9
    under = (pos[:, 0] > 0.15) & (pos[:, 2] < 1.2)
    assert new[under, ua].max() < 1e-6 and new[under, sp5].min() > 0.9      # under the arm: the spine it followed
    assert report["moved_to_spine"] > 0 and report["moved_to_clavicle"] > 0


def test_influences_capped():
    pos, _ = figure()
    w = np.full((len(pos), len(BONES)), 1.0 / len(BONES))
    new, _ = refine(w, BONES, pos, {"l": SHOULDER}, max_influences=4)
    assert ((new > 0).sum(1) <= 4).all() and np.allclose(new.sum(1), 1.0)


def test_layers_millimetres_apart_take_one_weight_and_the_rest_stays():
    """A lapel 5 mm over its shirt, the lapel on spine_05 + clavicle, the shirt on spine_04: smoothed, facing
    vertices end up with nearly the same weights; a vertex outside the region keeps its own."""
    grid = np.array([[x, 0.0, z] for x in np.arange(0.0, 0.06, 0.004) for z in np.arange(1.2, 1.3, 0.004)])
    shirt, lapel = grid, grid + [0, -0.005, 0]
    far = np.array([[0.3, 0.0, 1.25]])
    pos = np.vstack([shirt, lapel, far])
    w = np.zeros((len(pos), len(BONES)))
    w[:len(grid), 0] = 1.0                              # shirt: spine_04
    w[len(grid):2 * len(grid), 1] = 0.7                 # lapel: spine_05 + clavicle
    w[len(grid):2 * len(grid), 2] = 0.3
    w[-1, 3] = 1.0
    region = np.ones(len(pos), bool)
    region[-1] = False
    new, report = smooth_across_layers(w, pos, region, radius_m=0.015, iterations=2)
    assert np.allclose(new.sum(1), 1.0) and report["layer_vertices"] == len(pos) - 1
    inner = (grid[:, 0] > 0.015) & (grid[:, 0] < 0.045) & (grid[:, 2] > 1.215) & (grid[:, 2] < 1.285)
    gap = np.abs(new[:len(grid)][inner] - new[len(grid):2 * len(grid)][inner]).max()
    assert gap < 0.1                                     # was 1.0 (spine_04) apart
    assert np.allclose(new[-1], w[-1])
