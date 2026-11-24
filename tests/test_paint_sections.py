"""Painting a large model again in sections and laying them over its first paint.

The painter sees a whole model in 768 pixels whatever its size, so a large model
is cut into sections, each painted on its own with the reference cropped to
match. Everything in that chain that does not need a GPU is exercised here: how
a model is cut, that every face's weights sum to one, which way a model faces
in its picture, where each section's crop falls, that the first paint's tone
survives while a section's detail comes through, and that a small model is
passed through untouched.
"""

from __future__ import annotations

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

from paint_sections import (  # noqa: E402
    GENERATOR_FRAME,
    composite,
    crop_box,
    figure_box,
    harmonize,
    masked_blur,
    main,
    match_orientation,
    mesh_silhouette,
    reusable_paint,
    orientations,
    plan_sections,
    project,
    section_counts,
    texel_density,
)
from reference_asset_compiler.stages import StageError, prepare_paint_sections  # noqa: E402
from test_head_detail import glb_with_mesh, solid_png  # noqa: E402
from test_texture_stage import paint_stack  # noqa: E402


def strip(length=2.4, width=0.3, columns=48):
    """A flat strip along +X in the picture plane, with its UVs laid out along u."""
    positions, uvs, triangles = [], [], []
    for column in range(columns + 1):
        x = length * column / columns
        positions += [[x, 0.0, 0.0], [x, width, 0.0]]
        u = 0.05 + 0.9 * column / columns
        uvs += [[u, 0.6], [u, 0.4]]
    for column in range(columns):
        a, b, c, d = 2 * column, 2 * column + 1, 2 * column + 2, 2 * column + 3
        triangles += [[a, c, d], [a, d, b]]
    return (np.array(positions, dtype=np.float32), np.array(uvs, dtype=np.float32),
            np.array(triangles, dtype=np.int64))


def ell(step=0.1):
    """An L in the picture plane: a long arm along +X and a short one up +Y. No symmetry.

    Tiled in squares `step` across, so a section holds a realistic number of faces.
    """
    positions, triangles = [], []

    def quad(x0, y0, x1, y1):
        start = len(positions)
        positions.extend([[x0, y0, 0.0], [x1, y0, 0.0], [x1, y1, 0.0], [x0, y1, 0.0]])
        triangles.extend([[start, start + 1, start + 2], [start, start + 2, start + 3]])

    def tiles(x0, y0, x1, y1):
        for x in np.arange(x0, x1 - 1e-9, step):
            for y in np.arange(y0, y1 - 1e-9, step):
                quad(x, y, x + step, y + step)

    tiles(0.0, 0.0, 2.0, 0.4)
    tiles(0.0, 0.4, 0.4, 1.2)
    return np.array(positions, dtype=np.float32), np.array(triangles, dtype=np.int64)


def picture_of(positions, triangles, frame, canvas=(900, 600), size=400):
    """A figure's alpha: the model seen in `frame`, set in a larger picture."""
    outline = mesh_silhouette(project(positions, frame), triangles, size)
    alpha = np.zeros((canvas[1], canvas[0]), dtype=np.uint8)
    top, left = (canvas[1] - size) // 2, (canvas[0] - size) // 2
    alpha[top:top + size, left:left + size] = outline * 255
    return alpha


class CuttingTests(unittest.TestCase):
    def test_a_long_model_is_cut_along_its_length_only(self):
        positions, _, triangles = strip()
        plan = plan_sections(positions, triangles, 0.6, 0.25, 0.1, 12, min_faces=1)
        self.assertEqual(plan["counts"], [4, 1, 1])
        self.assertEqual(len(plan["cells"]), 4)

    def test_every_faces_weights_sum_to_one(self):
        positions, _, triangles = strip()
        plan = plan_sections(positions, triangles, 0.6, 0.25, 0.1, 12, min_faces=1)
        total = sum(cell["weights"] for cell in plan["cells"])
        np.testing.assert_allclose(total, 1.0, atol=1e-6)

    def test_a_cell_paints_every_face_it_weighs_and_a_little_more(self):
        positions, _, triangles = strip()
        plan = plan_sections(positions, triangles, 0.6, 0.25, 0.1, 12, min_faces=1)
        for cell in plan["cells"]:
            weighed = cell["weights"] > 0
            self.assertTrue(np.all(cell["faces"][weighed]))
            self.assertGreater(cell["faces"].sum(), weighed.sum())
        # the faces in the middle of the first section are its alone
        first = plan["cells"][0]
        centre = positions[triangles].mean(axis=1)[:, 0]
        np.testing.assert_allclose(first["weights"][centre < 0.4], 1.0)

    def test_too_many_sections_grow_until_they_fit_the_cap(self):
        counts, size = section_counts(np.array([3.0, 3.0, 3.0]), 0.6, 12)
        self.assertLessEqual(int(np.prod(counts)), 12)
        self.assertGreater(size, 0.6)

    def test_a_corner_the_model_barely_reaches_is_not_painted(self):
        positions, triangles = ell()
        plan = plan_sections(positions, triangles, 0.6, 0.25, 0.1, 12, min_faces=1)
        # the top right of the L's box holds no face at all
        self.assertTrue(plan["skipped"])
        self.assertLess(len(plan["cells"]), int(np.prod(plan["counts"])))

    def test_faces_of_a_cell_too_small_to_paint_go_to_their_nearest_neighbour(self):
        positions, triangles = ell()
        # with a high floor the cells the L only clips are folded into their neighbours
        plan = plan_sections(positions, triangles, 0.5, 0.25, 0.1, 12, min_faces=12)
        self.assertTrue(plan["skipped"])
        total = sum(cell["weights"] for cell in plan["cells"])
        np.testing.assert_allclose(total, 1.0, atol=1e-6)
        painted = np.zeros(len(triangles), dtype=bool)
        for cell in plan["cells"]:
            painted |= cell["faces"]
        self.assertTrue(painted.all())


class OrientationTests(unittest.TestCase):
    def test_there_are_twenty_four_frames_and_the_generators_is_first(self):
        frames = orientations()
        self.assertEqual(len(frames), 24)
        self.assertEqual(len(set(frames)), 24)
        self.assertEqual(frames[0], GENERATOR_FRAME)

    def test_a_model_left_as_generated_keeps_the_generators_frame(self):
        positions, triangles = ell()
        frame, scores = match_orientation(positions, triangles, picture_of(positions, triangles, GENERATOR_FRAME))
        self.assertEqual(frame, GENERATOR_FRAME)
        self.assertGreater(scores[frame], 0.9)

    def test_a_turned_model_is_found_facing_the_way_it_was_turned(self):
        positions, triangles = ell()
        turned = (1, 1, 0, -1)                  # +Y runs right in the picture, -X runs up
        frame, scores = match_orientation(positions, triangles, picture_of(positions, triangles, turned))
        self.assertEqual(frame, turned)
        self.assertGreater(scores[turned], scores[GENERATOR_FRAME] + 0.2)


class CropTests(unittest.TestCase):
    def test_each_sections_crop_falls_where_it_is_in_the_picture(self):
        positions, _, triangles = strip()
        alpha = picture_of(positions, triangles, GENERATOR_FRAME)
        figure = figure_box(alpha)
        points = project(positions, GENERATOR_FRAME)
        low, high = points.min(axis=0), points.max(axis=0)
        plan = plan_sections(positions, triangles, 0.6, 0.25, 0.1, 12, min_faces=1)
        centres = []
        for cell in plan["cells"]:
            used = np.unique(triangles[cell["faces"]])
            left, top, right, bottom = crop_box(points[used], figure, low, high, 0.1)
            self.assertEqual(right - left, bottom - top)
            centres.append((left + right) / 2.0)
        self.assertEqual(centres, sorted(centres))
        self.assertGreater(centres[0], figure[0])
        self.assertLess(centres[-1], figure[2])

    def test_a_crop_is_never_smaller_than_a_fifth_of_the_figure(self):
        figure = (100, 100, 600, 300)                       # 500 wide
        tip = np.array([[0.99, 0.5], [1.0, 0.51]])          # a sliver at the far end
        left, top, right, bottom = crop_box(tip, figure, np.array([0.0, 0.0]), np.array([1.0, 1.0]), 0.1)
        self.assertGreaterEqual(right - left, 100)

    def test_each_axis_is_fitted_to_the_figure_on_its_own(self):
        # a model twice as wide as tall, in a figure as tall as it is wide: the
        # model's bottom still lands on the figure's bottom
        figure = (0, 0, 400, 400)
        bottom = np.array([[0.4, 0.0], [0.6, 0.05]])
        _, top, _, low_edge = crop_box(bottom, figure, np.array([0.0, 0.0]), np.array([2.0, 1.0]), 0.0)
        self.assertGreater((top + low_edge) / 2.0, 340)


class CompositeTests(unittest.TestCase):
    def setUp(self):
        size = 64
        ramp = np.linspace(40, 200, size, dtype=np.float32)
        self.base = np.repeat(np.repeat(ramp[None, :, None], size, axis=0), 3, axis=2)
        checker = ((np.indices((size, size)).sum(axis=0) % 2) * 2 - 1).astype(np.float32) * 20
        # a section painted 40 levels warmer than the first paint, with fine detail in it
        self.section = self.base + 40.0 + checker[..., None]
        self.weights = np.zeros((size, size), dtype=np.float32)
        self.weights[:, :32] = 1.0
        self.mask = self.weights > 0

    def test_the_first_paints_tone_survives_and_the_sections_detail_comes_through(self):
        out = composite(self.base, [(self.section, self.weights, self.mask)], sigma=3.0)
        inside = (out - self.base)[8:56, 4:28]
        self.assertLess(abs(float(inside.mean())), 3.0)          # not 40 warmer
        self.assertGreater(float(inside.std()), 15.0)            # the checker is there

    def test_without_keeping_tone_the_section_is_laid_as_it_is(self):
        out = composite(self.base, [(self.section, self.weights, self.mask)], sigma=0.0)
        np.testing.assert_allclose(out[:, :32], self.section[:, :32], atol=1e-3)

    def test_the_padding_outside_every_island_is_refilled_from_the_nearest_painted_texel(self):
        # what a mip level reads at an island's edge must be the section's colour, not the first paint's
        out = composite(self.base, [(self.section, self.weights, self.mask)], sigma=0.0)
        np.testing.assert_allclose(out[:, 32:], np.repeat(self.section[:, 31:32], 32, axis=1), atol=1e-3)

    def test_where_two_sections_both_reach_they_share(self):
        other = self.base - 30.0
        both = np.ones_like(self.weights)
        out = composite(self.base, [(self.section, both, both > 0), (other, both, both > 0)], sigma=0.0)
        np.testing.assert_allclose(out, (self.section + other) / 2.0, atol=1e-3)

    def test_neighbours_painted_a_shade_apart_are_matched_where_they_overlap(self):
        size = 64
        left = np.zeros((size, size), dtype=np.float32)
        left[:, :36] = 1.0
        right = np.zeros((size, size), dtype=np.float32)
        right[:, 28:] = 1.0
        # weights fall across the shared columns and sum to one
        ramp = np.clip((np.arange(size) - 28) / 8.0, 0, 1).astype(np.float32)
        weights_left, weights_right = left * (1 - ramp), right * ramp
        warm = np.clip(self.base * 1.25, 0, 255)
        sections = [(self.base, weights_left, left > 0), (warm, weights_right, right > 0)]
        gains, pairs = harmonize(sections)
        self.assertEqual(len(pairs), 1)
        self.assertAlmostEqual(float(np.prod(gains[:, 0])), 1.0, places=3)   # the sections' own colour overall
        self.assertAlmostEqual(float(gains[1, 0] / gains[0, 0]), 0.8, places=2)
        out = composite(self.base, sections, sigma=0.0, gains=gains)
        unmatched = composite(self.base, sections, sigma=0.0)

        def steepest(image):
            return float(np.abs(np.diff(image[:, 24:40, 0], axis=1)).mean(axis=0).max())

        self.assertGreater(steepest(unmatched), steepest(out) + 2.0)


class KeepTheDesignTests(unittest.TestCase):
    """A section's painter sees too little to know iron from wood; the first paint's colour stays."""

    def test_the_first_paints_colour_survives_and_the_sections_light_and_dark_come_through(self):
        size = 64
        base = np.zeros((size, size, 3), np.float32)
        base[...] = (190.0, 40.0, 35.0)                      # a red fin, as the first paint has it
        checker = ((np.indices((size, size)).sum(axis=0) % 2) * 2 - 1).astype(np.float32) * 25
        section = np.zeros_like(base)
        section[...] = (130.0, 95.0, 60.0)                   # the section painted it as wood,
        section += checker[..., None]                        # with grain in it
        section[..., 2] += checker * 1.5                     # and the grain has its own colour
        weights = np.ones((size, size), np.float32)
        inner = composite(base, [(section, weights, weights > 0)], sigma=3.0, mode="light")[8:56, 8:56]
        hue_ratio = inner[..., 0].mean() / max(inner[..., 1].mean(), 1e-3)
        self.assertGreater(hue_ratio, 3.5)                    # still red, not wood
        self.assertGreater(float((inner @ np.array([0.2126, 0.7152, 0.0722])).std()), 4.0)  # the detail is there
        chroma = inner / np.maximum(inner.sum(axis=2, keepdims=True), 1e-3)
        self.assertLess(float(chroma[..., 2].std()), 0.01)    # none of the section's colour came with it
        # The colour mode, by contrast, lets the grain's own colour through.
        other = composite(base, [(section, weights, weights > 0)], sigma=3.0, mode="colour")[8:56, 8:56]
        other_chroma = other / np.maximum(other.sum(axis=2, keepdims=True), 1e-3)
        self.assertGreater(float(other_chroma[..., 2].std()), 0.05)

    def test_the_fast_blur_agrees_with_a_full_one(self):
        from scipy.ndimage import gaussian_filter  # noqa: PLC0415
        rng = np.random.default_rng(1)
        image = gaussian_filter(rng.random((256, 256, 3)).astype(np.float32), (4, 4, 0)) * 255
        mask = np.ones((256, 256), bool)
        fast = masked_blur(image, mask, 24.0)
        full = np.stack([gaussian_filter(image[..., c], 24.0) for c in range(3)], axis=2)
        self.assertLess(float(np.abs(fast - full)[32:-32, 32:-32].mean()), 0.5)


class DensityTests(unittest.TestCase):
    def test_a_metre_square_on_half_a_1024_sheet_is_512_texels_a_metre(self):
        positions = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float32)
        uvs = np.array([[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]], dtype=np.float32)
        triangles = np.array([[0, 1, 2], [0, 2, 3]])
        self.assertAlmostEqual(texel_density(positions, uvs, triangles, 1024), 512.0, places=3)


class RunTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def write_model(self, positions, uvs, triangles):
        source = self.root / "painted.glb"
        source.write_bytes(glb_with_mesh(positions, uvs, triangles, [solid_png(64, (120, 90, 60))]))
        return source

    def test_a_small_model_is_passed_through_byte_for_byte(self):
        positions, uvs, triangles = strip(length=0.5, columns=8)
        source = self.write_model(positions, uvs, triangles)
        reference = self.root / "reference.png"
        reference.write_bytes(solid_png(32, (200, 200, 200)))
        output, report = self.root / "out.glb", self.root / "out.json"
        self.assertEqual(main(["--", str(source), str(output), str(report), "--reference", str(reference)]), 0)
        self.assertEqual(output.read_bytes(), source.read_bytes())
        receipt = json.loads(report.read_text(encoding="utf-8"))
        self.assertFalse(receipt["painted"])
        self.assertEqual(receipt["reason"], "shorter_than_min_length")
        self.assertGreater(receipt["whole_model_mm_per_pixel"], 0)
        self.assertEqual(receipt["output_sha256"], receipt["source_sha256"])

    def test_a_plan_names_its_sections_and_crops_without_painting(self):
        positions, uvs, triangles = strip()
        source = self.write_model(positions, uvs, triangles)
        alpha = picture_of(positions, triangles, GENERATOR_FRAME)
        picture = np.zeros(alpha.shape + (4,), dtype=np.uint8)
        picture[..., :3] = 150
        picture[..., 3] = alpha
        reference = self.root / "reference.png"
        Image.fromarray(picture, "RGBA").save(reference)
        output, report = self.root / "out.glb", self.root / "out.json"
        code = main(["--", str(source), str(output), str(report), "--reference", str(reference),
                     "--plan-only"])
        self.assertEqual(code, 0)
        self.assertFalse(output.exists())
        receipt = json.loads(report.read_text(encoding="utf-8"))
        self.assertFalse(receipt["painted"])
        self.assertEqual(receipt["plan"]["grid"], [4, 1, 1])
        self.assertEqual(len(receipt["plan"]["sections"]), 4)
        self.assertEqual(receipt["orientation"]["chosen"], "+X right, +Y up")
        self.assertEqual(receipt["reason"], "plan_only")
        self.assertEqual(receipt["settings"]["keep_colour_m"], 0.03)
        whole = receipt["plan"]["whole_model_mm_per_pixel"]
        for section in receipt["plan"]["sections"]:
            self.assertLess(section["painted_mm_per_pixel"], whole)
            crop = Image.open(Path(section["folder"]) / "reference.png")
            self.assertEqual(crop.mode, "RGBA")
            self.assertTrue((Path(section["folder"]) / "section.obj").is_file())

    def test_a_model_with_two_materials_is_refused(self):
        positions, uvs, triangles = strip()
        source = self.write_model(positions, uvs, triangles)
        from compress_textures import read_glb, write_glb  # noqa: PLC0415
        document, binary = read_glb(source.read_bytes())
        document["materials"].append({"name": "second"})
        source.write_bytes(write_glb(document, binary))
        reference = self.root / "reference.png"
        reference.write_bytes(solid_png(32, (200, 200, 200)))
        code = main(["--", str(source), str(self.root / "o.glb"), str(self.root / "o.json"),
                     "--reference", str(reference)])
        self.assertEqual(code, 1)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.legacy = paint_stack(self.root / "studio")
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"png")

    def test_the_section_pass_is_handed_the_picture_the_stack_and_its_settings(self):
        prepared = prepare_paint_sections({"reference": self.reference, "views": 12, "atlas": 4096,
                                           "section": 0.5, "keep_tone": 0.03, "max_sections": 8},
                                          self.legacy)
        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("--reference") + 1], str(self.reference.resolve()))
        self.assertEqual(arguments[arguments.index("--legacy-root") + 1], str(self.legacy))
        self.assertEqual(arguments[arguments.index("--section") + 1], "0.5")
        self.assertEqual(arguments[arguments.index("--keep-tone") + 1], "0.03")
        self.assertEqual(arguments[arguments.index("--max-sections") + 1], "8")
        self.assertNotIn("--overlap", arguments)

    def test_the_playbooks_finer_settings_reach_the_section_pass(self):
        # The playbook's finer cut names --context; run-stage once refused it.
        from reference_asset_compiler import cli  # noqa: PLC0415
        args = cli.build_parser().parse_args([
            "run-stage", "paint-sections", "--source", "painted.glb", "--output", "s.glb",
            "--report", "s.json", "--reference", str(self.reference), "--section", "0.45",
            "--overlap", "0.2", "--context", "0.05", "--max-sections", "48"])
        self.assertEqual(args.context, 0.05)
        prepared = prepare_paint_sections({"reference": self.reference, "section": 0.45,
                                           "overlap": 0.2, "context": 0.05, "max_sections": 48},
                                          self.legacy)
        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("--context") + 1], "0.05")
        self.assertEqual(arguments[arguments.index("--overlap") + 1], "0.2")

    def test_the_listing_says_how_long_a_section_takes(self):
        from reference_asset_compiler.stages import describe_stages  # noqa: PLC0415
        listing = describe_stages(ROOT, None, self.legacy)
        entry = next(stage for stage in listing["stages"] if stage["stage"] == "paint-sections")
        self.assertEqual(entry["estimate"]["unit"], "section")
        self.assertGreater(entry["estimate"]["minutes"], 0)

    def test_without_a_reference_it_refuses(self):
        with self.assertRaises(StageError):
            prepare_paint_sections({}, self.legacy)

    def test_without_the_paint_stack_it_says_what_is_missing(self):
        shutil.rmtree(self.legacy / "upstream" / "Hunyuan3D-2.1")
        with self.assertRaises(StageError):
            prepare_paint_sections({"reference": self.reference}, self.legacy)


if __name__ == "__main__":
    unittest.main()


class ReuseTests(unittest.TestCase):
    """A stopped pass picks up where it stopped, and never takes the wrong section."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.args = type("Args", (), {"views": 12, "resolution": 768, "atlas": 4096})()
        self.folder = self.root / "new" / "section-03"
        self.folder.mkdir(parents=True)
        (self.folder / "section.obj").write_text("v 0 0 0", encoding="utf-8")
        (self.folder / "reference.png").write_bytes(solid_png(16, (90, 60, 30)))
        self.earlier = self.root / "earlier"
        self.paint = self.earlier / "section-03" / "paint"
        self.paint.mkdir(parents=True)
        (self.paint / "section.glb").write_bytes(b"glTF")
        self.gate({"faces_equal": True, "geometry_delta": 0.0, "uv_delta": 0.0})
        # As the launcher writes it: PowerShell's upper-case hashes, and a
        # failed status from the painter's known teardown fault.
        self.record(views=12)

    def gate(self, gate):
        (self.paint / "section.validation.json").write_text(json.dumps(gate), encoding="utf-8")

    def record(self, views, mesh=None, crop=None):
        import hashlib  # noqa: PLC0415
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest().upper()  # noqa: E731
        (self.paint / "section.execution.json").write_text(json.dumps({
            "status": "failed", "exit_code": -1073741819,
            "input_mesh_sha256": mesh or digest(self.folder / "section.obj"),
            "reference_sha256": crop or digest(self.folder / "reference.png"),
            "views": views, "resolution": 768, "atlas": 4096}), encoding="utf-8")

    def test_the_same_section_painted_before_is_reused(self):
        self.assertEqual(reusable_paint(self.earlier, self.folder, self.args), self.paint)

    def test_without_an_earlier_attempt_nothing_is_reused(self):
        self.assertIsNone(reusable_paint(None, self.folder, self.args))
        self.assertIsNone(reusable_paint(self.root / "nowhere", self.folder, self.args))

    def test_a_different_crop_is_painted_again(self):
        self.record(views=12, crop="0" * 64)
        self.assertIsNone(reusable_paint(self.earlier, self.folder, self.args))

    def test_a_different_mesh_is_painted_again(self):
        self.record(views=12, mesh="0" * 64)
        self.assertIsNone(reusable_paint(self.earlier, self.folder, self.args))

    def test_other_painter_settings_are_painted_again(self):
        self.record(views=8)
        self.assertIsNone(reusable_paint(self.earlier, self.folder, self.args))

    def test_a_section_the_painter_moved_is_painted_again(self):
        self.gate({"faces_equal": True, "geometry_delta": 0.01, "uv_delta": 0.0})
        self.assertIsNone(reusable_paint(self.earlier, self.folder, self.args))


class StageTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.legacy = paint_stack(self.root / "studio")
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(solid_png(16, (200, 200, 200)))
        self.source = self.root / "painted.glb"
        self.source.write_bytes(b"glTF")

    def waited(self, stage, **options):
        from reference_asset_compiler import stages  # noqa: PLC0415
        seen = {}

        class Stop(Exception):
            pass

        def record(command, **keywords):
            seen.update(keywords)
            raise Stop()

        original = stages.subprocess.run
        stages.subprocess.run = record
        try:
            with self.assertRaises(Stop):
                stages.run_stage(stage, self.source, self.root / "out.glb", self.root / "out.json",
                                 repo_root=ROOT, legacy_root=self.legacy, blender=sys.executable,
                                 options=options)
        finally:
            stages.subprocess.run = original
        return seen["timeout"]

    def test_painting_in_sections_gets_four_hours_unless_told_otherwise(self):
        # The skiff's 32 sections were stopped at the twentieth by the hour
        # every stage used to get.
        self.assertEqual(self.waited("paint-sections", reference=self.reference), 14400)

    def test_other_stages_keep_their_hour(self):
        self.assertEqual(self.waited("compress-textures"), 3600)

    def test_the_listing_says_how_long_each_stage_is_given(self):
        from reference_asset_compiler.stages import describe_stages  # noqa: PLC0415
        listing = {entry["stage"]: entry for entry in describe_stages(ROOT, None, self.legacy)["stages"]}
        self.assertEqual(listing["paint-sections"]["timeout_seconds"], 14400)
        self.assertEqual(listing["compress-textures"]["timeout_seconds"], 3600)

    def test_the_command_line_leaves_the_timeout_to_the_stage(self):
        from reference_asset_compiler import cli  # noqa: PLC0415
        args = cli.build_parser().parse_args(["run-stage", "paint-sections"])
        self.assertIsNone(args.timeout)

    def test_an_earlier_attempt_reaches_the_section_pass_and_a_missing_one_is_refused(self):
        earlier = self.root / "sections-attempt001"
        earlier.mkdir()
        prepared = prepare_paint_sections({"reference": self.reference, "reuse_sections": earlier},
                                          self.legacy)
        arguments = prepared["arguments"]
        self.assertEqual(arguments[arguments.index("--reuse-sections") + 1], str(earlier.resolve()))
        with self.assertRaises(StageError):
            prepare_paint_sections({"reference": self.reference, "reuse_sections": self.root / "none"},
                                   self.legacy)
