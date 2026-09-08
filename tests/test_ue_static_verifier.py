"""Exercise the actual UE verifier with minimal engine doubles, not a second verifier."""
import os
from pathlib import Path
import runpy
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch


class Mesh:
    vertices = 14534
    def get_bounds(self):
        return NS(box_extent=NS(z=3.0))
    def get_editor_property(self, name):
        return [NS(get_editor_property=lambda key: NS(get_name=lambda: "M_Board"))]
    def get_num_lods(self):
        return 1
    def get_num_triangles(self, lod):
        return 15300
    def get_num_sections(self, lod):
        return 1


class StaticVerifierTests(unittest.TestCase):
    def run_verifier(self, vertices=14534, srgb=True, count_error=False):
        mesh = Mesh()
        mesh.vertices = vertices
        texture = NS(get_editor_property=lambda key: srgb)
        def counts(obj, lod):
            if count_error:
                raise RuntimeError("native buffer unavailable")
            return obj.vertices
        engine = NS(
            StaticMesh=Mesh, SkeletalMesh=type("SkeletalMesh", (), {}),
            MaterialInstance=type("MaterialInstance", (), {}),
            EditorAssetLibrary=NS(
                load_asset=lambda path: texture if "/Textures/" in path else mesh,
                find_asset_data=lambda path: NS(get_tag_values=lambda: {})),
            MaterialEditingLibrary=NS(get_used_textures=lambda material: [
                NS(get_name=lambda: "T_Base")]),
            EditorStaticMeshLibrary=NS(get_number_verts=counts))
        root = Path(__file__).resolve().parents[1]
        old_path = list(__import__("sys").path)
        try:
            with patch.dict(os.environ, {"RAC_ROOT": str(root)}), patch.dict(
                "sys.modules", {"unreal": engine, "import_asset": NS()}):
                module = runpy.run_path(str(root / "scripts/ue5/import_and_verify.py"))
                return module["verify"]({
                    "asset_id": "board", "ue5_mesh_type": "StaticMesh",
                    "measurements": {"height_cm_in_ue5": 6}, "lods": [{}],
                    "textures": {"M_Board": {"BaseColor": {
                        "file": "textures/T_Base.png", "settings": {"sRGB": True}}}}},
                    "/Game/Board", mesh_path="/Game/Board/Mesh")
        finally:
            __import__("sys").path[:] = old_path

    def test_static_checks_include_native_counts_and_texture_settings(self):
        result = self.run_verifier()
        self.assertTrue(result["ok"])
        self.assertEqual(14534, result["native_lods"][0]["vertices"])
        self.assertIn("texture_settings", [c["check"] for c in result["checks"]])

    def test_overbudget_built_mesh_fails(self):
        self.assertFalse(self.run_verifier(vertices=15973)["ok"])

    def test_static_wrong_srgb_fails(self):
        self.assertFalse(self.run_verifier(srgb=False)["ok"])

    def test_missing_native_measurement_is_not_a_pass(self):
        self.assertFalse(self.run_verifier(count_error=True)["ok"])
