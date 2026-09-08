"""The region roughness clamp must lift only what it was asked to and refuse bad inputs.

Runs the script as a subprocess against a synthetic four-map attempt so the
test covers the argument contract, the copy-drift checks and the receipt, not
just an inner function.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "clamp_region_roughness.py"
STEM = "cat-painted"
SIZE = 64


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ClampRegionRoughnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = root / "attempt007"
        self.source.mkdir()
        (self.source / f"{STEM}.obj").write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8")
        (self.source / f"{STEM}.mtl").write_text("newmtl cat\n", encoding="utf-8")
        Image.fromarray(np.full((SIZE, SIZE, 3), 120, np.uint8)).save(self.source / f"{STEM}.jpg", quality=95)
        Image.fromarray(np.zeros((SIZE, SIZE), np.uint8), mode="L").save(
            self.source / f"{STEM}_metallic.jpg", quality=95)
        rough = np.full((SIZE, SIZE), 242, np.uint8)  # ~0.95, the painted head
        rough[16:32, 16:32] = 28                        # ~0.11, a 256-texel mirror-glossy eye
        rough[40:44, 40:44] = 28                        # a 16-texel speck, below the size threshold
        Image.fromarray(rough, mode="L").save(self.source / f"{STEM}_roughness.jpg", quality=100)
        mask = np.zeros((SIZE, SIZE), np.uint8)
        mask[8:48, 8:48] = 255                          # region covers both the eye and the speck
        self.mask = root / "head-front.png"
        Image.fromarray(mask, mode="L").save(self.mask)
        self.output = root / "clamped-v1"

    def tearDown(self):
        self.tmp.cleanup()

    def run_clamp(self, *extra, output=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), str(output or self.output),
             "--region-mask", str(self.mask), "--min-component-texels", "100", *extra],
            capture_output=True, text=True)

    def test_lifts_only_the_large_glossy_component_and_preserves_everything_else(self):
        before = {name: sha256(self.source / name) for name in
                  (f"{STEM}.obj", f"{STEM}.mtl", f"{STEM}.jpg", f"{STEM}_metallic.jpg")}
        result = self.run_clamp()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REGION_ROUGHNESS_CLAMP_OK", result.stdout)
        report = json.loads((self.output / "roughness-clamp-report.json").read_text(encoding="utf-8"))
        for name, digest in before.items():
            self.assertEqual(sha256(self.output / name), digest, f"{name} must be copied bit-for-bit")
        kept = [c for c in report["components"] if c["kept"]]
        self.assertEqual(len(report["components"]), 2)
        self.assertEqual(len(kept), 1)
        self.assertGreaterEqual(kept[0]["texels"], 256)
        self.assertFalse(report["base_color_changed"])
        self.assertFalse(report["geometry_or_uv_changed"])
        written = np.asarray(Image.open(self.output / f"{STEM}_roughness.jpg").convert("L")).astype(float) / 255
        self.assertGreater(written[16:32, 16:32].mean(), 0.40, "the eye must reach the floor")
        self.assertLess(written[40:44, 40:44].mean(), 0.25, "the speck below threshold stays glossy")
        self.assertGreater(written[0:8, 0:8].mean(), 0.90, "texels outside the region are untouched")
        self.assertGreater(report["roughness_in_lift_mask"]["after_mean"],
                           report["roughness_in_lift_mask"]["before_mean"])

    def test_refuses_missing_region_mask(self):
        self.mask.unlink()
        result = self.run_clamp()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing region mask", result.stderr)

    def test_refuses_missing_source_map(self):
        (self.source / f"{STEM}_metallic.jpg").unlink()
        result = self.run_clamp()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing source file", result.stderr)

    def test_refuses_when_nothing_in_the_region_is_glossy(self):
        result = self.run_clamp("--glossy-below", "0.05")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No glossy component", result.stderr)
        self.assertFalse(self.output.exists(), "no partial output may be left behind")

    def test_refuses_to_overwrite_retained_output(self):
        self.output.mkdir()
        result = self.run_clamp()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to overwrite", result.stderr)


if __name__ == "__main__":
    unittest.main()
