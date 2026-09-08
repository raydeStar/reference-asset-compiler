"""Hermetic contract tests; fake files do not constitute a cooked engine test."""
import copy
import importlib.util
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler.io import sha256_file
from reference_asset_compiler.scene_tools import (
    bundle_scene_review, local_fog_falloff, plan_atmosphere, require_unchanged,
)


class AtmospherePlanTests(unittest.TestCase):
    def setUp(self):
        self.recipe = json.loads((ROOT / "examples/scene-atmosphere.json").read_text())

    def test_physical_falloff_accounts_for_engine_ui_scale(self):
        self.assertEqual(1200, local_fog_falloff(2400, 200))
        self.assertEqual(1750, local_fog_falloff(3500, 200))

    def test_planner_import_needs_no_site_packages_in_embedded_python(self):
        result = subprocess.run([sys.executable, "-S", "-c",
            "import sys; sys.path.insert(0, {0!r}); "
            "from reference_asset_compiler.scene_tools import local_fog_falloff; "
            "assert local_fog_falloff(2400, 200) == 1200".format(str(ROOT / "src"))],
            capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_plan_is_nonmutating_and_pending(self):
        before = copy.deepcopy(self.recipe)
        result = plan_atmosphere(self.recipe)
        self.assertEqual(before, self.recipe)
        self.assertEqual("pending", result["human_review"])
        self.assertFalse(result["changes_applied"])
        self.assertEqual(-280, result["operations"][0]["z_cm"])
        self.assertEqual(4.8, result["operations"][0]["uniform_scale"])
        self.assertEqual(0, result["operations"][0]["properties"]["radial_fog_extinction"])

    def test_rejects_nonfinite_boolean_zero_and_out_of_range(self):
        for value in (True, float("nan"), float("inf"), 0, -2, "200"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_fog_falloff(2400, value)
        with self.assertRaises(ValueError):
            local_fog_falloff(2400, .01)

    def test_rejects_source_overwrite_and_map_traversal(self):
        for target in (self.recipe["source_map"], "/Game/../Outside", "C:/level.umap"):
            self.recipe["target_map"] = target
            with self.assertRaises(ValueError):
                plan_atmosphere(self.recipe)

    def test_rejects_typos_duplicates_and_wrong_version(self):
        variants = []
        typo = copy.deepcopy(self.recipe)
        typo["fog"][0]["denisty"] = .1
        variants.append(typo)
        duplicate = copy.deepcopy(self.recipe)
        duplicate["fog"] *= 2
        variants.append(duplicate)
        version = copy.deepcopy(self.recipe)
        version["engine_adapter"] = "ue5.9"
        variants.append(version)
        for recipe in variants:
            with self.assertRaises(ValueError):
                plan_atmosphere(recipe)

    def test_static_snapshot_changes_have_named_failures(self):
        require_unchanged({"cup": [1, 2, 3]}, {"cup": [1, 2, 3]})
        with self.assertRaisesRegex(ValueError, "cup"):
            require_unchanged({"cup": [1, 2, 3]}, {"cup": [1, 2, 4]})

    def test_adapter_readback_checks_values_not_setter_return(self):
        spec = importlib.util.spec_from_file_location(
            "scene_adapter", ROOT / "scripts/ue5/apply_scene_atmosphere.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.matches(1200.00001, 1200))
        self.assertFalse(module.matches(12, 1200))
        self.assertTrue(module.matches(SimpleNamespace(r=.1, g=.2, b=.3), [.1, .2, .3]))


class SceneBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "portable"
        self.receipt_path = self.root / "source.json"
        self.package = self.root / "package"
        self.package.mkdir()
        (self.package / "RacValidate.exe").write_bytes(b"fixture executable, not a real game")
        (self.package / "content.pak").write_bytes(b"fixture package")
        self.map = self.root / "L_Test.umap"
        self.map.write_bytes(b"fixture map")
        self.frames = []
        for i in range(3):
            path = self.root / ("frame{0}.png".format(i))
            Image.new("RGB", (64, 64), (10 + i, 25, 50)).save(path)
            self.frames.append(path)
        self.audit = self.root / "audit.json"
        self.checks = {"possessed": True, "frames_written": True}
        self.audit.write_text(json.dumps({"ok": True, "map": "L_Test", "error": "",
            "cooked_runtime": True, "checks": self.checks,
            "frames": [str(p) for p in self.frames]}))
        self.invariants = self.root / "invariants.json"
        self.invariants.write_text(json.dumps({"maps": [self.bind(self.map)]}))
        self.receipt = {
            "schema": "reference-asset-compiler.scene-lighting-review.v1",
            "variant": '<script>alert("test")</script> café',
            "map": "/Game/L_Test", "map_sha256": sha256_file(self.map),
            "human_visual_review": False, "reviewer": "codex",
            "cooked_programmatic_checks": self.checks,
            "frames": [self.bind(p) for p in self.frames],
            "package": [self.bind(p) for p in self.package.iterdir()],
            "evidence": [self.bind(self.audit), self.bind(self.invariants)],
            "package_bytes": sum(p.stat().st_size for p in self.package.iterdir()),
        }
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def bind(self, path):
        return {"path": str(path.relative_to(self.root)), "sha256": sha256_file(path),
                "bytes": path.stat().st_size}

    def save(self):
        self.receipt_path.write_text(json.dumps(self.receipt), encoding="utf-8")

    def bundle(self):
        return bundle_scene_review(self.receipt_path, self.root, self.output)

    def test_portable_bundle_is_always_pending_and_escapes_html(self):
        self.receipt["human_visual_review"] = True
        self.save()
        result = self.bundle()
        self.assertEqual("pending", result["human_review"])
        self.assertFalse(result["production_ready"])
        page = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn("café", page)
        self.assertNotIn("<script>", page)
        self.assertNotIn(str(self.root), page)
        self.assertIn("Awaiting human approval", page)
        for frame in result["frames"]:
            self.assertEqual(frame["sha256"], sha256_file(self.output / frame["path"]))
        self.assertEqual(2, len(result["verified_inputs"]["package"]))
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_refuses_overwrite(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "overwritten"):
            self.bundle()

    def test_rejects_changed_frame_map_package_or_evidence(self):
        for path in [self.frames[0], self.map, self.package / "content.pak", self.audit]:
            old = path.read_bytes()
            path.write_bytes(old + b"changed")
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.bundle()
            self.assertFalse(self.output.exists())
            path.write_bytes(old)

    def test_missing_and_extra_package_files_fail(self):
        extra = self.package / "unbound.dll"
        extra.write_bytes(b"surprise")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.bundle()
        extra.unlink()
        (self.package / "content.pak").unlink()
        with self.assertRaises(ValueError):
            self.bundle()

    def test_saved_runtime_logs_do_not_invalidate_package(self):
        saved = self.package / "Saved"
        saved.mkdir()
        (saved / "runtime.log").write_text("runtime output")
        self.bundle()

    def test_bootstrap_and_nested_game_executable_are_both_bound(self):
        nested = self.package / "RacValidate/Binaries/Win64/RacValidate.exe"
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"fixture nested game")
        self.receipt["package"].append(self.bind(nested))
        self.receipt["package_bytes"] += nested.stat().st_size
        self.save()
        self.assertEqual(3, self.bundle()["package_files"])

    def test_output_inside_package_fails(self):
        self.output = self.package / "review"
        with self.assertRaisesRegex(ValueError, "outside the verified package"):
            self.bundle()

    def test_rejects_failed_empty_or_truthy_nonboolean_checks(self):
        for checks in ({}, {"ok": 1}, {"ok": False}, {"ok": "true"}):
            self.receipt["cooked_programmatic_checks"] = checks
            self.save()
            with self.assertRaises(ValueError):
                self.bundle()

    def test_receipt_and_audit_must_agree(self):
        self.receipt["map"] = "/Game/Other"
        self.save()
        with self.assertRaisesRegex(ValueError, "contradicts"):
            self.bundle()

    def test_duplicate_frames_fail(self):
        self.receipt["frames"][1] = self.receipt["frames"][0]
        self.save()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.bundle()

    def test_path_escape_fails(self):
        self.receipt["frames"][0]["path"] = "../outside.png"
        self.save()
        with self.assertRaisesRegex(ValueError, "outside"):
            self.bundle()

    def test_size_binding_is_enforced(self):
        self.receipt["frames"][0]["bytes"] += 1
        self.save()
        with self.assertRaisesRegex(ValueError, "Size mismatch"):
            self.bundle()

    def test_readable_non_png_is_not_accepted_as_a_capture(self):
        path = self.frames[0]
        Image.new("RGB", (64, 64)).save(path, format="JPEG")
        self.receipt["frames"][0] = self.bind(path)
        self.save()
        with self.assertRaisesRegex(ValueError, "PNG"):
            self.bundle()


if __name__ == "__main__":
    unittest.main()
