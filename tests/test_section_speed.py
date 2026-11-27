"""The section pass, faster and the same: fill near the mesh, one painter run, sums only where sections weigh.

A hero stair took two hours, 114 minutes of it in 33 sections. Each section's
painter filled every empty texel of an 8192 sheet (140 s of its 210 s) and
loaded its models again (25 s), and the composite blurred the whole sheet for
every section and map (25-30 s each). These tests hold the faster paths to the
numbers of the slow ones on the texels that are used.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import paint_sections  # noqa: E402
from paint_sections import (  # noqa: E402
    LUMINANCE, Stitch, composite, masked_blur, masked_blur_at, repad, sparse_layout)

try:
    import cv2  # noqa: F401
    HAVE_CV2 = True
except ImportError:  # pragma: no cover - the tools extra installs it
    HAVE_CV2 = False

HELPER = ROOT / "workflows" / "texture" / "hunyuan3d21" / "sheet_fill.py"
SPEC = importlib.util.spec_from_file_location("sheet_fill", HELPER)
SHEET_FILL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHEET_FILL)


def islands(size, count, rng, largest=None):
    """A sheet with `count` rectangular islands on it, as a mask."""
    largest = largest or size // 6
    mask = np.zeros((size, size), bool)
    for _ in range(count):
        top, left = rng.integers(0, size - largest, 2)
        height, width = rng.integers(4, largest, 2)
        mask[top:top + height, left:left + width] = True
    return mask


@unittest.skipUnless(HAVE_CV2, "needs OpenCV, as the painter's environment has")
class SheetFillTests(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(5)
        size = 512
        self.footprint = islands(size, 20, self.rng)
        self.image = np.zeros((size, size, 3), np.uint8)
        colours = self.rng.integers(40, 220, (size, size, 3))
        self.image[self.footprint] = colours[self.footprint].astype(np.uint8)
        # The views missed a few texels of the mesh and one whole strip.
        self.unseen = (self.rng.random((size, size)) < 0.03) & self.footprint
        rows, columns = np.nonzero(self.footprint)
        self.unseen[rows[0]:rows[0] + 6, columns[0]:columns[0] + 20] |= \
            self.footprint[rows[0]:rows[0] + 6, columns[0]:columns[0] + 20]
        self.mask = ((self.footprint & ~self.unseen) * 255).astype(np.uint8)
        self.painted = self.image * (self.mask[..., None] > 0)

    def test_painted_texels_are_kept_exactly(self):
        filled, _ = SHEET_FILL.inpaint_near(self.painted, self.mask, self.footprint, 8)
        np.testing.assert_array_equal(filled[self.mask == 255], self.painted[self.mask == 255])

    def test_near_the_mesh_it_is_upstreams_fill(self):
        import cv2  # noqa: PLC0415
        whole = cv2.inpaint(self.painted, 255 - self.mask, 3, cv2.INPAINT_NS)
        reach, _, _ = SHEET_FILL.reach_for(self.mask, self.footprint, 32)
        near, count = SHEET_FILL.inpaint_near(self.painted, self.mask, self.footprint, reach)
        read = cv2.dilate(self.footprint.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        np.testing.assert_array_equal(near[read], whole[read])
        self.assertGreater(count, int(self.unseen.sum()))

    def test_unpainted_rims_need_the_wider_reach_and_get_it(self):
        # A 256-pixel view leaves a rim round every island unpainted. Eight
        # texels of reach filled those rims from the band's edge, not the paint:
        # on the stair's first section 41 % of its texels moved, by up to 19/255.
        import cv2  # noqa: PLC0415
        rng = np.random.default_rng(9)
        size = 512
        footprint = np.zeros((size, size), bool)
        image = np.zeros((size, size, 3), np.uint8)
        for _ in range(20):
            top, left = rng.integers(0, size - 90, 2)
            height, width = rng.integers(20, 90, 2)
            footprint[top:top + height, left:left + width] = True
            image[top:top + height, left:left + width] = rng.integers(40, 220, (height, width, 3))
        rim = footprint & ~cv2.erode(footprint.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        mask = ((footprint & ~rim) * 255).astype(np.uint8)
        painted = image * (mask[..., None] > 0)
        whole = cv2.inpaint(painted, 255 - mask, 3, cv2.INPAINT_NS)
        read = cv2.dilate(footprint.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        narrow, _ = SHEET_FILL.inpaint_near(painted, mask, footprint, 8)
        self.assertFalse(np.array_equal(narrow[read], whole[read]))
        reach, deepest, _ = SHEET_FILL.reach_for(mask, footprint, 8)
        self.assertEqual(reach, int(min(max(8, 2 * deepest + 16), 256)))
        wide, _ = SHEET_FILL.inpaint_near(painted, mask, footprint, reach)
        np.testing.assert_array_equal(wide[read], whole[read])

    def test_a_face_no_view_saw_does_not_widen_the_band_and_the_rest_stays_exact(self):
        import cv2  # noqa: PLC0415
        footprint = self.footprint.copy()
        far = np.zeros_like(footprint)
        far[480:500, 480:510] = True                 # an island no view saw, far from the paint
        footprint |= far
        mask = self.mask.copy()
        mask[far] = 0
        painted = self.image * (mask[..., None] > 0)
        reach, deepest, unseen = SHEET_FILL.reach_for(mask, footprint, 32, local=16)
        self.assertLess(reach, 256)
        self.assertGreater(unseen, 0)
        whole = cv2.inpaint(painted, 255 - mask, 3, cv2.INPAINT_NS)
        near, _ = SHEET_FILL.inpaint_near(painted, mask, footprint, reach)
        read = cv2.dilate(footprint.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        gap = cv2.distanceTransform((mask != 255).astype(np.uint8), cv2.DIST_L2, 5)
        close = read & (gap <= 16)
        np.testing.assert_array_equal(near[close], whole[close])

    def test_unseen_texels_are_never_filled_from_the_empty_sheets_black(self):
        near, _ = SHEET_FILL.inpaint_near(self.painted, self.mask, self.footprint, 8)
        self.assertGreater(float(near[self.unseen].mean(axis=1).min()), 20.0)

    def test_the_rest_of_the_sheet_takes_the_nearest_paint(self):
        known = np.zeros((64, 64), bool)
        known[:8, :8] = True
        image = np.zeros((64, 64, 3), np.uint8)
        image[:8, :8] = (200, 100, 50)
        filled = SHEET_FILL.fill_from_coarser(image, known)
        np.testing.assert_array_equal(filled[:8, :8], image[:8, :8])
        np.testing.assert_allclose(filled[60, 60], (200, 100, 50), atol=1)

    def test_one_channel_sheets_are_filled_too(self):
        known = np.zeros((32, 32), bool)
        known[4:8, 4:8] = True
        image = np.where(known, 90, 0).astype(np.uint8)
        filled = SHEET_FILL.fill_from_coarser(image, known)
        self.assertEqual(filled.shape, (32, 32))
        self.assertEqual(int(filled[30, 30]), 90)


class BlurAtTests(unittest.TestCase):
    def check(self, size, sigma, tile=64):
        rng = np.random.default_rng(int(sigma * 10) + size)
        mask = islands(size, 12, rng)
        mask[:3, :5] = True                      # an island against the sheet's corner
        image = rng.integers(0, 255, (size, size, 3)).astype(np.uint8)
        index = np.flatnonzero(mask)
        full = masked_blur(image.astype(np.float32), mask, sigma).reshape(-1, 3)[index]
        at = masked_blur_at(image, mask, sigma, index, tile=tile)
        np.testing.assert_allclose(at, full, atol=2e-3, rtol=1e-5)

    def test_a_full_size_blur_is_the_whole_sheets_at_every_texel_asked_for(self):
        self.check(256, 3.9)

    def test_a_shrunk_blur_is_read_back_as_the_whole_sheet_grows_it(self):
        self.check(256, 19.3)

    def test_a_sheet_the_shrink_does_not_divide(self):
        self.check(250, 9.5)


class SparseCompositeTests(unittest.TestCase):
    """The composite now sums only where a section weighs; these are the whole-sheet sums it replaced."""

    @staticmethod
    def whole_sheet(base, sections, sigma, gains=None, mode="colour"):
        total = np.zeros(base.shape[:2], dtype=np.float32)
        laid = np.zeros_like(base)
        base_tone = None
        if sigma > 0 and mode != "light":
            everywhere = np.zeros(base.shape[:2], dtype=bool)
            for _, _, mask in sections:
                everywhere |= mask
            base_tone = masked_blur(base, everywhere, sigma)
        for number, (paint, weights, mask) in enumerate(sections):
            paint = paint.astype(np.float32)
            if gains is not None:
                paint = paint * np.asarray(gains[number], dtype=np.float32)
            if sigma > 0 and mode == "light":
                own = masked_blur(paint, mask, sigma)
                ratio = np.clip((paint @ LUMINANCE + 4.0) / (own @ LUMINANCE + 4.0), 0.55, 1.6)
                paint = base * ratio[..., None]
            elif sigma > 0:
                paint = base_tone + (paint - masked_blur(paint, mask, sigma))
            laid += paint * weights[..., None]
            total += weights
        share = np.where(total > 0, total, 1.0)
        covered = (total > 0).astype(np.float32)[..., None]
        return repad(base * (1.0 - covered) + laid / share[..., None], total > 0)

    def test_every_mode_gives_the_whole_sheet_numbers(self):
        rng = np.random.default_rng(11)
        size = 200
        base = rng.integers(0, 255, (size, size, 3)).astype(np.float32)
        sections = []
        for _ in range(3):
            mask = islands(size, 6, rng)
            weights = (mask * rng.random((size, size))).astype(np.float32)
            weights[mask & (rng.random((size, size)) < 0.1)] = 0
            sections.append((rng.integers(0, 255, (size, size, 3)).astype(np.uint8), weights, mask))
        gains = rng.uniform(0.8, 1.2, (3, 3))
        for sigma in (0.0, 3.9, 12.0):
            for mode in ("light", "colour"):
                for chosen in (None, gains):
                    with self.subTest(sigma=sigma, mode=mode, gains=chosen is not None):
                        np.testing.assert_allclose(composite(base, sections, sigma, chosen, mode),
                                                   self.whole_sheet(base, sections, sigma, chosen, mode),
                                                   atol=2e-3)


class StitchTests(unittest.TestCase):
    """The composite laid one section at a time, as the section pass lays them while the painter paints."""

    def setUp(self):
        rng = np.random.default_rng(13)
        size = 120
        self.base = rng.integers(0, 255, (size, size, 3)).astype(np.float32)
        self.sections = []
        for _ in range(3):
            mask = islands(size, 5, rng)
            weights = (mask * rng.random((size, size))).astype(np.float32)
            self.sections.append((rng.integers(0, 255, (size, size, 3)).astype(np.uint8), weights, mask))

    def stitch(self, sigma=6.0, mode="colour"):
        return Stitch(self.base, [sparse_layout(weights, mask) for _, weights, mask in self.sections], sigma, mode)

    def test_laid_one_at_a_time_it_is_the_whole_sheet_composite(self):
        for sigma in (0.0, 6.0):
            for mode in ("light", "colour"):
                with self.subTest(sigma=sigma, mode=mode):
                    stitch = self.stitch(sigma, mode)
                    for number, (paint, _, _) in enumerate(self.sections):
                        stitch.lay(number, paint)
                    np.testing.assert_allclose(
                        stitch.result(), SparseCompositeTests.whole_sheet(self.base, self.sections, sigma, None, mode),
                        atol=2e-3)

    def test_sections_are_laid_in_order_and_let_go_once_laid(self):
        stitch = self.stitch()
        with self.assertRaises(ValueError):
            stitch.lay(1, self.sections[1][0])
        stitch.lay(0, self.sections[0][0])
        self.assertIsNone(stitch.layout[0])
        with self.assertRaises(ValueError):
            stitch.result()


class FakePainter:
    """Popen for paint_batch: writes each job's gate as the painter would, or never finishes.

    With `gradual`, it writes one more job's gate each time it is waited on, as a
    painter does over a batch, and every job succeeds.
    """

    calls = []
    hang = False
    gradual = False

    def __init__(self, command, **keywords):
        FakePainter.calls.append(command)
        self.pid = 4321
        self.returncode = None
        self.waiting = []
        jobs = json.loads(Path(command[command.index("-Jobs") + 1]).read_text(encoding="utf-8"))
        if FakePainter.gradual:
            self.waiting = [Path(job["output_obj"]) for job in jobs]
        elif not FakePainter.hang:
            for job in jobs[:-1]:            # the last job fails, as a crashed section would
                output = Path(job["output_obj"])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.with_suffix(".validation.json").write_text("{}", encoding="utf-8")
            failed = Path(jobs[-1]["output_obj"])
            failed.parent.mkdir(parents=True, exist_ok=True)
            failed.with_suffix(".failure.json").write_text(json.dumps({"error": "CUDA out of memory"}),
                                                           encoding="utf-8")
            self.returncode = 1

    def wait(self, timeout=None):
        if self.waiting:
            output = self.waiting.pop(0)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_suffix(".validation.json").write_text("{}", encoding="utf-8")
            if not self.waiting:
                self.returncode = 0
            raise subprocess.TimeoutExpired("painter", timeout)
        if self.returncode is None:
            raise subprocess.TimeoutExpired("painter", timeout)
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class OnePainterRunTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.args = type("Args", (), {"launcher": Path("launch.ps1"), "legacy_root": Path("studio"), "views": 12,
                                      "resolution": 768, "atlas": 8192, "min_free_vram": 0,
                                      "inpaint_reach": 32})()
        self.jobs = [(self.root / "section-{0:02d}".format(n) / "section.obj",
                      self.root / "section-{0:02d}".format(n) / "reference.png",
                      self.root / "section-{0:02d}".format(n) / "paint", 256 + n) for n in range(3)]
        FakePainter.calls, FakePainter.hang, FakePainter.gradual = [], False, False
        self.popen, self.kill_tree = paint_sections.subprocess.Popen, paint_sections.kill_tree
        paint_sections.subprocess.Popen = FakePainter
        self.killed = []
        paint_sections.kill_tree = self.killed.append

    def tearDown(self):
        paint_sections.subprocess.Popen, paint_sections.kill_tree = self.popen, self.kill_tree

    def test_every_section_goes_to_one_painter_run_with_its_own_bake_size(self):
        code = paint_sections.paint_batch(self.args, self.jobs, self.root)
        self.assertEqual(code, 1)
        self.assertEqual(len(FakePainter.calls), 1)
        command = FakePainter.calls[0]
        self.assertEqual(command[command.index("-InpaintReach") + 1], "32")
        self.assertEqual(command[command.index("-Atlas") + 1], "8192")
        self.assertIn("-MapsOnly", command)
        listed = json.loads((self.root / "paint-jobs.json").read_text(encoding="utf-8"))
        self.assertEqual([job["bake_size"] for job in listed], [256, 257, 258])
        self.assertEqual(Path(listed[1]["output_obj"]), self.root / "section-01" / "paint" / "section.obj")

    def test_the_painter_run_is_told_to_skip_the_upscale_only_when_asked(self):
        paint_sections.paint_batch(self.args, self.jobs, self.root)
        self.assertNotIn("-NoUpscale", FakePainter.calls[-1])
        self.args.no_upscale = True
        paint_sections.paint_batch(self.args, self.jobs, self.root)
        self.assertIn("-NoUpscale", FakePainter.calls[-1])

    def test_the_studio_painter_can_skip_the_upscale(self):
        source = (ROOT / "workflows" / "texture" / "hunyuan3d21" / "run_hy3d21_studio.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--no-upscale"', source)
        self.assertIn('painter.models["super_model"] = lambda image: image', source)
        launcher = (ROOT / "scripts" / "run_hy3d21_texture.ps1").read_text(encoding="utf-8")
        self.assertIn("if ($NoUpscale) { $runnerArgs += '--no-upscale' }", launcher)
        self.assertIn("no_upscale = [bool]$NoUpscale", launcher)

    def test_a_section_the_painter_failed_says_why(self):
        paint_sections.paint_batch(self.args, self.jobs, self.root)
        self.assertIn("CUDA out of memory", paint_sections.why_unpainted(self.jobs[2][2], self.root))
        with self.assertRaises(RuntimeError):
            paint_sections.read_paint(self.jobs[2][2])

    def test_the_pass_is_told_as_each_section_is_painted_while_the_painter_runs(self):
        FakePainter.gradual = True
        seen = []

        def on_progress():
            seen.append(sum((paint_dir / "section.validation.json").is_file() for _, _, paint_dir, _ in self.jobs))

        self.assertEqual(paint_sections.paint_batch(self.args, self.jobs, self.root, on_progress=on_progress), 0)
        self.assertEqual(seen, [1, 2, 3])

    def test_a_painter_that_never_finishes_is_stopped_with_everything_it_started(self):
        FakePainter.hang = True
        original = paint_sections.time.monotonic
        clock = iter(range(0, 100000, 1000))
        paint_sections.time.monotonic = lambda: next(clock)
        try:
            with self.assertRaises(subprocess.TimeoutExpired):
                paint_sections.paint_batch(self.args, self.jobs, self.root, minutes_each=0.1)
        finally:
            paint_sections.time.monotonic = original
        self.assertEqual(self.killed, [4321])


class StageOptionTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_texture_stage import paint_stack  # noqa: PLC0415
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.legacy = paint_stack(self.root / "studio")
        self.reference = self.root / "reference.png"
        self.reference.write_bytes(b"png")

    def test_by_default_the_pass_is_left_its_own_reach_and_one_painter_run(self):
        from reference_asset_compiler.stages import prepare_paint_sections  # noqa: PLC0415
        arguments = prepare_paint_sections({"reference": self.reference}, self.legacy)["arguments"]
        self.assertNotIn("--inpaint-reach", arguments)
        self.assertNotIn("--separate-runs", arguments)
        self.assertEqual(paint_sections.parse_arguments(["a.glb", "b.glb", "c.json", "--reference", "r.png"])
                         .inpaint_reach, 32)

    def test_the_whole_sheet_fill_and_a_run_per_section_can_still_be_asked_for(self):
        from reference_asset_compiler import cli  # noqa: PLC0415
        from reference_asset_compiler.stages import prepare_paint_sections  # noqa: PLC0415
        args = cli.build_parser().parse_args([
            "run-stage", "paint-sections", "--source", "painted.glb", "--output", "s.glb", "--report", "s.json",
            "--reference", str(self.reference), "--inpaint-reach", "0", "--separate-runs"])
        self.assertEqual((args.inpaint_reach, args.separate_runs), (0, True))
        arguments = prepare_paint_sections({"reference": self.reference, "inpaint_reach": 0, "separate_runs": True},
                                           self.legacy)["arguments"]
        self.assertEqual(arguments[arguments.index("--inpaint-reach") + 1], "0")
        self.assertIn("--separate-runs", arguments)


class MapsOnlyTests(unittest.TestCase):
    def test_a_section_painted_maps_only_reads_as_its_glb_would(self):
        from PIL import Image  # noqa: PLC0415
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        rng = np.random.default_rng(2)
        colour = rng.integers(0, 255, (16, 16, 3)).astype(np.uint8)
        metallic = rng.integers(0, 255, (16, 16)).astype(np.uint8)
        roughness = rng.integers(0, 255, (16, 16)).astype(np.uint8)
        Image.fromarray(colour, "RGB").save(root / "section.png")
        Image.fromarray(metallic, "L").save(root / "section_metallic.png")
        Image.fromarray(roughness, "L").save(root / "section_roughness.png")
        (root / "section.validation.json").write_text(json.dumps(
            {"faces_equal": True, "geometry_delta": 0.0, "uv_delta": 0.0}), encoding="utf-8")
        glb, _ = paint_sections.read_paint(root)
        self.assertIsNone(glb)
        albedo, mr = paint_sections.section_maps(root, glb)
        np.testing.assert_array_equal(np.asarray(albedo.convert("RGB")), colour)
        packed = np.asarray(mr)
        np.testing.assert_array_equal(packed[..., 0], 255)
        np.testing.assert_array_equal(packed[..., 1], roughness)
        np.testing.assert_array_equal(packed[..., 2], metallic)

    def test_without_its_maps_or_a_glb_a_section_is_not_painted(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        (root / "section.validation.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            paint_sections.read_paint(root)


class BackProjectionTests(unittest.TestCase):
    """An edge-on section must keep the other views without hiding renderer errors."""

    class Array(np.ndarray):
        def to(self, _device):
            return self

    class Render:
        texture_size = (1, 2)
        device = "cpu"

        def __init__(self, errors=None, visible=()):
            self.errors = errors or {}
            self.visible = visible
            self.alpha_requests = []

        def back_project(self, _view, _elevation, azimuth):
            if azimuth in self.errors:
                raise self.errors[azimuth]
            weight = np.zeros((1, 2, 1), dtype=np.float32)
            weight[0, azimuth // 180, 0] = 1.0
            return np.full((1, 2, 3), azimuth / 360 + 0.25, dtype=np.float32), weight, None

        def render_alpha(self, elevation, azimuth, *, resolution):
            self.alpha_requests.append((elevation, azimuth, tuple(resolution)))
            return np.array([azimuth in self.visible])

    empty_error = (
        "max(): Expected reduction dim to be specified for input.numel() == 0. "
        "Specify the reduction dim with the 'dim' argument."
    )

    @classmethod
    def setUpClass(cls):
        # Load this function without importing the workstation's CUDA runner.
        source = ROOT / "workflows" / "texture" / "hunyuan3d21" / "run_hy3d21_studio.py"
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        bake = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "bake_from_multiview_one_view_at_a_time")
        bake.decorator_list = []
        torch = SimpleNamespace(
            zeros=lambda shape: np.zeros(shape, dtype=np.float32).view(cls.Array),
            clamp=lambda value, *, min: np.maximum(value, min),
        )
        namespace = {"torch": torch}
        exec(compile(ast.Module(body=[bake], type_ignores=[]), str(source), "exec"), namespace)
        cls.bake = staticmethod(namespace[bake.name])

    def project(self, render, azimuths):
        processor = SimpleNamespace(render=render, config=SimpleNamespace(bake_exp=2))
        views = [Image.new("RGB", (6, 4)) for _ in azimuths]
        return self.bake(processor, views, [0] * len(views), azimuths, [1.0] * len(views))

    def test_a_confirmed_empty_view_leaves_the_other_views_byte_identical(self):
        baseline = self.Render()
        expected_texture, expected_mask = self.project(baseline, [0, 180])
        with_empty = self.Render({90: RuntimeError(self.empty_error)})
        with contextlib.redirect_stdout(io.StringIO()) as log:
            actual_texture, actual_mask = self.project(with_empty, [90, 0, 180])
        self.assertEqual(expected_texture.tobytes(), actual_texture.tobytes())
        self.assertEqual(expected_mask.tobytes(), actual_mask.tobytes())
        self.assertEqual(baseline.alpha_requests, [])
        self.assertEqual(with_empty.alpha_requests, [(0, 90, (4, 6))])
        self.assertIn("HY3D21_EMPTY_BACK_PROJECTION", log.getvalue())

    def test_refuses_when_all_views_are_empty(self):
        render = self.Render({90: RuntimeError(self.empty_error)})
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "No paint view projected any texels"):
                self.project(render, [90])

    def test_visible_raster_preserves_the_original_error(self):
        error = RuntimeError(self.empty_error)
        render = self.Render(errors={90: error}, visible=(90,))
        with self.assertRaises(RuntimeError) as caught:
            self.project(render, [90])
        self.assertIs(caught.exception, error)
        self.assertEqual(render.alpha_requests, [(0, 90, (4, 6))])

    def test_unrelated_renderer_error_is_never_retried_or_swallowed(self):
        error = RuntimeError("CUDA out of memory")
        render = self.Render({90: error})
        with self.assertRaises(RuntimeError) as caught:
            self.project(render, [90])
        self.assertIs(caught.exception, error)
        self.assertEqual(render.alpha_requests, [])


class PainterPinTests(unittest.TestCase):
    def test_the_launcher_pins_the_sheet_fill_helper_as_it_is(self):
        actual = hashlib.sha256(HELPER.read_bytes()).hexdigest().upper()
        launcher = (ROOT / "scripts" / "run_hy3d21_texture.ps1").read_text(encoding="utf-8")
        pinned = re.search(r"\$fillHelper = .*?-ne '([0-9A-F]{64})'", launcher, re.S).group(1)
        self.assertEqual(pinned, actual)

    def test_the_studio_painter_paints_a_batch_and_fills_near_the_mesh(self):
        source = (ROOT / "workflows" / "texture" / "hunyuan3d21" / "run_hy3d21_studio.py").read_text(encoding="utf-8")
        for needle in ('"--jobs"', '"--inpaint-reach"', '"--maps-only"', "from sheet_fill import inpaint_near", "def rearm",
                       "trimesh.geometry.mean_vertex_normals = _original_mean_vertex_normals"):
            self.assertIn(needle, source)

    def test_the_studio_painter_finishes_a_job_while_the_next_paints_and_reports_it_whole(self):
        source = (ROOT / "workflows" / "texture" / "hunyuan3d21" / "run_hy3d21_studio.py").read_text(encoding="utf-8")
        for needle in ("FINISH_BESIDE_NEXT = args.jobs is not None and args.maps_only",
                       "fill_as_upstream, texture.cpu().numpy(), mask_np, footprint",
                       "held = host_copy(self)", "os.replace(partial, report_path)", '"seconds_painting": on_card'):
            self.assertIn(needle, source)
        # The repository stores it with LF endings, and the launcher pins that file.
        self.assertNotIn(b"\r\n", (ROOT / "workflows" / "texture" / "hunyuan3d21" / "run_hy3d21_studio.py").read_bytes())
        actual = hashlib.sha256(
            (ROOT / "workflows" / "texture" / "hunyuan3d21" / "run_hy3d21_studio.py").read_bytes()).hexdigest().upper()
        launcher = (ROOT / "scripts" / "run_hy3d21_texture.ps1").read_text(encoding="utf-8")
        self.assertIn("$expectedStudioRunnerHash = '{0}'".format(actual), launcher)
        catalog = json.loads((ROOT / "workflows" / "catalog.json").read_text(encoding="utf-8"))
        entry = next(item for item in catalog["workflows"] if item.get("id") == "hunyuan3d21_studio_runner")
        self.assertEqual(entry["sha256"], actual)


class StreamedPassTests(unittest.TestCase):
    """The pass lays each section as the painter finishes it; the model is the one laid after painting."""

    class AtOnce:
        """An executor that runs what it is given at once, so the stitch is planned before painting starts."""

        def __init__(self, *args, **keywords):
            pass

        def submit(self, function, *args, **keywords):
            from concurrent.futures import Future  # noqa: PLC0415
            future = Future()
            future.set_result(function(*args, **keywords))
            return future

        def shutdown(self, wait=True):
            pass

    def setUp(self):
        from PIL import Image  # noqa: PLC0415
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from compress_textures import read_glb, write_glb  # noqa: PLC0415
        from test_head_detail import glb_with_mesh  # noqa: PLC0415
        from test_paint_sections import picture_of, strip  # noqa: PLC0415
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        rng = np.random.default_rng(5)
        positions, uvs, triangles = strip()

        def png(pixels, mode):
            import io  # noqa: PLC0415
            buffer = io.BytesIO()
            Image.fromarray(pixels, mode).save(buffer, format="PNG")
            return buffer.getvalue()

        document, binary = read_glb(glb_with_mesh(positions, uvs, triangles, [
            png(rng.integers(0, 255, (64, 64, 3)).astype(np.uint8), "RGB"),
            png(rng.integers(0, 255, (64, 64, 3)).astype(np.uint8), "RGB")]))
        document["materials"][0]["pbrMetallicRoughness"]["metallicRoughnessTexture"] = {"index": 1}
        self.source = self.root / "painted.glb"
        self.source.write_bytes(write_glb(document, binary))
        alpha = picture_of(positions, triangles, paint_sections.GENERATOR_FRAME)
        picture = np.zeros(alpha.shape + (4,), dtype=np.uint8)
        picture[..., :3] = 150
        picture[..., 3] = alpha
        self.reference = self.root / "reference.png"
        Image.fromarray(picture, "RGBA").save(self.reference)
        self.legacy = self.root / "studio"
        (self.legacy / ".venv-hy3d21" / "Scripts").mkdir(parents=True)
        (self.legacy / ".venv-hy3d21" / "Scripts" / "python.exe").write_bytes(b"")
        self.launcher = self.root / "launch.ps1"
        self.launcher.write_text("", encoding="utf-8")
        saved = paint_sections.paint_batch, paint_sections.ThreadPoolExecutor
        self.addCleanup(lambda: (setattr(paint_sections, "paint_batch", saved[0]),
                                 setattr(paint_sections, "ThreadPoolExecutor", saved[1])))

    @staticmethod
    def painter(streamed):
        """paint_batch as the painter does it: each section's maps and gate in turn, the pass told after each."""
        from PIL import Image  # noqa: PLC0415

        def paint_batch(args, jobs, attempt, minutes_each=10.0, on_progress=None):
            for _, _, paint_dir, _ in jobs:
                paint_dir.mkdir(parents=True, exist_ok=True)
                rng = np.random.default_rng(100 + int(paint_dir.parent.name[-2:]))
                Image.fromarray(rng.integers(0, 255, (96, 96, 3)).astype(np.uint8), "RGB").save(paint_dir / "section.png")
                for name in ("section_metallic.png", "section_roughness.png"):
                    Image.fromarray(rng.integers(0, 255, (96, 96)).astype(np.uint8), "L").save(paint_dir / name)
                (paint_dir / "section.validation.json").write_text(json.dumps(
                    {"faces_equal": True, "geometry_delta": 0.0, "uv_delta": 0.0, "seconds": 1.0}), encoding="utf-8")
                if streamed and on_progress is not None:
                    on_progress()
            return 0
        return paint_batch

    def run_pass(self, name, streamed, *extra):
        paint_sections.paint_batch = self.painter(streamed)
        output, report = self.root / (name + ".glb"), self.root / (name + ".json")
        code = paint_sections.main(["--", str(self.source), str(output), str(report), "--reference", str(self.reference),
                                    "--legacy-root", str(self.legacy), "--launcher", str(self.launcher),
                                    "--atlas", "2048", *extra])
        self.assertEqual(code, 0)
        return output.read_bytes(), json.loads(report.read_text(encoding="utf-8"))

    def test_sections_laid_as_they_are_painted_make_the_model_laid_after_painting(self):
        paint_sections.ThreadPoolExecutor = self.AtOnce
        streamed, receipt = self.run_pass("streamed", True)
        after, later = self.run_pass("after", False)
        self.assertEqual(streamed, after)
        self.assertTrue(receipt["painted"])
        self.assertEqual(receipt["sections_laid_while_painting"], len(receipt["plan"]["sections"]))
        self.assertEqual(later["sections_laid_while_painting"], 0)
        self.assertTrue(receipt["composite"]["metallic_roughness_replaced"])
        self.assertIn("planning_the_stitch", receipt["seconds_by_step"])

    def test_the_stitch_planned_beside_the_painter_makes_the_same_model(self):
        planned_beside, _ = self.run_pass("beside", True)
        paint_sections.ThreadPoolExecutor = self.AtOnce
        planned_first, _ = self.run_pass("first", True)
        self.assertEqual(planned_beside, planned_first)

    def test_matching_neighbours_still_lays_every_section(self):
        matched, receipt = self.run_pass("matched", True, "--keep-colour", "0")
        self.assertTrue(receipt["painted"])
        self.assertTrue(all("colour_gain" in section for section in receipt["plan"]["sections"]))
        self.assertTrue(receipt["composite"]["metallic_roughness_replaced"])
        launcher = (ROOT / "scripts" / "run_hy3d21_texture.ps1").read_text(encoding="utf-8")
        for needle in ("[string] $Jobs", "$InpaintReach", "'--jobs'", "'--inpaint-reach'", "'--maps-only'"):
            self.assertIn(needle, launcher)


if __name__ == "__main__":
    unittest.main()
