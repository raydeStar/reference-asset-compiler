import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from scripts.verify_texture_repack import samples


class TextureRepackSamplesTests(unittest.TestCase):
    def test_constant_texture_remains_constant_at_four_surface_points(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"constant.png"
            Image.new("RGB", (16,16), (20,40,80)).save(path)
            uv = np.array([[[.1,.2],[.8,.2],[.8,.9]],[[.2,.2],[.4,.2],[.2,.4]]])
            result = samples(path,uv)
            self.assertEqual(result.shape, (8,3))
            np.testing.assert_allclose(result, np.tile([20,40,80],(8,1)))
