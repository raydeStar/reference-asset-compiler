"""Prove that recovering a bake is not enlarging a smaller picture."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from scripts.recover_fullsize_paint_maps import recover, sha
from scripts.crank_from_image import recovered_paint_maps


class FullsizePaintRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.attempt = self.root / "attempt"
        self.diag = self.attempt / "diagnostics"
        self.diag.mkdir(parents=True)
        self.output = self.root / "recovered"
        self.uv, self.reference = self.root / "input.obj", self.root / "reference.png"
        self.uv.write_bytes(b"uv-fixture")
        self.reference.write_bytes(b"reference-fixture")
        (self.attempt / "painted.obj").write_bytes(b"painted-mesh-fixture")
        (self.attempt / "painted.validation.json").write_text(json.dumps({
            "faces_equal": True, "geometry_delta": 0, "uv_delta": 0,
            "source_mesh": str(self.uv), "reference": str(self.reference)}))
        albedo = Image.fromarray(np.full((16, 16, 3), (40, 100, 180), dtype=np.uint8))
        mr = Image.fromarray(np.full((16, 16, 3), (30, 200, 0), dtype=np.uint8))
        albedo.save(self.diag / "post-inpaint-albedo.png")
        mr.save(self.diag / "post-inpaint-metallic-roughness.png")
        for suffix, image in (("", albedo), ("_metallic", mr.getchannel("R")), ("_roughness", mr.getchannel("G"))):
            image.resize((8, 8), Image.Resampling.BOX).save(self.attempt / ("painted" + suffix + ".jpg"), quality=100)

    def tearDown(self):
        self.temp.cleanup()

    def test_recovery_preserves_full_albedo_and_authored_channels(self):
        receipt = recover(self.attempt, self.output)
        self.assertFalse(receipt["upscaled"])
        self.assertEqual(sha(self.diag / "post-inpaint-albedo.png"), sha(self.output / "BaseColor.png"))
        self.assertEqual(30, Image.open(self.output / "Metallic.png").getpixel((0, 0)))
        self.assertEqual(200, Image.open(self.output / "Roughness.png").getpixel((0, 0)))
        maps = recovered_paint_maps(self.output, self.attempt / "painted.obj", self.uv, self.reference)
        self.assertEqual(3, len(maps))

    def test_unrelated_diagnostic_bake_is_refused(self):
        Image.new("RGB", (16, 16), (255, 255, 255)).save(self.diag / "post-inpaint-albedo.png")
        with self.assertRaisesRegex(ValueError, "correspondence failed"):
            recover(self.attempt, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_recovery_is_never_overwritten(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "immutable"):
            recover(self.attempt, self.output)

    def test_named_output_and_separate_diagnostics_preserve_the_same_payload(self):
        diagnostics = self.root / "separate-diagnostics"
        self.diag.rename(diagnostics)
        for path in self.attempt.glob("painted*"):
            path.rename(path.with_name(path.name.replace("painted", "plant", 1)))
        receipt = recover(self.attempt, self.output, stem="plant", diagnostics=diagnostics)
        self.assertEqual(sha(diagnostics / "post-inpaint-albedo.png"), sha(self.output / "BaseColor.png"))
        self.assertEqual(sha(self.attempt / "plant.obj"), receipt["source_obj_sha256"])
        self.assertFalse(receipt["inference_rerun"])

    def test_output_stem_cannot_escape_attempt_directory(self):
        for stem in ("", "..", "../plant"):
            with self.subTest(stem=stem), self.assertRaisesRegex(ValueError, "filename stem"):
                recover(self.attempt, self.output, stem=stem)
        self.assertFalse(self.output.exists())

    def test_changed_recovered_map_refused_by_operator(self):
        recover(self.attempt, self.output)
        (self.output / "Metallic.png").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "hash changed"):
            recovered_paint_maps(self.output, self.attempt / "painted.obj", self.uv, self.reference)
