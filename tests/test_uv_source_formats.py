"""A triangle transport gets a narrow invitation, not the keys to the manor."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


class UVSourceFormatTests(unittest.TestCase):
    def setUp(self):
        self.bpy = MagicMock()
        self.mesh = SimpleNamespace(type="MESH", data=SimpleNamespace(
            polygons=[SimpleNamespace(vertices=(0, 1, 2))]))
        self.bpy.context.scene.objects = [self.mesh]
        source = Path(__file__).resolve().parents[1] / "scripts/blender/prepare_texture_uv_transport.py"
        spec = importlib.util.spec_from_file_location("uv_source_test", source)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"bpy": self.bpy, "mathutils": MagicMock(),
                                      "mathutils.kdtree": MagicMock()}):
            spec.loader.exec_module(self.module)

    def test_glb_requires_explicit_static_opt_in(self):
        with self.assertRaisesRegex(RuntimeError, "explicitly enabled"):
            self.module.load_authority(Path("mesh.glb"), False)
        self.bpy.ops.import_scene.gltf.assert_not_called()

    def test_static_triangle_glb_is_read_without_mesh_editing(self):
        self.assertIs(self.mesh, self.module.load_authority(Path("mesh.glb"), True))
        self.bpy.ops.import_scene.gltf.assert_called_once_with(filepath="mesh.glb")
        self.bpy.ops.mesh.assert_not_called()
        self.bpy.ops.wm.save_as_mainfile.assert_not_called()

    def test_armature_glb_refused(self):
        self.bpy.context.scene.objects.append(SimpleNamespace(type="ARMATURE"))
        with self.assertRaisesRegex(RuntimeError, "not articulated"):
            self.module.load_authority(Path("mesh.glb"), True)

    def test_nontriangle_glb_refused(self):
        self.mesh.data.polygons[0].vertices = (0, 1, 2, 3)
        with self.assertRaisesRegex(RuntimeError, "triangulated"):
            self.module.load_authority(Path("mesh.glb"), True)

    def test_native_blend_route_is_unchanged(self):
        self.assertIs(self.mesh, self.module.load_authority(Path("mesh.blend"), False))
        self.bpy.ops.wm.open_mainfile.assert_called_once_with(filepath="mesh.blend")
        self.bpy.ops.import_scene.gltf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
