"""An inferred view must not contaminate surfaces outside its trusted region."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler import view_projection as vp


def test_world_region_excludes_paint_without_removing_surface_coverage():
    verts = np.array([[-0.5, 0, -0.5], [0.5, 0, -0.5], [0.5, 0, 0.5], [-0.5, 0, 0.5]])
    tris = np.array([[0, 1, 2], [0, 2, 3]])
    uv = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
    normals = np.tile([0, -1, 0], (4, 1))
    red = vp.View("front", np.tile([1, 0, 0], (16, 16, 1)), 10, np.eye(2), np.array([8, 8]))
    tex, _, painted, where = vp.bake([red], verts, normals, tris, uv, tris, 16,
                                    (verts, tris), view_weights={"front": lambda p: (p[:, 0] < 0)})
    left = where[..., 0] < -0.1
    right = where[..., 0] > 0.1
    assert painted[left].all()
    assert not painted[right].any()
    np.testing.assert_allclose(tex[left], np.tile([1, 0, 0], (left.sum(), 1)))
    np.testing.assert_allclose(tex[right], 0)


def test_default_projection_remains_unchanged_with_unrestricted_region():
    verts = np.array([[-0.5, 0, -0.5], [0.5, 0, -0.5], [0, 0, 0.5]])
    tris = np.array([[0, 1, 2]])
    uv = np.array([[0, 0], [1, 0], [0.5, 1]], dtype=float)
    normals = np.tile([0, -1, 0], (3, 1))
    view = vp.View("front", np.tile([0.2, 0.4, 0.7], (16, 16, 1)), 10, np.eye(2), np.array([8, 8]))
    args = ([view], verts, normals, tris, uv, tris, 16, (verts, tris))
    before = vp.bake(*args)
    after = vp.bake(*args, view_weights={"front": lambda p: np.ones(len(p))})
    for a, b in zip(before, after):
        np.testing.assert_array_equal(a, b)
