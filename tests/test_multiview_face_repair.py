import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from map_multiview_face_repair import linear, srgb, surface_anchor
from projection_visibility import project_surface


class MultiViewFaceTests(unittest.TestCase):
    def test_color_roundtrip_preserves_every_byte(self):
        values = np.arange(256,dtype=np.uint8)
        np.testing.assert_array_equal(srgb(linear(values)),values)

    def test_shared_anchor_reprojects_to_exact_original_pixel(self):
        data = {'screen':np.array([[[0.,0.],[100.,0.],[0.,100.]]]),'depth':np.array([[1.,4.,2.]])}
        point = np.array([20.4,33.2])
        triangle,weights = surface_anchor(data,point)
        screen,_ = project_surface(weights[None,:],data['screen'][triangle],data['depth'][triangle])
        np.testing.assert_allclose(screen[0],point,atol=1e-10)
        self.assertAlmostEqual(weights.sum(),1)

    def test_shared_anchor_chooses_foreground_not_hidden_surface(self):
        data = {'screen':np.array([[[0.,0.],[100.,0.],[0.,100.]]]*2),'depth':np.array([[4.,4.,4.],[2.,2.,2.]])}
        triangle,_ = surface_anchor(data,np.array([20.,30.]))
        self.assertEqual(triangle,1)

    def test_background_annotation_is_rejected(self):
        data = {'screen':np.array([[[0.,0.],[100.,0.],[0.,100.]]]),'depth':np.ones((1,3))}
        with self.assertRaisesRegex(ValueError,'misses the mesh'):
            surface_anchor(data,np.array([80.,80.]))


if __name__ == '__main__':
    unittest.main()
