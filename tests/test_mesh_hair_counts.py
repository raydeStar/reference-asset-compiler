"""reduce_mesh_hair.py reports the triangles that ship, and says when they miss the request.

The quadric collapse lays some thin blades' two sides onto each other (the same
three vertices twice); Blender's mesh validation then drops the copy at the
bake, so character-02's hair shipped 36,587 triangles for a 40,000 request while
its receipt said 40,000. The copies are now dropped in the reduction and every
count that misses the request by more than 2% is a warning.
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

import reduce_mesh_hair as reduce  # noqa: E402


def test_repeated_faces_are_dropped_in_any_order_or_winding():
    tris = np.array([[0, 1, 2], [2, 1, 0], [1, 2, 0], [0, 2, 3], [3, 4, 5], [0, 2, 3]])
    assert reduce.unique_faces(tris).tolist() == [[0, 1, 2], [0, 2, 3], [3, 4, 5]]


def test_a_count_off_the_request_by_more_than_two_percent_is_a_warning():
    assert reduce.count_warning(40000, 39999) is None
    assert reduce.count_warning(40000, 39200) is None                  # exactly 2% off
    assert "36,587" in reduce.count_warning(40000, 36587, "the shipped hair")
    assert "40,000 requested" in reduce.count_warning(40000, 36587)
    assert "20,467" in reduce.count_warning(9000, 20467)                 # a floor above the request


def pieces(n):
    """n separate quads, each also covered by its two triangles' reversed copies."""
    verts, tris = [], []
    for k in range(n):
        base = len(verts)
        verts += [[k, 0, 0], [k + 0.5, 0, 0], [k + 0.5, 0.5, 0], [k, 0.5, 0]]
        tris += [[base, base + 1, base + 2], [base, base + 2, base + 3],
                 [base + 2, base + 1, base], [base + 3, base + 2, base]]
    return np.array(verts, float), np.array(tris)


def run(tmp_path, triangles):
    verts, tris = pieces(50)
    source, out = tmp_path / "hair.npz", tmp_path / "low.npz"
    np.savez(source, verts=verts, tris=tris)
    result = subprocess.run([sys.executable, str(ROOT / "scripts/reduce_mesh_hair.py"), str(source), str(out),
                             "--triangles", str(triangles)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout.strip().splitlines()[-1]), result.stderr, np.load(out)


def test_the_reported_count_is_the_count_written_and_a_miss_is_reported(tmp_path):
    pytest.importorskip("fast_simplification")
    report, stderr, low = run(tmp_path, 120)
    assert report["triangles"] == len(low["tris"])
    assert len(reduce.unique_faces(low["tris"])) == len(low["tris"])   # no repeated faces ship
    assert report["collapsed"] - report["duplicates_dropped"] == report["triangles"]
    assert report["triangles"] < 120 * 0.98 and "WARNING" in stderr and "120 requested" in report["warning"]


def test_a_hair_already_under_the_request_is_left_alone_without_a_warning(tmp_path):
    report, stderr, low = run(tmp_path, 1000)
    assert report["triangles"] == 100 and report["duplicates_dropped"] == 100   # only the copies go
    assert "warning" not in report and "WARNING" not in stderr
