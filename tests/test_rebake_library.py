"""Reducing and re-baking a whole library of painted props, without Blender.

The runner's job is bookkeeping a person can trust: refuse an item list that
names files that are not there, keep a source the budget says is already
close enough, record every prop as it finishes so a stopped run resumes, and
add up what was saved only over what was actually accepted. The stages
themselves are stood in for here.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler import appearance  # noqa: E402
from reference_asset_compiler.appearance import comparison_sheet, judge, worst_patch  # noqa: E402

SPEC = importlib.util.spec_from_file_location("rebake_library", ROOT / "scripts" / "rebake_library.py")
library = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(library)


class FakeStages:
    """Stands in for run_stage, writing the receipts the real stages would."""

    def __init__(self, keep_source=False, reduce_ok=True, verdict="accepted"):
        self.keep_source, self.reduce_ok, self.verdict = keep_source, reduce_ok, verdict
        self.calls = []

    def __call__(self, stage, source, output, report, **kwargs):
        self.calls.append((stage, Path(source), kwargs.get("options")))
        report = Path(report)
        if stage == "reduce-mesh":
            if not self.reduce_ok:
                return {"ok": False, "error": "surface gates refused every rung"}
            native = report.parent / "reduced-attempt" / "feature-qem-candidate.blend"
            native.parent.mkdir(parents=True, exist_ok=True)
            native.write_bytes(b"reduced")
            report.write_text(json.dumps({
                "budget_decision": {"role": "prop", "triangle_budget": 10000,
                                    "ladder": [10000, 15000], "keep_source": self.keep_source,
                                    "summary": "A medium prop."},
                "output": {"path": str(native)}}), encoding="utf-8")
            return {"ok": True, "attempt_directory": str(native.parent)}
        accepted = self.verdict == "accepted"
        report.write_text(json.dumps({
            "status": self.verdict,
            "attempts": [{"rung": 10000, "triangles": 10000, "uv_layout": "kept",
                          "appearance": {"passed": accepted, "summary": {
                              "beauty": {"minimum_ssim": 0.95 if accepted else 0.90},
                              "albedo": {"minimum_ssim": 0.98}}}}],
            "accepted": {"rung": 10000, "triangles": 10000, "uv_layout": "kept",
                         "delivered_to": str(output)} if accepted else None,
            "savings": {"dense_triangles": 100000, "runtime_triangles": 10000,
                        "share_saved": 0.9} if accepted else None,
            "failures": [] if accepted else ["No rung kept the original's appearance"]}),
            encoding="utf-8")
        return {"ok": accepted, "attempt_directory": str(report.parent / "rebake-attempt")}


class Library(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.dense = self.root / "cog-2m.blend"
        self.dense.write_bytes(b"dense")
        self.reference = self.root / "cog-2m.glb"
        self.reference.write_bytes(b"delivered")
        self.progress = self.root / "out" / "progress.json"

    def items(self, **changes):
        item = {"name": "cog-2m", "dense": str(self.dense), "reference": str(self.reference),
                "notes": "A 2 m bronze cog"}
        item.update(changes)
        path = self.root / "items.json"
        path.write_text(json.dumps([item]), encoding="utf-8")
        return library.load_items(path, self.root / "out")

    def test_an_item_naming_a_missing_file_is_refused_before_anything_runs(self):
        with self.assertRaises(library.LibraryError):
            self.items(dense=str(self.root / "gone.blend"))
        with self.assertRaises(library.LibraryError):
            self.items(reference=str(self.root / "gone.glb"))

    def test_the_reduction_is_asked_for_by_the_budget_table_not_a_number(self):
        stages = FakeStages()
        library.process(self.items()[0], "blender.exe", 8, self.progress, run=stages)

        stage, source, options = stages.calls[0]
        self.assertEqual(stage, "reduce-mesh")
        self.assertEqual(options["triangle_budget"], "auto")
        self.assertTrue(options["runtime_derivative"])
        # Notes may promote a role, so they travel with the name.
        self.assertEqual(options["asset_notes"], "A 2 m bronze cog")

    def test_the_rebake_reads_the_native_reduction_and_is_judged_against_the_reference(self):
        stages = FakeStages()
        entry = library.process(self.items()[0], "blender.exe", 6, self.progress, run=stages)

        stage, source, options = stages.calls[1]
        self.assertEqual(stage, "rebake-maps")
        self.assertEqual(source.suffix, ".blend")
        self.assertEqual(Path(options["appearance_reference"]), self.reference)
        self.assertEqual(options["threads"], 6)
        self.assertEqual(entry["status"], "accepted")

    def test_a_source_already_close_to_its_budget_is_kept_and_nothing_is_baked(self):
        stages = FakeStages(keep_source=True)
        entry = library.process(self.items()[0], "blender.exe", 8, self.progress, run=stages)

        self.assertEqual(entry["status"], "kept_source")
        self.assertEqual([call[0] for call in stages.calls], ["reduce-mesh"])

    def test_a_refused_reduction_is_recorded_not_retried(self):
        entry = library.process(self.items()[0], "blender.exe", 8, self.progress,
                                run=FakeStages(reduce_ok=False))

        self.assertEqual(entry["status"], "reduction_refused")
        self.assertIn("refused", entry["error"])

    def test_every_prop_is_recorded_as_it_finishes_so_a_stopped_run_resumes(self):
        library.process(self.items()[0], "blender.exe", 8, self.progress, run=FakeStages())

        self.assertIn("cog-2m", library.read_progress(self.progress))

    def test_savings_are_added_up_only_over_what_was_accepted(self):
        progress = {
            "cog-2m": {"status": "accepted", "savings": {"dense_triangles": 100000,
                                                         "share_saved": 0.85},
                       "accepted": {"triangles": 15000, "uv_layout": "kept"},
                       "attempts": [{"rung": 15000, "appearance": {
                           "beauty": {"minimum_ssim": 0.957}, "albedo": {"minimum_ssim": 0.988}}}]},
            "valve-wheel": {"status": "rejected", "savings": None, "accepted": None,
                            "attempts": [{"rung": 10000}]},
            "handhold": {"status": "kept_source"},
        }

        summary = library.summarise(progress)

        self.assertEqual(summary["accepted_dense_triangles"], 100000)
        self.assertEqual(summary["accepted_runtime_triangles"], 15000)
        self.assertEqual(summary["counts"], {"accepted": 1, "rejected": 1, "kept_source": 1})
        table = library.markdown(summary)
        self.assertIn("100,000 -> 15,000", table)
        self.assertIn("0.957 / 0.988", table)


class LocalFlaws(unittest.TestCase):
    def test_a_crack_the_mean_forgives_fails_on_its_worst_patch(self):
        size = 96
        rng = np.random.default_rng(3)
        texture = rng.random((size, size))
        cracked = texture.copy()
        cracked[40:56, 40:56] = 0.0
        inside = np.ones((size, size), dtype=bool)

        similarity = appearance.ssim_map(texture, cracked)

        self.assertGreater(float(similarity.mean()), 0.9)
        self.assertLess(worst_patch(similarity, inside), 0.35)

    def test_background_patches_cannot_be_the_worst_patch(self):
        similarity = np.ones((64, 64))
        similarity[:8, :8] = -1.0
        inside = np.zeros((64, 64), dtype=bool)
        inside[16:48, 16:48] = True

        self.assertAlmostEqual(worst_patch(similarity, inside), 1.0)

    def test_the_verdict_names_a_local_flaw(self):
        views = [{"pass": "beauty", "view": "front", "ssim": 0.97, "silhouette_iou": 0.99,
                  "worst_patch_ssim": 0.12}]

        passed, failures = judge(views)

        self.assertFalse(passed)
        self.assertIn("patch", failures[0])


class ComparisonSheet(unittest.TestCase):
    def test_one_row_per_version_four_views_wide(self):
        root = Path(tempfile.mkdtemp())
        rows = []
        for name in ("original", "rebaked"):
            directory = root / name
            directory.mkdir()
            for view in appearance.FIXED_VIEWS:
                pixels = np.zeros((32, 32, 4), dtype=np.uint8)
                pixels[8:24, 8:24] = (200, 120, 60, 255)
                Image.fromarray(pixels, "RGBA").save(directory / "beauty-{0}.png".format(view))
            rows.append((name.title(), "detail", directory))

        path = comparison_sheet(rows, "beauty", root / "sheet.png")

        with Image.open(path) as sheet:
            self.assertEqual(sheet.size[0], 32 * 4)
            self.assertEqual(sheet.size[1], 2 * (32 + 46))


if __name__ == "__main__":
    unittest.main()
