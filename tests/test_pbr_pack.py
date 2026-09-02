import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from promote_production import pack_orm


class PbrPackTests(unittest.TestCase):
    def _write(self, path, value, mode="L"):
        shape = (4, 4) if mode == "L" else (4, 4, 3)
        Image.fromarray(np.full(shape, value, dtype=np.uint8), mode=mode).save(path)

    def test_authored_channels_survive_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ao, base = root / "ao.png", root / "base.png"
            rough, metal, out = root / "rough.png", root / "metal.png", root / "orm.png"
            self._write(ao, 211)
            self._write(base, 128, "RGB")
            self._write(rough, 173)
            self._write(metal, 64)

            stats = pack_orm(ao, base, out, rough, metal)
            packed = np.asarray(Image.open(out).convert("RGB"))

            self.assertTrue(np.all(packed[..., 0] == 211))
            self.assertTrue(np.all(packed[..., 1] == 173))
            self.assertTrue(np.all(packed[..., 2] == 64))
            self.assertEqual(stats["roughness_source"], "authored per-material bake")
            self.assertEqual(stats["metallic_source"], "authored per-material bake")

    def test_legacy_build_retains_declared_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ao, base, out = root / "ao.png", root / "base.png", root / "orm.png"
            self._write(ao, 255)
            self._write(base, 128, "RGB")

            stats = pack_orm(ao, base, out)
            packed = np.asarray(Image.open(out).convert("RGB"))

            self.assertTrue(np.all(packed[..., 2] == 0))
            self.assertIn("legacy fallback", stats["roughness_source"])
            self.assertIn("legacy fallback", stats["metallic_source"])


if __name__ == "__main__":
    unittest.main()
