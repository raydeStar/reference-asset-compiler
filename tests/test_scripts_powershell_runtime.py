"""Run the 5.1 drivers with a harmless stand-in executable, never inference."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell required")
class PowerShellRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        stub = self.root / "blender_stub.py"
        stub.write_text(
            "import json, os, sys\nfrom pathlib import Path\n"
            "sys.stderr.write('ordinary Blender progress warning\\n')\n"
            "if os.environ.get('RAC_TEST_FAIL'): sys.exit(5)\n"
            "out = Path(sys.argv[-1]); out.mkdir(parents=True)\n"
            "(out / 'neck-transfer.json').write_text(json.dumps({'ok': True, "
            "'before_fingerprint': 'same', 'after_fingerprint': 'same'}))\n",
            encoding="utf-8")
        self.blender = self.root / "fake-blender.cmd"
        self.blender.write_text('@echo off\n"{0}" "{1}" %*\n'.format(sys.executable, stub),
                                encoding="utf-8")
        self.recipe = self.root / "recipe.json"
        self.recipe.write_text("{}", encoding="utf-8")

    def run_neck(self, fail=False):
        wrapper = self.root / "invoke.ps1"
        wrapper.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            "& $env:RAC_TEST_SCRIPT -Recipe $env:RAC_TEST_RECIPE "
            "-Output $env:RAC_TEST_OUTPUT -Blender $env:RAC_TEST_BLENDER "
            "-CompilerPython $env:RAC_TEST_PYTHON -SkipReview *> $env:RAC_TEST_LOG\n"
            "exit $LASTEXITCODE\n", encoding="utf-8")
        env = {**os.environ, "RAC_TEST_SCRIPT": str(ROOT / "scripts/run_neck_transition.ps1"),
               "RAC_TEST_RECIPE": str(self.recipe), "RAC_TEST_OUTPUT": str(self.root / "attempt"),
               "RAC_TEST_BLENDER": str(self.blender), "RAC_TEST_PYTHON": sys.executable,
               "RAC_TEST_LOG": str(self.root / "launcher.log")}
        if fail:
            env["RAC_TEST_FAIL"] = "1"
        return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                               "-File", str(wrapper)], env=env, capture_output=True,
                              text=True, timeout=40)

    def test_neck_driver_accepts_absolute_paths_and_survives_redirected_stderr(self):
        result = self.run_neck()
        log = (self.root / "launcher.log").read_text(encoding="utf-16")
        self.assertEqual(0, result.returncode, result.stderr + log)
        self.assertIn("RAC_NECK_CANDIDATE_READY", log)
        self.assertTrue(json.loads((self.root / "attempt/neck-transfer.json").read_text())["ok"])

    def test_neck_driver_rejects_a_nonzero_exit(self):
        result = self.run_neck(fail=True)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse((self.root / "attempt/neck-transfer.json").exists())

    def test_character_compile_keeps_previous_scratch_and_isolates_a_failed_attempt(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("compile_asset.ps1", "resolve_python.ps1"):
            shutil.copy2(ROOT / "scripts" / name, scripts / name)
        profile = self.root / "profiles/skeletons/test.json"
        profile.parent.mkdir(parents=True)
        profile.write_text("{}", encoding="utf-8")
        self.recipe.write_text(json.dumps({"asset_id": "test-character", "skeleton_profile": "test"}))
        retained = self.root / "work/test-character/staged/old.fbx"
        retained.parent.mkdir(parents=True)
        retained.write_bytes(b"old evidence")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(scripts / "compile_asset.ps1"), "-Recipe", str(self.recipe),
             "-Blender", str(self.blender), "-CompilerPython", sys.executable, "-SkipRender"],
            env={**os.environ, "RAC_TEST_FAIL": "1"}, capture_output=True, text=True, timeout=40)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(b"old evidence", retained.read_bytes())
        attempts = list((retained.parent.parent / "compile-attempts").iterdir())
        self.assertEqual(1, len(attempts))
        self.assertTrue((attempts[0] / "logs/normalize_ue5.py.stderr.log").is_file())
        self.assertFalse((self.root / "out/test-character").exists())

    def test_shared_gpu_guard_fails_closed_without_querying_a_real_gpu(self):
        harness = r"""
function nvidia-smi {
    $global:LASTEXITCODE = 0
    if ($args[0] -like '--query-compute*') { return '123,synthetic-owner,1' }
    if ($env:RAC_TEST_MODE -eq 'multi') { return @('50000,0', '50000,0') }
    if ($env:RAC_TEST_MODE -eq 'low') { return '100,99' }
    return '50000,0'
}
function Get-CimInstance {
    if ($env:RAC_TEST_MODE -eq 'busy') {
        return [pscustomobject]@{CommandLine='python C:\ComfyUI\main.py'}
    }
}
function Invoke-RestMethod {
    return [pscustomobject]@{queue_running=@('synthetic-job'); queue_pending=@()}
}
try {
    & $env:RAC_TEST_GUARD -MinimumFreeVramMiB 21504 | ConvertTo-Json -Depth 3
} catch { Write-Output $_.Exception.Message; exit 2 }
"""
        for mode, expected, message in (
            ("idle", 0, '"free_mib":  50000'),
            ("low", 2, "100 MiB free"),
            ("multi", 2, "unambiguous GPU state"),
            ("busy", 2, "queue is busy"),
        ):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", harness],
                    env={**os.environ, "RAC_TEST_MODE": mode,
                         "RAC_TEST_GUARD": str(ROOT / "scripts/assert_gpu_available.ps1")},
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(expected, result.returncode, result.stderr + result.stdout)
                self.assertIn(message, result.stdout)
