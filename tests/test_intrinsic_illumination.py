"""The illumination estimator must not become a replacement artwork generator."""

from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from transfer_intrinsic_illumination import encode, illumination_field, linear, validate_donor_signal, main


class IntrinsicIlluminationTests(unittest.TestCase):
    def test_srgb_roundtrip_preserves_every_byte(self):
        original = np.arange(256, dtype=np.uint8)
        np.testing.assert_array_equal(encode(linear(original)), original)

    def test_identical_image_has_no_gain(self):
        rng = np.random.default_rng(1)
        source = np.concatenate([rng.integers(0, 256, (48, 48, 3), dtype=np.uint8),
                                 np.full((48, 48, 1), 255, np.uint8)], axis=2)
        field, boundary = illumination_field(source, source[..., :3])
        np.testing.assert_allclose(field, 0, atol=1e-12)
        self.assertTrue(np.all((boundary >= 0) & (boundary <= 1)))

    def test_background_does_not_bias_foreground_gain(self):
        source = np.zeros((64, 64, 4), np.uint8)
        source[16:48, 16:48] = [100, 100, 100, 255]
        donor = np.full((64, 64, 3), 255, np.uint8)
        donor[16:48, 16:48] = 100
        field, boundary = illumination_field(source, donor)
        np.testing.assert_allclose(field, 0, atol=1e-12)
        self.assertEqual(boundary[0, 0], 0)

    def test_extreme_estimate_is_bounded(self):
        source = np.full((32, 32, 4), 255, np.uint8)
        source[..., :3] = 0
        field, _ = illumination_field(source, np.full((32, 32, 3), 255, np.uint8))
        np.testing.assert_allclose(field, np.log(2))

    def test_mismatched_view_is_refused(self):
        with self.assertRaises(ValueError):
            illumination_field(np.zeros((32, 32, 4)), np.zeros((64, 64, 3)))

    def test_black_silhouette_is_refused_before_transport(self):
        with self.assertRaisesRegex(ValueError, "black silhouette"):
            validate_donor_signal(np.full((32, 32, 4), 255, np.uint8), np.zeros((32, 32, 3), np.uint8))

    def test_actual_transport_preserves_head_and_original_atlas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            def digest(path):
                return hashlib.sha256(path.read_bytes()).hexdigest()
            mesh = root / "fixture.fbx"
            mesh.write_text("Synthetic test authority, not a real geometry claim")
            base = root / "base.png"
            original = np.full((64, 64, 3), 100, np.uint8)
            Image.fromarray(original).save(base)
            original_hash = digest(base)
            frames, donors = [], []
            uv = np.array([[[0, 0], [1, 0], [0, 1]], [[1, 1], [1, 0], [0, 1]]], float)
            screen = uv.copy()
            screen[..., 0] *= 63
            screen[..., 1] = (1 - screen[..., 1]) * 63
            for view in ("front", "side", "back", "opposite", "top", "bottom"):
                src = root / ("body-" + view + ".png")
                src_array = np.full((64, 64, 4), 100, np.uint8)
                src_array[..., 3] = 255
                Image.fromarray(src_array).save(src)
                target_dir = root / "donor"
                target_dir.mkdir(exist_ok=True)
                donor = target_dir / src.name
                Image.fromarray(np.full((64, 64, 3), 150, np.uint8)).save(donor)
                data = root / (view + ".npz")
                np.savez(data, uv=uv, screen=screen, height=np.array([[.4] * 3, [.9] * 3]),
                         cosine=np.ones((2, 3)), depth=np.ones((2, 3)),
                         depth_buffer=np.ones((64, 64)), depth_tolerance=np.array(.001))
                frames.append({"path": str(src), "sha256": digest(src), "correspondence": str(data),
                               "correspondence_sha256": digest(data)})
                donors.append({"path": str(donor), "sha256": digest(donor)})
            inputs = root / "inputs.json"
            inputs.write_text(json.dumps({"textures": {str(base): original_hash}, "source": str(mesh),
                                           "source_sha256": digest(mesh), "frames": frames}))
            inference = root / "inference.json"
            inference.write_text(json.dumps({"status": "candidate_needs_review",
                                              "inputs_receipt_sha256": digest(inputs), "outputs": donors}))
            output = root / "output"
            with patch.object(sys, "argv", ["transfer", str(inputs), str(inference), str(output)]):
                main()
            result = np.asarray(Image.open(output / "BaseColor.png"))
            head = np.asarray(Image.open(output / "protected-head.png")) > 0
            self.assertGreater(head.sum(), 1000)
            np.testing.assert_array_equal(result[head], original[head])
            self.assertTrue(np.any(result[~head] != original[~head]))
            self.assertEqual(digest(base), original_hash)


if __name__ == "__main__":
    unittest.main()
