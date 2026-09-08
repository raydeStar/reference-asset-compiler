"""Routing and immutable binding checks without requiring a Blender installation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/blender/transfer_surface_normals.py'

class SurfaceNormalLoadingTests(unittest.TestCase):
    def setUp(self):
        self.bpy = MagicMock()
        with patch.dict('sys.modules', {'bpy': self.bpy, 'mathutils': MagicMock(),
                                       'mathutils.bvhtree': MagicMock()}):
            spec = importlib.util.spec_from_file_location('surface_normal_test_subject', SCRIPT)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)

    def test_native_authority_is_opened_without_gltf_import(self):
        self.module.load_reduced_authority(Path('approved.blend'))
        self.bpy.ops.wm.open_mainfile.assert_called_once_with(filepath='approved.blend')
        self.bpy.ops.import_scene.gltf.assert_not_called()

    def test_gltf_authority_keeps_existing_import_route(self):
        self.module.load_reduced_authority(Path('approved.glb'))
        self.bpy.ops.wm.read_factory_settings.assert_called_once_with(use_empty=True)
        self.bpy.ops.import_scene.gltf.assert_called_once_with(filepath='approved.glb')

    def test_unsupported_format_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.module.load_reduced_authority(Path('unbound.obj'))

    def test_region_is_zero_outside_and_full_inside(self):
        region = {'minimum': [-1,-1,-1], 'maximum': [1,1,1], 'feather': .2}
        self.assertEqual(self.module.region_weight((0,0,0), region), 1)
        self.assertEqual(self.module.region_weight((1,0,0), region), 0)
        self.assertEqual(self.module.region_weight((0,0,2), region), 0)
        self.assertAlmostEqual(self.module.region_weight((.9,0,0), region), .5)

    def test_region_requires_finite_bounds_and_exact_binding(self):
        region = {'schema':'reference-asset-compiler.normal-region.v1',
                  'authority_sha256':'source', 'reduced_sha256':'target',
                  'minimum':[-1,-1,-1], 'maximum':[1,1,1], 'feather':.1}
        self.module.validate_region(region, 'source', 'target')
        for changed in [{'feather':0}, {'minimum':[0,0,float('nan')]},
                        {'maximum':[0]}, {'authority_sha256':'wrong'}]:
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.module.validate_region({**region, **changed}, 'source', 'target')

    def test_rejected_input_needs_explicit_diagnostic_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            source, reduced = Path(directory)/'source', Path(directory)/'reduced'
            source.write_bytes(b'authority')
            reduced.write_bytes(b'candidate')
            report = {'source': {'sha256': self.module.sha(source)},
                      'output': {'sha256': self.module.sha(reduced)}, 'status': 'rejected'}
            with self.assertRaises(RuntimeError):
                self.module.validate_reduction_binding(report, source, reduced)
            self.module.validate_reduction_binding(report, source, reduced, True)
            self.assertEqual(report['status'], 'rejected')

    def test_diagnostic_flag_never_relaxes_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, reduced = Path(directory)/'source', Path(directory)/'reduced'
            source.write_bytes(b'authority')
            reduced.write_bytes(b'candidate')
            report = {'source': {'sha256': self.module.sha(source)},
                      'output': {'sha256': self.module.sha(reduced)}, 'status': 'rejected'}
            for field in ('source', 'output'):
                with self.subTest(field=field):
                    changed = {**report, field: {'sha256': 'changed'}}
                    with self.assertRaises(RuntimeError):
                        self.module.validate_reduction_binding(changed, source, reduced, True)

    def test_incomplete_attempt_is_not_a_diagnostic_mesh(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source'
            source.write_bytes(b'authority')
            report = {'source': {'sha256': self.module.sha(source)},
                      'output': {'sha256': self.module.sha(source)}, 'status': 'failed'}
            with self.assertRaises(RuntimeError):
                self.module.validate_reduction_binding(report, source, source, True)

if __name__ == '__main__':
    unittest.main()
