"""Re-encoding a model's textures without disturbing anything else about it.

A finished asset is mostly texture: one real library was 133.7 MB across 22
models and almost every byte of it uncompressed PNG. The mesh was never the
problem.

Two things have to hold, and both are the kind that would otherwise be noticed
much later by somebody else. A colour map and a data map are different
questions, because one is looked at and the other is read as numbers by a
shader. And an asset that went in rigged has to come out rigged, which is why
the file is rewritten chunk by chunk rather than opened in a mesh library.

Nothing here needs Blender or a GPU.
"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compress_textures import (  # noqa: E402
    carries_alpha,
    data_images,
    main,
    read_glb,
    write_glb,
)

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def noisy_png(size=512, alpha=False, seed=7):
    """A picture with real detail in it, so re-encoding has something to lose."""
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (size, size, 3), dtype=np.uint8)
    # Some structure as well as noise, or a codec has nothing to hold on to.
    base[size // 4: size // 2] = 200
    if alpha:
        channel = np.full((size, size, 1), 255, dtype=np.uint8)
        channel[: size // 3] = 0
        base = np.concatenate([base, channel], axis=2)
    buffer = io.BytesIO()
    Image.fromarray(base, "RGBA" if alpha else "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def noisy_jpeg(size=256, seed=11):
    """A picture that has already been through a lossy codec once."""
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 255, (size, size, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(base, "RGB").save(buffer, format="JPEG", quality=70)
    return buffer.getvalue()


def flat_png(size=512):
    """A picture a codec can reproduce almost exactly, so its loss is small."""
    base = np.full((size, size, 3), 130, dtype=np.uint8)
    base[: size // 2] = 90
    buffer = io.BytesIO()
    Image.fromarray(base, "RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def build_glb(images, *, rigged=False):
    """A minimal but honest GLB: real image bytes, an accessor, optionally a skin."""
    binary = bytearray()
    views = []
    # One accessor's worth of positions, so there is non-image data to preserve.
    positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32).tobytes()
    views.append({"buffer": 0, "byteOffset": 0, "byteLength": len(positions)})
    binary.extend(positions)

    for payload in images:
        while len(binary) % 4:
            binary.append(0)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(payload)})
        binary.extend(payload)

    # Geometry on both sides of the images, as a real file has it. A test where
    # every accessor sits before the first image proves nothing: those views
    # keep offset 0 whatever happens to the images after them.
    indices = np.array([0, 1, 2], dtype=np.uint16).tobytes()
    while len(binary) % 4:
        binary.append(0)
    views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(indices)})
    binary.extend(indices)
    indices_view = len(views) - 1

    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1,
                                    "material": 0}]}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": indices_view, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "bufferViews": views,
        "buffers": [{"byteLength": len(binary)}],
        "images": [{"bufferView": index + 1, "mimeType": "image/png", "name": f"image{index}"}
                   for index in range(len(images))],
        "textures": [{"source": index} for index in range(len(images))],
        "materials": [{
            "name": "surface",
            "pbrMetallicRoughness": {
                "baseColorTexture": {"index": 0},
                **({"metallicRoughnessTexture": {"index": 1}} if len(images) > 1 else {}),
            },
        }],
    }
    if rigged:
        document["nodes"].append({"name": "bone"})
        document["skins"] = [{"joints": [1]}]
        document["nodes"][0]["skin"] = 0
    return write_glb(document, bytes(binary))


class ShapeTests(unittest.TestCase):
    def test_a_file_survives_a_round_trip_unchanged(self):
        original = build_glb([noisy_png()])
        document, binary = read_glb(original)
        rebuilt = write_glb(document, binary)

        again, _ = read_glb(rebuilt)
        self.assertEqual(document["accessors"], again["accessors"])
        self.assertEqual(document["meshes"], again["meshes"])

    def test_a_map_a_shader_reads_as_numbers_is_told_apart_from_one_that_is_looked_at(self):
        document, _ = read_glb(build_glb([noisy_png(), noisy_png(seed=9)]))

        # The whole reason the two are encoded differently. Getting this
        # backwards would blur a colour map nobody minded and quantise a
        # roughness map into visible banding.
        self.assertEqual(data_images(document), {1})

    def test_alpha_that_something_relies_on_is_recognised(self):
        self.assertTrue(carries_alpha(Image.open(io.BytesIO(noisy_png(alpha=True)))))
        self.assertFalse(carries_alpha(Image.open(io.BytesIO(noisy_png()))))


class ReEncodeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def run_on(self, data, *extra):
        source = self.root / f"in{len(list(self.root.iterdir()))}.glb"
        source.write_bytes(data)
        output = source.with_name(source.stem + "-out.glb")
        report = source.with_name(source.stem + "-report.json")
        code = main([str(source), str(output), str(report), *extra])
        return code, output, report

    def test_a_model_comes_out_smaller_and_says_what_that_cost(self):
        source_bytes = build_glb([noisy_png(1024), noisy_png(1024, seed=3)])
        code, output, report = self.run_on(source_bytes)

        self.assertEqual(code, 0)
        self.assertLess(output.stat().st_size, len(source_bytes))

        written = json.loads(report.read_text(encoding="utf-8-sig"))
        self.assertEqual(written["file"]["before_bytes"], len(source_bytes))
        self.assertEqual(written["file"]["after_bytes"], output.stat().st_size)
        self.assertGreater(written["file"]["saved_share"], 0)
        # Said out loud, because a stage that quietly changed an asset's
        # appearance would be worse than one that refused to run.
        self.assertTrue(written["geometry_unchanged"])
        self.assertTrue(written["rig_unchanged"])

    def test_the_geometry_can_still_be_read_after_the_images_moved(self):
        source_bytes = build_glb([noisy_png(1024), noisy_png(1024, seed=3)])
        code, output, _ = self.run_on(source_bytes)
        self.assertEqual(code, 0)

        # Not that the accessor's JSON survived -- that it still points at the
        # right bytes. Every image changed size, so every buffer view after the
        # first moved, and an accessor left pointing at an old offset would read
        # texture bytes as vertex positions and report success either way.
        def read_accessor(data, index, dtype):
            document, binary = read_glb(data)
            accessor = document["accessors"][index]
            view = document["bufferViews"][accessor["bufferView"]]
            start = view.get("byteOffset", 0)
            return np.frombuffer(binary[start: start + view["byteLength"]], dtype=dtype)

        after = output.read_bytes()
        np.testing.assert_array_equal(read_accessor(source_bytes, 0, np.float32),
                                      read_accessor(after, 0, np.float32))
        # The indices sit after the images, so their view really moves.
        np.testing.assert_array_equal(read_accessor(source_bytes, 1, np.uint16),
                                      read_accessor(after, 1, np.uint16))

    def test_rigging_survives_because_nothing_is_reopened(self):
        code, output, _ = self.run_on(
            build_glb([noisy_png(1024), noisy_png(1024, seed=3)], rigged=True))
        self.assertEqual(code, 0)

        before, _ = read_glb(build_glb([noisy_png(1024), noisy_png(1024, seed=3)], rigged=True))
        after, _ = read_glb(output.read_bytes())

        # An asset that went in rigged comes out rigged. Round-tripping through
        # a mesh library is exactly how that stops being true.
        self.assertEqual(before["skins"], after["skins"])
        self.assertEqual(before["accessors"], after["accessors"])
        self.assertEqual(before["meshes"], after["meshes"])
        self.assertEqual(len(before["nodes"]), len(after["nodes"]))

    def test_a_cutout_keeps_a_format_that_has_an_alpha_channel(self):
        code, _, report = self.run_on(build_glb([noisy_png(1024, alpha=True)]))
        self.assertEqual(code, 0)

        record = json.loads(report.read_text(encoding="utf-8-sig"))["textures"]["images"][0]
        # JPEG has none. Something relying on a cutout would arrive opaque, so
        # the format gives way rather than the picture.
        self.assertTrue(record["kept_alpha"])
        self.assertEqual(record["now"]["format"], "png")

    def test_a_data_map_drops_further_than_a_colour_map(self):
        # 2048 on the way in, so the colour cap and the data cap are actually
        # different numbers. At 1024 both caps are above the source and the
        # test would pass while proving nothing.
        code, _, report = self.run_on(build_glb([noisy_png(2048), noisy_png(2048, seed=3)]))
        self.assertEqual(code, 0)

        images = json.loads(report.read_text(encoding="utf-8-sig"))["textures"]["images"]
        colour = next(entry for entry in images if entry["reads_as"] == "colour")
        data = next(entry for entry in images if entry["reads_as"] == "data")
        self.assertGreater(colour["now"]["size"][0], data["now"]["size"][0])

    def test_re_encoding_that_would_grow_a_file_is_refused(self):
        # A texture that has already been through a lossy codec at a lower
        # quality has nothing left to give, and writing a bigger file would
        # leave somebody worse off for having run this.
        already = build_glb([noisy_jpeg(256)])
        code, output, _ = self.run_on(already, "--colour-size", "0", "--quality", "95")
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())

    def test_what_was_lost_is_measured_per_image_and_the_worst_is_reported(self):
        # One image a codec reproduces almost exactly and one it struggles
        # with, so the worst and the average are far apart. With two similar
        # images they agree to the decimal and the assertion proves nothing.
        code, _, report = self.run_on(build_glb([flat_png(1024), noisy_png(1024, seed=3)]))
        self.assertEqual(code, 0)

        written = json.loads(report.read_text(encoding="utf-8-sig"))
        images = written["textures"]["images"]
        scores = [entry["psnr_db"] for entry in images]
        self.assertTrue(all(score > 0 for score in scores))
        self.assertGreater(max(scores) - min(scores), 5)

        # The worst, not the average: an average lets one ruined map hide
        # behind five untouched ones.
        self.assertEqual(written["worst_psnr_db"], round(min(scores), 2))
        self.assertNotAlmostEqual(written["worst_psnr_db"], sum(scores) / len(scores), places=1)

    def test_a_model_with_no_textures_says_so_rather_than_writing_a_copy(self):
        document, binary = read_glb(build_glb([noisy_png(256)]))
        document.pop("images")
        code, output, _ = self.run_on(write_glb(document, binary))
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
