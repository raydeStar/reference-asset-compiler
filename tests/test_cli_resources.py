import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler import cli
from reference_asset_compiler.resources import load_registry


class CliResourceTests(unittest.TestCase):
    def test_checkout_registry_is_canonical(self):
        self.assertTrue(load_registry()["adapters"])

    def test_registry_failure_uses_normal_error_channel(self):
        output = io.StringIO()
        with patch.object(cli, "load_registry", side_effect=FileNotFoundError("missing registry")), \
                contextlib.redirect_stderr(output):
            self.assertEqual(2, cli.main(["plan", "unused.json"]))
        self.assertIn("RAC_ERROR", output.getvalue())
        self.assertNotIn("Traceback", output.getvalue())

    def test_audit_does_not_need_registry(self):
        with patch.object(cli, "load_registry", side_effect=AssertionError("unneeded")), \
                patch.object(cli, "audit_workspace", return_value={"ok": False}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(2, cli.main(["audit", "missing-job"]))

    def test_installed_geometry_preflight_explains_checkout_requirement(self):
        output = io.StringIO()
        with patch.object(cli, "checkout_root", return_value=None), \
                contextlib.redirect_stderr(output):
            self.assertEqual(2, cli.main(["geometry-preflight", "request.json",
                                          "--legacy-root", "studio"]))
        self.assertIn("--repo-root", output.getvalue())
