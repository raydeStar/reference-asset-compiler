"""Exercise import dispatch without starting a second Blender at the dinner table."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch


class DescribeMeshFormatTests(unittest.TestCase):
    def test_native_cleanup_uses_open_mainfile(self):
        bpy = MagicMock()
        source = Path(__file__).resolve().parents[1] / "scripts/blender/describe_mesh.py"
        spec = importlib.util.spec_from_file_location("describe_mesh_format_test", source)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"bpy": bpy, "mathutils": MagicMock()}):
            spec.loader.exec_module(module)
            module.import_any(Path("cleaned.blend"))
        bpy.ops.wm.open_mainfile.assert_called_once_with(filepath="cleaned.blend")
        bpy.ops.import_scene.gltf.assert_not_called()
        bpy.ops.wm.save_as_mainfile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
