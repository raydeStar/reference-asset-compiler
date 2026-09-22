"""UV discontinuities must not become normal-map conditioning discontinuities."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

SPEC = importlib.util.spec_from_file_location('seam_normals', Path(__file__).resolve().parents[1] / 'workflows/texture/hunyuan3d21/seam_normals.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def average(count, faces, face_normals):
    result = np.zeros((count, 3))
    np.add.at(result, np.asarray(faces).ravel(), np.repeat(face_normals, 3, axis=0))
    return result / np.maximum(np.linalg.norm(result, axis=1, keepdims=True), 1e-12)


class PainterSeamNormalTests(unittest.TestCase):
    def test_only_normals_are_shared_across_a_uv_split(self):
        points = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0], [0, 1, 0], [0, 0, 1]])
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        before_points, before_faces = points.copy(), faces.copy()
        geometry = SimpleNamespace(mean_vertex_normals=average)
        report = MODULE.install_seam_normal_repair(geometry, points, faces)
        normals = geometry.mean_vertex_normals(6, faces, np.array([[0., 0, 1], [1, 0, 0]]))
        np.testing.assert_allclose(normals[0], normals[3])
        np.testing.assert_allclose(normals[0], [2**-.5, 0, 2**-.5])
        np.testing.assert_array_equal(points, before_points)
        np.testing.assert_array_equal(faces, before_faces)
        self.assertEqual(report['normal_proxy_vertices'], 4)

    def test_other_topology_uses_original_calculation(self):
        geometry = SimpleNamespace(mean_vertex_normals=average)
        points = np.array([[0., 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]])
        MODULE.install_seam_normal_repair(geometry, points, [[0, 1, 2]])
        changed = np.array([[3, 1, 2]])
        normals = np.array([[0., 0, 1]])
        np.testing.assert_array_equal(geometry.mean_vertex_normals(4, changed, normals), average(4, changed, normals))

    def test_collapsed_face_is_refused_before_installing_hook(self):
        geometry = SimpleNamespace(mean_vertex_normals=average)
        with self.assertRaisesRegex(ValueError, 'collapse'):
            MODULE.install_seam_normal_repair(geometry, [[0, 0, 0], [0, 0, 0], [1, 0, 0]], [[0, 1, 2]])
        self.assertIs(geometry.mean_vertex_normals, average)
