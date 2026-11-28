"""The surface-map bake, run for real in Blender on a box with one rivet head. Skipped unless RAC_BLENDER is set."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler.polish_glb import write_glb

BLENDER = os.environ.get("RAC_BLENDER")


def box_with_a_head():
    """A 40 cm box, each face on its own UV cell, and a small pyramid standing on one upright face. glTF axes (Y up)."""
    half = .2
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)), ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
             ((0, -1, 0), (1, 0, 0), (0, 0, 1)), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (0, 1, 0), (1, 0, 0))]
    positions, uvs, indices = [], [], []
    for k, (normal, u, v) in enumerate(faces):
        n, u, v = (np.array(a, float) for a in (normal, u, v))
        cell = np.array([k % 3, k // 3], float)
        start = len(positions)
        for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            positions.append(n * half + u * su * half + v * sv * half)
            uvs.append((cell + .05 + .9 * np.array([(su + 1) / 2, (sv + 1) / 2])) / np.array([3.0, 3.0]))
        indices += [start, start + 1, start + 2, start, start + 2, start + 3]
    box_indices = len(indices)
    # the head: a pyramid 24 mm across and 8 mm tall on the +Z face (an upright face once Blender stands the part up)
    # Its five vertices are shared between its four sides, so it is one loose part, as a modelled rivet is.
    start = len(positions)
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        positions.append(np.array([sx * .012, sy * .012, half]))
        uvs.append(np.array([.15 + .05 * sx, .8 + .05 * sy]))
    positions.append(np.array([0, 0, half + .008]))
    uvs.append(np.array([.15, .8]))
    for i in range(4):
        indices += [start + i, start + (i + 1) % 4, start + 4]
    positions = np.array(positions, "<f4")
    uvs = np.array(uvs, "<f4")
    indices = np.array(indices, "<u2")
    blob = positions.tobytes() + uvs.tobytes() + indices.tobytes()
    blob += b"\0" * (-len(blob) % 4)
    views = [{"buffer": 0, "byteOffset": 0, "byteLength": positions.nbytes},
             {"buffer": 0, "byteOffset": positions.nbytes, "byteLength": uvs.nbytes},
             {"buffer": 0, "byteOffset": positions.nbytes + uvs.nbytes, "byteLength": box_indices * 2},
             {"buffer": 0, "byteOffset": positions.nbytes + uvs.nbytes + box_indices * 2, "byteLength": (len(indices) - box_indices) * 2}]
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0, "name": "box"}],
           "materials": [{"name": "panel"}, {"name": "head"}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0},
                                      {"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 3, "material": 1}]}],
           "buffers": [{"byteLength": len(blob)}], "bufferViews": views,
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3",
                          "min": positions.min(0).tolist(), "max": positions.max(0).tolist()},
                         {"bufferView": 1, "componentType": 5126, "count": len(uvs), "type": "VEC2"},
                         {"bufferView": 2, "componentType": 5123, "count": box_indices, "type": "SCALAR"},
                         {"bufferView": 3, "componentType": 5123, "count": len(indices) - box_indices, "type": "SCALAR"}]}
    return write_glb(doc, blob)


@unittest.skipUnless(BLENDER, "Set RAC_BLENDER to run the bake in Blender")
class BakeSurfaceMaps(unittest.TestCase):
    def test_a_box_tells_where_its_surface_is_and_what_stands_on_it(self):
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            source = box_with_a_head()
            (folder / "box.glb").write_bytes(source)
            recipe = {"schema": "rac.surface-maps-recipe.v1", "source_sha256": hashlib.sha256(source).hexdigest(), "resolution": 96, "samples": .25}
            (folder / "recipe.json").write_text(json.dumps(recipe), encoding="utf-8")
            command = [BLENDER, "--background", "--factory-startup", "--python-exit-code", "1", "--python",
                       str(ROOT / "scripts" / "blender" / "bake_surface_maps.py"), "--",
                       str(folder / "box.glb"), str(folder / "maps.npz"), str(folder / "maps.json"), "--textures", str(folder / "recipe.json")]
            done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(done.returncode, 0, (done.stdout + done.stderr)[-1500:])
            receipt = json.loads((folder / "maps.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["schema"], "rac.surface-maps.v1")
            self.assertEqual(receipt["class_source"], "material slots")
            self.assertEqual(receipt["class_names"], ["panel", "head"])
            self.assertEqual(receipt["output_sha256"], hashlib.sha256((folder / "maps.npz").read_bytes()).hexdigest())
            self.assertEqual(receipt["annotations"], [])
            with np.load(folder / "maps.npz") as held:
                maps = {key: held[key] for key in held.files}
            valid = maps["valid"]
            self.assertGreater(float(valid.mean()), .3)
            # Blender stands the part up: the box is 40 cm on every side, and the head reaches 8 mm past it toward -Y
            low, high = maps["bounds"]
            np.testing.assert_allclose(high - low, [.4, .408, .4], atol=2e-3)
            self.assertAlmostEqual(float(low[1]), -.208, places=3)
            inside = maps["pos"][valid]
            self.assertTrue(((inside >= low - 2e-3) & (inside <= high + 2e-3)).all())
            lengths = np.linalg.norm(maps["nrm"][valid].astype(np.float32), axis=1)
            self.assertLess(float(np.abs(lengths - 1).max()), .06)
            ambient = maps["ao"][valid].astype(np.float32)
            self.assertGreater(float(np.median(ambient[:, 0])), .9)             # a convex box is open to the sky
            self.assertTrue(((ambient > -.01) & (ambient < 1.01)).all())
            self.assertEqual(sorted(np.unique(maps["cls"][valid]).tolist()), [0, 1])
            self.assertGreater(float((1 - maps["bev"][valid][:, 3].astype(np.float32)).max()), .05)   # the box's edges are found
            heads = maps["fasteners"]
            self.assertEqual(len(heads), 1)
            np.testing.assert_allclose(heads[0][3:6], [0, -1, 0], atol=.02)     # it faces out of the upright face it stands on
            self.assertAlmostEqual(float(heads[0][6]), .017, places=2)


if __name__ == "__main__":
    unittest.main()
