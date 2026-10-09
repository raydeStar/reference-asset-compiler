"""view_projection's surface fill and smoothed normals on small synthetic meshes (no pictures needed)."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler import template_conform as tc  # noqa: E402
from reference_asset_compiler import view_projection as vp  # noqa: E402


def strip(n, x0=0.0, y=0.0, length=1.0, zigzag=0.0):
    """A ribbon of n quads along x (two rows of vertices), optionally pleated up and down."""
    xs = np.linspace(x0, x0 + length, n + 1)
    z = np.where(np.arange(n + 1) % 2, zigzag, 0.0)
    verts = np.concatenate([np.c_[xs, np.full(n + 1, y), z], np.c_[xs, np.full(n + 1, y + 0.1), z]])
    tris = []
    for i in range(n):
        a, b, c, d = i, i + 1, n + 2 + i, n + 1 + i
        tris += [(a, b, c), (a, c, d)]
    return verts.astype(float), np.array(tris)


def one_texel_per_vertex(verts, tris):
    """A 'texture' with one texel sitting exactly on each vertex: tri_id/bary that pick the vertex."""
    n = len(verts)
    tri_id = np.full((1, n), -1)
    bary = np.zeros((1, n, 3))
    for v in range(n):
        t = int(np.nonzero((tris == v).any(1))[0][0])
        tri_id[0, v] = t
        bary[0, v, list(tris[t]).index(v)] = 1.0
    return tri_id, bary


def test_the_fill_is_a_smooth_blend_between_the_paint_either_side():
    verts, tris = strip(10)
    tri_id, bary = one_texel_per_vertex(verts, tris)
    x = verts[:, 0]
    tex = np.zeros((1, len(verts), 3))
    tex[0, x <= 0.0] = [1.0, 0.0, 0.0]          # red paint at one end
    tex[0, x >= 1.0] = [0.0, 0.0, 1.0]          # blue at the other
    keep = ((x <= 0.0) | (x >= 1.0)).astype(float)[None]
    out, record = vp.fill_unseen_surface(tex, keep, tri_id, bary, verts, tris)
    assert record["source_vertices"] == 4 and record["filled_vertices"] == len(verts) - 4
    # A blend of the two paints only (red + blue = 1), near linear along the ribbon, and monotonic.
    assert out[0, :, 0] + out[0, :, 2] == pytest.approx(np.ones(len(x)), abs=1e-6)
    assert out[0, :, 0] == pytest.approx(1.0 - x, abs=0.03)
    for row in (slice(0, 11), slice(11, 22)):      # each edge of the ribbon, along x
        assert np.all(np.diff(out[0, row, 2]) > 0)


def test_the_fill_never_reaches_across_a_gap():
    # Two ribbons a centimetre apart: the near ribbon is all grey outline paint, the far one navy at one end.
    a_verts, a_tris = strip(10)
    b_verts, b_tris = strip(10, y=0.11)
    verts = np.concatenate([a_verts, b_verts])
    tris = np.concatenate([a_tris, b_tris + len(a_verts)])
    tri_id, bary = one_texel_per_vertex(verts, tris)
    tex = np.zeros((1, len(verts), 3))
    tex[0, :len(a_verts)] = 0.8                                   # ribbon A: painted grey everywhere
    keep = np.zeros((1, len(verts)))
    keep[0, :len(a_verts)] = 1.0
    far_end = np.arange(len(verts)) >= len(a_verts)
    far_end &= verts[:, 0] <= 0.0
    tex[0, far_end] = [0.05, 0.07, 0.2]
    keep[0, far_end] = 1.0
    out, _ = vp.fill_unseen_surface(tex, keep, tri_id, bary, verts, tris)
    # Ribbon B is navy all along, though grey paint lies a centimetre away the whole length.
    assert out[0, len(a_verts):] == pytest.approx(np.tile([0.05, 0.07, 0.2], (len(b_verts), 1)), abs=1e-4)
    # The nearest-point fill does reach across.
    painted = keep > 0
    near = vp.fill_unseen_3d(tex, painted, np.ones_like(painted), verts[None], k=6)
    assert near[0, len(a_verts):, 0].max() > 0.5


def test_paint_at_the_edge_of_a_view_fades_into_the_fill():
    verts, tris = strip(4)
    tri_id, bary = one_texel_per_vertex(verts, tris)
    x = verts[:, 0]
    tex = np.full((1, len(verts), 3), 0.2)
    edge = np.isclose(x, 0.5)
    tex[0, edge] = 0.9                   # a light outline pixel
    keep = np.where(edge, 0.5, 1.0)[None]
    out, record = vp.fill_unseen_surface(tex, keep, tri_id, bary, verts, tris)
    assert record["feathered_texels"] == 2
    assert out[0, edge, 0] == pytest.approx(0.5 * 0.9 + 0.5 * 0.2, abs=1e-4)
    assert out[0, ~edge, 0] == pytest.approx(0.2)


def test_a_part_with_no_paint_takes_the_median():
    a_verts, a_tris = strip(3)
    b_verts, b_tris = strip(3, y=1.0)
    verts = np.concatenate([a_verts, b_verts])
    tris = np.concatenate([a_tris, b_tris + len(a_verts)])
    tri_id, bary = one_texel_per_vertex(verts, tris)
    tex = np.zeros((1, len(verts), 3))
    tex[0, :len(a_verts)] = [0.3, 0.2, 0.1]
    keep = np.zeros((1, len(verts)))
    keep[0, :len(a_verts)] = 1.0
    out, _ = vp.fill_unseen_surface(tex, keep, tri_id, bary, verts, tris)
    assert out[0, len(a_verts):] == pytest.approx(np.tile([0.3, 0.2, 0.1], (len(b_verts), 1)), abs=1e-3)


def test_smoothed_normals_see_through_a_pleat():
    # Pleats steep enough that every facet leans 45 degrees toward +-x; on average the ribbon faces straight up.
    verts, tris = strip(40, length=0.4, zigzag=0.01)
    raw = tc.vertex_normals(verts, tris)
    faceted = np.abs(raw[:, 0]).max()
    smooth = vp.smooth_normals(verts, tris, raw, 0.05)
    inner = (verts[:, 0] > 0.08) & (verts[:, 0] < 0.32)
    assert faceted > 0.3
    assert np.abs(smooth[inner, 0]).max() < 0.1 and smooth[inner, 2].min() > 0.99 * np.abs(smooth[inner, 2]).max()
    assert vp.smooth_normals(verts, tris, raw, 0.0) == pytest.approx(raw)
