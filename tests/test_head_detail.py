"""Painting a head on its own and laying it over the body's atlas.

A full-body paint gives a face ninety pixels of each view, and nothing after
the diffusion can put back what it never saw. The head pass cuts the head out,
paints it alone with the reference cropped to match, and composites the result
in UV space. Every decision in that chain that does not need a GPU is
exercised here: which faces are head, what the painter is handed, where the
reference is cropped, where the paint lands, and what of the body survives
byte for byte.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from compress_textures import read_glb, write_glb  # noqa: E402
from paint_head_detail import (  # noqa: E402
    blend,
    face_weights,
    grow,
    head_crop_box,
    head_faces,
    mesh_from_glb,
    rasterize_weights,
    swap_images,
    write_obj,
)
from reference_asset_compiler.stages import StageError, prepare_paint_head  # noqa: E402
from test_texture_stage import paint_stack  # noqa: E402


def figure(height=1.8, rows=10):
    """A stack of quads up a column: two triangles per row, rows evenly up +Y."""
    positions, uvs, triangles = [], [], []
    for row in range(rows + 1):
        y = height * row / rows
        positions += [[-0.1, y, 0.0], [0.1, y, 0.0]]
        uvs += [[0.1, 0.9 - 0.8 * row / rows], [0.3, 0.9 - 0.8 * row / rows]]
    for row in range(rows):
        a, b, c, d = 2 * row, 2 * row + 1, 2 * row + 2, 2 * row + 3
        triangles += [[a, b, d], [a, d, c]]
    return (np.array(positions, dtype=np.float32), np.array(uvs, dtype=np.float32),
            np.array(triangles, dtype=np.int64))


def glb_with_mesh(positions, uvs, triangles, images):
    binary = bytearray()
    views = []

    def add(payload):
        while len(binary) % 4:
            binary.append(0)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(payload)})
        binary.extend(payload)
        return len(views) - 1

    position_view = add(positions.astype(np.float32).tobytes())
    uv_view = add(uvs.astype(np.float32).tobytes())
    index_view = add(triangles.astype(np.uint16).reshape(-1).tobytes())
    image_views = [add(payload) for payload in images]
    document = {
        "asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "translation": [0.0, 0.5, 0.0]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2,
                                    "material": 0}]}],
        "accessors": [
            {"bufferView": position_view, "componentType": 5126, "count": len(positions), "type": "VEC3"},
            {"bufferView": uv_view, "componentType": 5126, "count": len(uvs), "type": "VEC2"},
            {"bufferView": index_view, "componentType": 5123, "count": triangles.size, "type": "SCALAR"},
        ],
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
        "images": [{"bufferView": view, "mimeType": "image/png", "name": "image{0}".format(i)}
                   for i, view in enumerate(image_views)],
        "textures": [{"source": i} for i in range(len(images))],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
    }
    return write_glb(document, bytes(binary))


def solid_png(size, colour):
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), colour).save(buffer, format="PNG")
    return buffer.getvalue()


class HeadSelectionTests(unittest.TestCase):
    def test_a_face_is_head_only_when_entirely_above_the_cut(self):
        positions, uvs, triangles = figure(rows=10)
        kept, cut, height = head_faces(positions, triangles, 0.78)
        self.assertAlmostEqual(height, 1.8, places=5)
        self.assertAlmostEqual(cut, 1.8 * 0.78, places=5)
        # Rows start at multiples of 0.18; the first row whose bottom is at or
        # above 1.404 is row 8 (1.44). Two rows of two faces each.
        self.assertEqual(int(kept.sum()), 4)
        self.assertTrue(kept[16:].all())
        self.assertFalse(kept[:16].any())

    def test_the_mesh_is_read_in_world_space(self):
        positions, uvs, triangles = figure()
        glb = glb_with_mesh(positions, uvs, triangles, [solid_png(8, (10, 20, 30))])
        document, binary = read_glb(glb)
        placed, read_uvs, read_triangles = mesh_from_glb(document, binary)
        # The node lifts the mesh half a metre; a head decided in local space
        # would be a head decided on the wrong figure.
        self.assertAlmostEqual(float(placed[:, 1].min()), 0.5, places=5)
        self.assertTrue(np.allclose(read_uvs, uvs))
        self.assertTrue(np.array_equal(read_triangles, triangles))

    def test_weights_rise_from_the_cut_to_a_feather_above_it(self):
        positions, uvs, triangles = figure(rows=10)
        kept, cut, height = head_faces(positions, triangles, 0.78)
        weights = face_weights(positions, triangles, kept, cut, height, 0.05)
        # Row 8 starts 0.036 above the cut, a feather is 0.09: partway up.
        self.assertAlmostEqual(float(weights[16]), 0.036 / 0.09, places=3)
        # Row 9 starts 0.216 above: fully head.
        self.assertEqual(float(weights[18]), 1.0)
        self.assertEqual(float(weights[0]), 0.0)


class TransportTests(unittest.TestCase):
    def test_the_head_obj_carries_only_head_faces_with_the_files_own_uvs(self):
        positions, uvs, triangles = figure(rows=10)
        kept, _, _ = head_faces(positions, triangles, 0.78)
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "head.obj"
            vertices, faces = write_obj(path, positions, uvs, triangles, kept)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(faces, 4)
            self.assertEqual(vertices, 6)
            self.assertEqual(text.count("\nf "), 4)
            self.assertEqual(text.count("\nv "), 6)
            self.assertEqual(text.count("\nvt "), 6)
            # Faces index positions and UVs alike: a GLB already split them.
            self.assertIn("f 1/1 2/2 4/4", text)
            # glTF's v runs down the sheet and OBJ's runs up.
            first_vt = [line for line in text.splitlines() if line.startswith("vt ")][0]
            self.assertAlmostEqual(float(first_vt.split()[2]), 1.0 - uvs[16][1], places=5)
            self.assertTrue(path.with_suffix(".mtl").is_file())


class CropTests(unittest.TestCase):
    def test_the_crop_is_a_square_around_the_top_of_the_silhouette(self):
        alpha = np.zeros((1200, 800), dtype=np.uint8)
        # A figure 1000 rows tall, standing off-centre, with a narrow head.
        alpha[100:1100, 300:500] = 255
        alpha[100:300, 350:450] = 255
        alpha[100:300, 300:350] = 0
        alpha[100:300, 450:500] = 0
        box = head_crop_box(alpha, 0.78, 0.0)
        left, top, right, bottom = box
        self.assertEqual(right - left, bottom - top)
        # The head band is the top 22% of the figure's own rows, not the picture's.
        self.assertLessEqual(top, 100)
        self.assertGreaterEqual(bottom, 100 + 220)
        # And it is centred on the head's columns, not the body's.
        self.assertAlmostEqual((left + right) / 2, 400, delta=2)

    def test_no_silhouette_means_no_crop(self):
        self.assertIsNone(head_crop_box(np.zeros((10, 10), dtype=np.uint8), 0.78, 0.05))


class CompositeTests(unittest.TestCase):
    def test_head_texels_come_from_the_head_and_body_texels_stay_byte_for_byte(self):
        positions, uvs, triangles = figure(rows=10)
        kept, cut, height = head_faces(positions, triangles, 0.78)
        weights = face_weights(positions, triangles, kept, cut, height, 0.0)
        sheet = rasterize_weights(uvs, triangles, weights, 64)
        body = Image.new("RGB", (64, 64), (200, 40, 40))
        head = Image.new("RGB", (64, 64), (40, 40, 200))
        out = np.asarray(blend(body, head, sheet))
        # The head rows sit at the top of the UV column: v from 0.1 to 0.26.
        self.assertTrue((out[8:14, 8:18] == (40, 40, 200)).all())
        # The body below is untouched.
        self.assertTrue((out[40:56, 8:18] == (200, 40, 40)).all())
        # And so is everything off the column.
        self.assertTrue((out[:, 40:] == (200, 40, 40)).all())

    def test_the_mask_grows_so_a_sample_at_an_edge_is_covered(self):
        sheet = np.zeros((16, 16), dtype=np.float32)
        sheet[6:10, 6:10] = 1.0
        grown = grow(sheet, 2)
        self.assertEqual(float(grown[4, 8]), 1.0)
        self.assertEqual(float(grown[3, 8]), 0.0)

    def test_a_head_map_at_another_size_is_brought_to_the_bodys(self):
        body = Image.new("RGB", (16, 16), (0, 0, 0))
        head = Image.new("RGB", (32, 32), (255, 255, 255))
        out = blend(body, head, np.ones((16, 16), dtype=np.float32))
        self.assertEqual(out.size, (16, 16))
        self.assertEqual(out.getpixel((3, 3)), (255, 255, 255))

    def test_swapping_images_leaves_every_other_view_meaning_what_it_meant(self):
        positions, uvs, triangles = figure()
        glb = glb_with_mesh(positions, uvs, triangles, [solid_png(8, (1, 2, 3)), solid_png(8, (4, 5, 6))])
        document, binary = read_glb(glb)
        replacement = solid_png(16, (9, 9, 9))
        document, rebuilt = swap_images(document, binary, {0: replacement})
        again = write_glb(document, rebuilt)
        document, binary = read_glb(again)
        placed, read_uvs, read_triangles = mesh_from_glb(document, binary)
        self.assertTrue(np.array_equal(read_triangles, triangles))
        self.assertTrue(np.allclose(read_uvs, uvs))
        view = document["bufferViews"][document["images"][0]["bufferView"]]
        self.assertEqual(binary[view["byteOffset"]:view["byteOffset"] + view["byteLength"]], replacement)
        other = document["bufferViews"][document["images"][1]["bufferView"]]
        self.assertEqual(binary[other["byteOffset"]:other["byteOffset"] + other["byteLength"]],
                         solid_png(8, (4, 5, 6)))
        self.assertEqual(document["buffers"][0]["byteLength"], len(binary))


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.legacy = paint_stack(self.root / "studio")
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"png")

    def test_the_head_pass_is_handed_the_picture_and_the_stack(self):
        prepared = prepare_paint_head({"reference": self.reference, "views": 12, "atlas": 4096,
                                       "head_from": 0.8, "feather": 0.02}, self.legacy)
        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("--reference") + 1], str(self.reference.resolve()))
        self.assertEqual(arguments[arguments.index("--legacy-root") + 1], str(self.legacy))
        self.assertEqual(arguments[arguments.index("--views") + 1], "12")
        self.assertEqual(arguments[arguments.index("--atlas") + 1], "4096")
        self.assertEqual(arguments[arguments.index("--head-from") + 1], "0.8")
        self.assertEqual(arguments[arguments.index("--feather") + 1], "0.02")

    def test_without_a_reference_it_refuses(self):
        with self.assertRaises(StageError) as refusal:
            prepare_paint_head({}, self.legacy)
        self.assertIn("--reference", str(refusal.exception))

    def test_without_the_paint_stack_it_says_what_is_missing(self):
        shutil.rmtree(self.legacy / "upstream" / "Hunyuan3D-2.1")
        with self.assertRaises(StageError) as refusal:
            prepare_paint_head({"reference": self.reference}, self.legacy)
        self.assertIn("paint-checkout", str(refusal.exception))

    def test_settings_nobody_chose_are_left_to_the_stage(self):
        prepared = prepare_paint_head({"reference": self.reference}, self.legacy)
        for flag in ("--views", "--resolution", "--atlas", "--head-from", "--feather"):
            self.assertNotIn(flag, prepared["arguments"])


if __name__ == "__main__":
    unittest.main()
