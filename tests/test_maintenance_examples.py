"""Fresh-checkout examples and retained experiment entry points remain runnable."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MaintenanceExamplesTests(unittest.TestCase):
    def test_complete_approved_views_are_reused_and_partial_views_are_preserved(self):
        from unittest.mock import patch
        from scripts import compile_from_image as operator
        with tempfile.TemporaryDirectory() as directory:
            views = Path(directory)
            names = operator.MODELING_VIEW_NAMES
            for name in names:
                (views / name).write_bytes(name.encode())
            before = {path.name: path.read_bytes() for path in views.iterdir()}
            with patch.object(operator, "run_blender_stage") as render:
                self.assertTrue(operator.render_fixed_views(Path("mesh.fbx"), views, "review"))
                render.assert_not_called()
                (views / names[-1]).unlink()
                self.assertFalse(operator.render_fixed_views(Path("mesh.fbx"), views, "review"))
                render.assert_not_called()
            self.assertEqual({name: value for name, value in before.items() if name != names[-1]},
                             {path.name: path.read_bytes() for path in views.iterdir()})

    def test_generated_recipe_paths_inside_the_checkout_are_relative(self):
        from scripts import compile_from_image as operator
        path = operator.ROOT / "work/example/model.glb"
        self.assertEqual("work/example/model.glb", operator.portable_path(path))

    def test_crate_generator_reproduces_the_checked_in_example(self):
        path = ROOT / "examples/crate/make_crate_assets.py"
        spec = importlib.util.spec_from_file_location("crate_fixture", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module.HERE = Path(directory)
            module.main()
            for name in ("crate.obj", "crate.mtl", "crate_basecolor.png"):
                self.assertEqual((path.parent / name).read_bytes(),
                                 (module.HERE / name).read_bytes())

    def test_moved_python_entrypoints_find_the_package_from_an_unrelated_cwd(self):
        import os
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as directory:
            for name in ("build_retopology_review_bundle.py",
                         "canonicalize_feature_fairing_report.py",
                         "canonicalize_paired_qem_report.py"):
                with self.subTest(script=name):
                    # -S prevents an editable site installation from hiding a broken path.
                    # Pillow is needed by the review-plate helper, so retain site packages there.
                    isolated = [] if name.startswith("build_") else ["-S"]
                    result = subprocess.run(
                        [sys.executable, *isolated, str(ROOT / "scripts/experiments" / name), "--help"],
                        cwd=directory, env=env, capture_output=True, text=True, timeout=30)
                    self.assertEqual(0, result.returncode, result.stderr)
