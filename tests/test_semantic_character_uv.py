"""Corner topology and rig-preserving proxy contracts, without GPU inference."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location('semantic_character_uv', Path(__file__).resolve().parents[1] / 'scripts/blender/semantic_character_uv.py')
UV = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UV)


class SemanticCharacterUvTests(unittest.TestCase):
    def test_weld_is_proxy_only_and_nearby_surfaces_remain_distinct(self):
        positions = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1e-8]])
        source = positions.copy()
        faces = [(0, 1, 2), (3, 4, 5), (0, 6, 1)]
        vertices, proxy = UV.welded_proxy(positions, faces)
        np.testing.assert_array_equal(positions, source)
        self.assertEqual(len(vertices), 5)
        self.assertEqual(proxy[:2], [(0, 1, 2), (1, 3, 2)])
        self.assertEqual(faces[1], (3, 4, 5))
        self.assertNotEqual(proxy[2][0], proxy[2][1])

    def test_collapsing_a_face_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'collapse'):
            UV.welded_proxy(np.array([[0, 0, 0], [0, 0, 0], [1, 0, 0]]), [(0, 1, 2)])

    def test_shared_vertex_does_not_join_separate_uv_charts(self):
        faces = [(0, 1, 2), (0, 3, 4)]
        uvs = np.array([[[0, 0], [1, 0], [0, 1]], [[0, 0], [-1, 0], [0, -1]]])
        self.assertEqual(len(UV.charts(faces, uvs, ['a', 'a'])), 2)

    def test_both_edge_corners_and_atlas_must_match(self):
        faces = [(0, 1, 2), (2, 1, 3)]
        uvs = np.array([[[0., 0], [1, 0], [0, 1]], [[0., 1], [1, 0], [1, 1]]])
        self.assertEqual(len(UV.charts(faces, uvs, ['a', 'a'])), 1)
        self.assertEqual(len(UV.charts(faces, uvs, ['a', 'b'])), 2)
        uvs[1, 0] += .01
        self.assertEqual(len(UV.charts(faces, uvs, ['a', 'a'])), 2)

    def test_twist_bones_and_fingers_keep_their_sides(self):
        self.assertEqual(UV.region_of('lowerarm_twist_02_l'), 'forearm_l')
        self.assertEqual(UV.region_of('index_03_r'), 'hand_r')
        self.assertEqual(UV.atlas_of(UV.region_of('upperarm_l')), 'clothing')
        self.assertEqual(UV.atlas_of(UV.region_of('lowerarm_l')), 'skin')

    def test_overlap_audit_distinguishes_shared_edges_from_stacked_faces(self):
        square = np.array([[[0, 0], [1, 0], [0, 1]], [[1, 0], [1, 1], [0, 1]]])
        self.assertEqual(UV.raster_audit(square, 32)['overlapping_pixels'], 0)
        self.assertGreater(UV.raster_audit([square[0], square[0]], 32)['overlapping_pixels'], 450)

    def test_barycentric_coordinates_follow_the_same_corner_order(self):
        triangle = np.array([[.1, .2], [.8, .2], [.1, .9]])
        y, x, weights = UV.triangle_pixels(triangle, 64)
        np.testing.assert_allclose(weights @ triangle, np.stack((x + .5, y + .5), axis=1) / 64)

    def test_obj_transport_shares_matching_pairs_without_collapsing_a_uv_seam(self):
        points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 0, 0], [1, 1, 0]])
        faces = [(0, 1, 2), (3, 4, 2)]
        uvs = np.array([[[0., 0], [1, 0], [0, 1]], [[1., 0], [1, 1], [0, 1]]])
        lines = UV.region_obj(points, faces, uvs).splitlines()
        self.assertEqual(sum(line.startswith('v ') for line in lines), 4)
        self.assertEqual(sum(line.startswith('vt ') for line in lines), 4)
        self.assertEqual([line for line in lines if line.startswith('f ')], ['f 1/1 2/2 3/3', 'f 2/2 4/4 3/3'])
        uvs[1, 0] = [.5, .5]
        lines = UV.region_obj(points, faces, uvs).splitlines()
        self.assertEqual(sum(line.startswith('vt ') for line in lines), 5)
        self.assertEqual([line for line in lines if line.startswith('f ')][-1].split()[1], '2/4')


if __name__ == '__main__':
    unittest.main()
