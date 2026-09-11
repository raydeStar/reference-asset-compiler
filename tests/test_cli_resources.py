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
            self.assertEqual(1, cli.main(["audit", "missing-job"]))

    def test_audit_exit_codes_separate_failed_audit_from_usage_error(self):
        with patch.object(cli, "audit_workspace", return_value={"ok": True}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, cli.main(["audit", "job"]))
        with patch.object(cli, "audit_workspace", side_effect=ValueError("broken")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, cli.main(["audit", "job"]))
        with patch.object(cli, "audit_cohort", return_value={"ok": False, "production_ready": False}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(1, cli.main(["cohort-audit", "cohort.json"]))
        with patch.object(cli, "audit_cohort", side_effect=FileNotFoundError("cohort.json")), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(2, cli.main(["cohort-audit", "cohort.json"]))

    def test_receipt_and_preflight_commands_expose_their_new_flags(self):
        parser = cli.build_parser()
        args = parser.parse_args([
            "retopology-receipt", "job", "in.blend", "out.blend", "report.json",
            "--view", "matcap-front.png", "--approved-by", "codex", "--note", "Reviewed.",
            "--authorization", "delegation.json", "--deformation-topology-reviewed"])
        self.assertEqual("delegation.json", str(args.authorization))
        self.assertTrue(args.deformation_topology_reviewed)
        args = parser.parse_args(["geometry-preflight", "request.json", "--legacy-root", "studio",
                                  "--workspace-root", "jobs"])
        self.assertEqual("jobs", str(args.workspace_root))
        self.assertTrue(parser.parse_args(
            ["promote", "job", "cook", "--note", "n", "--approved-by", "a", "--replace"]).replace)

    def test_installed_geometry_preflight_explains_checkout_requirement(self):
        output = io.StringIO()
        with patch.object(cli, "checkout_root", return_value=None), \
                contextlib.redirect_stderr(output):
            self.assertEqual(2, cli.main(["geometry-preflight", "request.json",
                                          "--legacy-root", "studio"]))
        self.assertIn("--repo-root", output.getvalue())
