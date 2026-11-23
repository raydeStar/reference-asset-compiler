"""A fitted garment should cross material cuts, UV splits and an optional loose island."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_fitted_surface import inspect_mesh
from compress_textures import write_glb
from fit_segmented_surface import fit_surface


def test_uv_split_is_not_a_second_layer_but_a_raised_overlay_is(tmp_path):
    sheet = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0],
                      [-1, -1, 0], [1, 1, 0], [-1, 1, 0]], dtype="<f4")
    box = {"mesh": "coat", "regions": {"seam": [[-.6, -.6, -.1], [.6, .6, .1]]}}
    for copies in [1, 2]:
        data = np.concatenate([sheet + np.array([0, 0, i * .006], dtype="<f4")
                               for i in range(copies)]).astype("<f4")
        doc = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": data.nbytes}],
               "bufferViews": [{"buffer": 0, "byteLength": data.nbytes}],
               "accessors": [{"type": "VEC3", "componentType": 5126, "count": len(data),
                              "bufferView": 0}],
               "meshes": [{"name": "coat", "primitives": [{"attributes": {"POSITION": 0}}]}]}
        glb = tmp_path / f"coat{copies}.glb"
        glb.write_bytes(write_glb(doc, data.tobytes()))
        row = inspect_mesh(glb, box)["seam"]
        assert row["components_entering_box"] == copies
        assert row["boundary_edges"] == 0 and row["needs_inspection"] == (copies == 2)


def test_keep_shared_indices_and_drop_islands_only_by_request():
    p = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [4, 4, 4], [5, 4, 4], [5, 5, 4], [1, 1, 1]], dtype=float)
    faces = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [1, 2, 7]])
    labels = np.array(["leather", "cloth", "cloth", "skin"])
    select = np.isin(labels, ["leather", "cloth"])
    _, all_faces, report = fit_surface(p, faces, select)
    assert len(all_faces) == 3 and report["discarded_island_faces"] == 0
    points, t, report = fit_surface(p, faces, select, largest=True)
    assert len(points) == 4 and len(set(t[0]) & set(t[1])) == 2
    assert report["discarded_island_faces"] == 1
