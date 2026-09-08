import copy
import json
from pathlib import Path
import unittest

from reference_asset_compiler.neck_transition import geometry_seam_weight, seam_weight, smoothstep, srgb_to_linear, validate_config


class NeckTransitionTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((Path(__file__).resolve().parents[1]/'recipes/assemblies/sunset-ayric-neck-transition.json').read_text())

    def test_recipe_has_pinned_authorities(self):
        validate_config(self.cfg)

    def test_clamped_smooth_feather(self):
        self.assertEqual(smoothstep(0,1,-1),0)
        self.assertEqual(smoothstep(0,1,2),1)
        self.assertEqual(smoothstep(0,1,.5),.5)
        with self.assertRaises(ValueError):
            smoothstep(1,1,1)

    def test_linear_color_encoding(self):
        self.assertEqual(srgb_to_linear(0),0)
        self.assertEqual(srgb_to_linear(1),1)
        self.assertAlmostEqual(srgb_to_linear(.5),.21404114)
        for bad in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):
                srgb_to_linear(bad)

    def test_skin_transfers_but_blue_clothing_does_not(self):
        self.assertEqual(seam_weight((0,0,1.6),(.7,.4,.2),.001,self.cfg),1)
        self.assertEqual(seam_weight((0,0,1.6),(.05,.2,.5),.001,self.cfg),0)

    def test_geometry_mask_does_not_depend_on_sparse_corner_color(self):
        self.assertEqual(geometry_seam_weight((0,0,1.6),.001,self.cfg),1)
        self.assertEqual(geometry_seam_weight((0,0,1.4),.001,self.cfg),0)

    def test_outside_and_far_surfaces_untouched(self):
        for point,distance in [((0,0,1.4),0),((1,0,1.6),0),((0,0,1.6),.061)]:
            self.assertEqual(seam_weight(point,(.7,.4,.2),distance,self.cfg),0)

    def test_rejects_bad_measurements(self):
        for point,rgb,distance in [((0,0),(.7,.4,.2),0),((0,0,1.6),(2,0,0),0),((0,0,1.6),(.7,.4,.2),-1),((0,0,float('nan')),(.7,.4,.2),0)]:
            with self.assertRaises(ValueError):
                seam_weight(point,rgb,distance,self.cfg)

    def test_rejects_unpinned_or_invalid_recipes(self):
        for key,value in [('schema','v0'),('body_texture_sha256',''),('maximum_surface_distance_m',0),('bounds_min_m',[0,0]),('pixel_fade_bottom_m',[2,1]),('target_roughness',2)]:
            cfg=copy.deepcopy(self.cfg)
            cfg[key]=value
            with self.assertRaises(ValueError):
                validate_config(cfg)


if __name__=='__main__':
    unittest.main()
