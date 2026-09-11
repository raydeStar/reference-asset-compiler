import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import workflow_doctor as doctor
import rac_env


class DoctorTests(unittest.TestCase):
    def test_ledger_needs_no_dcc_or_ai_and_never_probes(self):
        with patch.object(rac_env, "find_blender", return_value=None), \
                patch.object(rac_env, "find_unreal_cmd", return_value=None), \
                patch.object(doctor, "probe_addon", side_effect=AssertionError("unneeded")):
            report = doctor.collect("ledger", legacy_root="not-installed")
        self.assertTrue(report["ok"], report["required_missing"])
        self.assertFalse(report["inference_launched"])

    def test_missing_components_fail_text_and_json_with_same_exit(self):
        for as_json in (False, True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = doctor.main(["--profile", "texture", "--legacy-root", "not-installed",
                                    "--blender", "missing.exe"] + (["--json"] if as_json else []))
            self.assertEqual(2, code)
            if as_json:
                report = json.loads(output.getvalue())
                self.assertFalse(report["ok"])
                self.assertIn("hy3d21.python", report["required_missing"])
            else:
                self.assertIn("WORKFLOW_DOCTOR_INCOMPLETE", output.getvalue())

    def test_ue_route_does_not_require_ai_or_historical_graph(self):
        with tempfile.TemporaryDirectory() as raw:
            exe = Path(raw) / "tool.exe"
            exe.touch()
            report = doctor.collect("ue", legacy_root="absent", blender=exe, unreal_cmd=exe)
            self.assertTrue(report["ok"], report["required_missing"])

    def test_pinned_geometry_runners_match_checked_in_files(self):
        report = doctor.collect("ledger")
        for item in report["checks"]:
            if item["id"] in ("hy3d2mv.runner_exact", "hy3d2.runner_exact"):
                self.assertTrue(item["available"], item)

    def test_texture_directories_with_dotted_names_are_directories(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for relative in ("upstream/Hunyuan3D-2.1", "models/hy3d21/Hunyuan3D-2.1"):
                (root / relative).mkdir(parents=True)
            report = doctor.collect("texture", legacy_root=root)
            self.assertNotIn("hy3d21.upstream", report["required_missing"])
            self.assertNotIn("hy3d21.model", report["required_missing"])

    def test_invalid_explicit_environment_does_not_pick_another_install(self):
        with patch.dict(os.environ, {"RAC_BLENDER": "absent.exe", "RAC_UNREAL_CMD": "absent.exe"}):
            self.assertIsNone(rac_env.find_blender(required=False))
            self.assertIsNone(rac_env.find_unreal_cmd(required=False))
            with self.assertRaises(SystemExit):
                rac_env.find_blender()

    def test_help_does_not_discover_blender(self):
        env = {**os.environ, "RAC_BLENDER": "absent.exe", "RAC_UNREAL_CMD": "absent.exe"}
        for script in ("compile_prop.py", "build_production.py", "package_accepted_texture.py"):
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--help"],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("--blender", result.stdout)

    @unittest.skipUnless(shutil.which("pwsh") or shutil.which("powershell"), "PowerShell required")
    def test_powershell_wrapper_preserves_json_and_failure_exit(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        result = subprocess.run([shell, "-NoProfile", "-File", str(ROOT / "scripts/workflow_doctor.ps1"),
                                 "-Python", sys.executable, "-Profile", "texture", "-Json",
                                 "-LegacyRoot", "not-installed", "-Blender", "absent.exe"],
                                capture_output=True, text=True)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertFalse(json.loads(result.stdout)["ok"])

    @unittest.skipUnless(shutil.which("pwsh") or shutil.which("powershell"), "PowerShell required")
    def test_verify_wrapper_preserves_selected_interpreter_exit_and_stderr(self):
        shells = [path for name in ("powershell", "pwsh") if (path := shutil.which(name))]
        with tempfile.TemporaryDirectory() as raw:
            stub = Path(raw) / "selected-python.ps1"
            for code in (0, 7):
                stub.write_text("Write-Output 'selected interpreter'; "
                                "[Console]::Error.WriteLine('ordinary stderr'); "
                                f"exit {code}", encoding="utf-8")
                for shell in shells:
                    with self.subTest(shell=shell, code=code):
                        result = subprocess.run([shell, "-NoProfile", "-File",
                                                 str(ROOT / "scripts/verify.ps1"),
                                                 "-Python", str(stub)],
                                                capture_output=True, text=True)
                        self.assertEqual(code, result.returncode, result.stderr)
                        self.assertIn("selected interpreter", result.stdout)
                        self.assertIn("ordinary stderr", result.stdout + result.stderr)
