"""Observable publication tests; simulated Blender output is not asset approval."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler.io import read_json, sha256_file, write_json
from reference_asset_compiler.prop_publication import normalization_report

spec = importlib.util.spec_from_file_location("prop_compile", ROOT / "scripts/compile_prop.py")
prop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prop)


class PropCompileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.addCleanup(patch.stopall)
        patch.object(prop, "ROOT", self.root).start()
        self.source = self.root / "source.fbx"
        self.source.write_bytes(b"source-fixture")
        self.texture = self.root / "color.png"
        self.texture.write_bytes(b"texture-fixture")
        self.recipe = self.root / "recipe.json"
        write_json(self.recipe, {"asset_id": "test-prop", "kind": "static_prop",
                                "source": {"authority_fbx": str(self.source)},
                                "material_textures": {"M_Body": {"BaseColor": str(self.texture)}}})
        self.out = self.root / "out/test-prop"

    def fake_blender(self, command, **kwargs):
        self.assertIn("--python-exit-code", command)
        recipe, fbx, report, texture_map, run_id = command[command.index("--") + 1:]
        fbx = Path(fbx)
        fbx.write_bytes(b"fresh-fbx-output")
        write_json(Path(report), {
            "schema": "reference-asset-compiler.prop-normalization.v1", "run_id": run_id,
            "asset_id": "test-prop", "source_authority": str(self.source),
            "source_sha256": sha256_file(self.source), "input_recipe_sha256": sha256_file(Path(recipe)),
            "input_texture_hashes": {str(Path(path).resolve()): sha256_file(Path(path))
                                     for slots in read_json(Path(texture_map)).values()
                                     for path in slots.values()},
            "output_fbx": str(fbx), "output_fbx_sha256": sha256_file(fbx),
            "after": {"height_m": 1.0, "tris": 12},
        })
        return subprocess.CompletedProcess(command, 0, "fixture completed", "")

    def compile(self, runner):
        with patch.object(prop.subprocess, "run", side_effect=runner):
            return prop.compile_prop(self.recipe, Path("fake-blender"))

    def test_success_publishes_hash_bound_payload_and_retains_attempt(self):
        self.compile(self.fake_blender)
        manifest = read_json(self.out / "test-prop.ue5import.json")
        receipt_path = self.out / manifest["compile_receipt"]["file"]
        self.assertEqual(sha256_file(receipt_path), manifest["compile_receipt"]["sha256"])
        for name, digest in read_json(receipt_path)["files"].items():
            self.assertEqual(digest, sha256_file(self.out / name))
        attempts = list((self.root / "work/test-prop/compile-attempts").iterdir())
        self.assertEqual(1, len(attempts))
        self.assertEqual("published", read_json(attempts[0] / "execution.json")["status"])
        self.assertTrue((attempts[0] / "payload/test-prop.fbx").is_file())
        # Windows CI may use an 8.3 temporary path; compare file identity, not spelling.
        self.assertTrue(normalization_report(
            self.root / "work/test-prop", self.out / "test-prop.ue5import.json"
        ).samefile(self.out / "normalize-prop-report.json"))

    def test_consumers_refuse_modified_published_payload(self):
        self.compile(self.fake_blender)
        (self.out / "test-prop.fbx").write_bytes(b"changed-after-publication")
        with self.assertRaisesRegex(ValueError, "hash changed"):
            normalization_report(self.root / "work/test-prop", self.out / "test-prop.ue5import.json")

    def test_jpeg_input_keeps_the_downstream_png_filename_and_encoding(self):
        jpeg = self.root / "color.jpg"
        Image.new("RGB", (8, 8), (90, 120, 150)).save(jpeg)
        recipe = read_json(self.recipe)
        recipe["material_textures"]["M_Body"]["BaseColor"] = str(jpeg)
        write_json(self.recipe, recipe)
        self.compile(self.fake_blender)
        texture = self.out / "textures/T_Body_BaseColor.png"
        with Image.open(texture) as image:
            self.assertEqual("PNG", image.format)
        normalization_report(self.root / "work/test-prop", self.out / "test-prop.ue5import.json")

    def test_historical_report_location_is_preserved(self):
        self.out.mkdir(parents=True)
        manifest = self.out / "test-prop.ue5import.json"
        write_json(manifest, {"fbx": "test-prop.fbx"})
        job = self.root / "work/test-prop"
        write_json(job / "normalize-prop-report.json", {"before": {}, "after": {}})
        self.assertEqual(job / "normalize-prop-report.json", normalization_report(job, manifest))

    def test_stale_report_cannot_stand_in_for_missing_new_output(self):
        old = self.root / "work/test-prop/normalize-prop-report.json"
        write_json(old, {"source_authority": "old.fbx", "after": {"height_m": 1, "tris": 12}})
        original = old.read_bytes()
        with self.assertRaises(FileNotFoundError):
            self.compile(lambda *a, **k: subprocess.CompletedProcess([], 0, "", "script failed"))
        self.assertFalse(self.out.exists())
        self.assertEqual(original, old.read_bytes())
        receipt = next((self.root / "work").rglob("execution.json"))
        self.assertEqual("failed", read_json(receipt)["status"])

    def test_failure_or_tampering_cannot_publish(self):
        for mode in ("exit", "missing-fbx", "output", "source", "texture", "recipe", "run-id"):
            with self.subTest(mode=mode):
                def runner(command, **kwargs):
                    result = self.fake_blender(command, **kwargs)
                    recipe, fbx, report, texture_map, _ = command[command.index("--") + 1:]
                    if mode == "exit":
                        result.returncode = 1
                    elif mode == "missing-fbx":
                        Path(fbx).unlink()
                    elif mode in ("output", "source", "texture", "recipe"):
                        target = {"output": Path(fbx), "source": self.source,
                                  "texture": self.texture, "recipe": Path(recipe)}[mode]
                        target.write_bytes(b"modified-after-stage")
                    else:
                        data = read_json(Path(report))
                        data["run_id"] = "old-attempt"
                        write_json(Path(report), data)
                    return result
                with self.assertRaises((ValueError, RuntimeError)):
                    self.compile(runner)
                self.assertFalse(self.out.exists())

    def test_existing_authority_is_untouched_and_no_blender_is_launched(self):
        self.out.mkdir(parents=True)
        authority = self.out / "approved.fbx"
        authority.write_bytes(b"accepted-authority")
        with patch.object(prop.subprocess, "run") as runner, self.assertRaises(FileExistsError):
            prop.compile_prop(self.recipe, Path("fake"))
        runner.assert_not_called()
        self.assertEqual(b"accepted-authority", authority.read_bytes())

    def test_receipt_cannot_bind_stale_textures(self):
        def runner(command, **kwargs):
            result = self.fake_blender(command, **kwargs)
            report_path = Path(command[command.index("--") + 3])
            report = json.loads(report_path.read_text())
            report["input_texture_hashes"] = {}
            write_json(report_path, report)
            return result
        with self.assertRaisesRegex(ValueError, "texture hashes"):
            self.compile(runner)
        self.assertFalse(self.out.exists())
