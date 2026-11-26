"""The section pass, faster and the same: fill near the mesh, one painter run, sums only where sections weigh.

A hero stair took two hours, 114 minutes of it in 33 sections. Each section's
painter filled every empty texel of an 8192 sheet (140 s of its 210 s) and
loaded its models again (25 s), and the composite blurred the whole sheet for
every section and map (25-30 s each). These tests hold the faster paths to the
numbers of the slow ones on the texels that are used.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import paint_sections  # noqa: E402
from paint_sections import LUMINANCE, composite, masked_blur, masked_blur_at, repad  # noqa: E402

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


class FakePainter:
    """Popen for paint_batch: writes each job's gate as the painter would, or never finishes."""

    calls = []
    hang = False

    def __init__(self, command, **keywords):
        FakePainter.calls.append(command)
        self.pid = 4321
        self.returncode = None
        if not FakePainter.hang:
            jobs = json.loads(Path(command[command.index("-Jobs") + 1]).read_text(encoding="utf-8"))
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
        FakePainter.calls, FakePainter.hang = [], False
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

    def test_a_section_the_painter_failed_says_why(self):
        paint_sections.paint_batch(self.args, self.jobs, self.root)
        self.assertIn("CUDA out of memory", paint_sections.why_unpainted(self.jobs[2][2], self.root))
        with self.assertRaises(RuntimeError):
            paint_sections.read_paint(self.jobs[2][2])

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
        launcher = (ROOT / "scripts" / "run_hy3d21_texture.ps1").read_text(encoding="utf-8")
        for needle in ("[string] $Jobs", "$InpaintReach", "'--jobs'", "'--inpaint-reach'", "'--maps-only'"):
            self.assertIn(needle, launcher)


if __name__ == "__main__":
    unittest.main()
