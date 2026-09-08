import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from scripts.rebake_delighted_views import linear, encode, transport_illumination
from scripts.run_hy3d_delight_probe import sha


class DelightTransportTests(unittest.TestCase):
    def test_color_transfer_roundtrips_all_eight_bit_values(self):
        values = np.arange(256,dtype=float)
        np.testing.assert_allclose(encode(linear(values))*255,values,atol=1e-10)

    def test_identity_donor_preserves_constant_source_exactly(self):
        source = Image.new("RGB",(512,512),(25,75,140))
        result = transport_illumination(source,source)
        np.testing.assert_array_equal(result,source)

    def test_luminance_gain_preserves_linear_chromaticity(self):
        source = Image.new("RGB",(512,512),(25,75,140))
        donor = Image.new("RGB",(512,512),(40,105,180))
        result = np.asarray(transport_illumination(source,donor))[200,200]
        before = linear(np.array([25,75,140],float))
        after = linear(result.astype(float))
        np.testing.assert_allclose(before/before.sum(),after/after.sum(),atol=.005)

    def test_probe_sha_hashes_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"fixture"
            path.write_bytes(b"abc")
            self.assertEqual(sha(path),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
