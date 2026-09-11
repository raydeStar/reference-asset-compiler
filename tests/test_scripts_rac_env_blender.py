"""The shared Blender command builder never loses the flags that make a crash visible."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rac_env  # noqa: E402


class BlenderCommandTests(unittest.TestCase):
    def test_command_always_carries_exit_code_and_factory_startup(self):
        command = rac_env.blender_command("describe_mesh.py", "in.glb", "out", "report.json",
                                          blender="fake-blender.exe")
        self.assertEqual("fake-blender.exe", command[0])
        self.assertIn("--background", command)
        self.assertIn("--factory-startup", command)
        exit_flag = command.index("--python-exit-code")
        self.assertEqual("1", command[exit_flag + 1])
        self.assertLess(command.index("--python"), command.index("--"))
        self.assertEqual(["in.glb", "out", "report.json"], command[command.index("--") + 1:])
        self.assertTrue(all(isinstance(part, str) for part in command))

    def test_bare_stage_name_resolves_under_scripts_blender(self):
        command = rac_env.blender_command("gate_rig.py", blender="b.exe")
        script = Path(command[command.index("--python") + 1])
        self.assertEqual(ROOT / "scripts" / "blender" / "gate_rig.py", script)
        explicit = ROOT / "scripts" / "blender" / "normalize_prop.py"
        command = rac_env.blender_command(explicit, blender="b.exe")
        self.assertEqual(str(explicit), command[command.index("--python") + 1])

    def test_default_flags_are_present_without_asking(self):
        with patch.object(rac_env, "find_blender", return_value=Path("found.exe")):
            command = rac_env.blender_command("x.py")
        self.assertEqual("found.exe", command[0])
        self.assertIn("--python-exit-code", command)
        self.assertIn("--factory-startup", command)

    def test_run_blender_decodes_utf8_with_replacement(self):
        # A stand-in for Blender: prints UTF-8 that is not valid in the console
        # code page, plus one byte that is not valid UTF-8 at all.
        script = ("import sys\n"
                  "sys.stdout.buffer.write('[RENDER] caf\\u00e9 \\u2713\\n'.encode('utf-8'))\n"
                  "sys.stderr.buffer.write(b'warn \\xff\\n')\n"
                  "sys.exit(3)\n")
        with patch.object(rac_env.subprocess, "run", wraps=subprocess.run) as run:
            code, stdout, stderr = rac_env.run_blender_command(
                [sys.executable, "-c", script], timeout=60)
        self.assertEqual(3, code)
        self.assertIn("[RENDER] café ✓", stdout)
        self.assertIn("warn �", stderr)
        kwargs = run.call_args.kwargs
        self.assertEqual("utf-8", kwargs["encoding"])
        self.assertEqual("replace", kwargs["errors"])

    def test_run_blender_reports_a_timeout_as_a_failed_exit(self):
        code, _stdout, stderr = rac_env.run_blender_command(
            [sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
        self.assertEqual(124, code)
        self.assertIn("killed", stderr)

    def test_run_blender_builds_through_blender_command(self):
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, "ok", "")

        with patch.object(rac_env.subprocess, "run", side_effect=fake_run):
            code, stdout, _ = rac_env.run_blender("gate_rig.py", "a.fbx", blender="b.exe",
                                                  timeout=12)
        self.assertEqual((0, "ok"), (code, stdout))
        self.assertIn("--python-exit-code", seen["command"])
        self.assertIn("--factory-startup", seen["command"])
        self.assertEqual(12, seen["kwargs"]["timeout"])

    def test_child_env_puts_src_first_and_camel_matches_the_old_spellings(self):
        env = rac_env.child_env()
        self.assertTrue(env["PYTHONPATH"].startswith(str(ROOT / "src")))
        self.assertEqual("FieldScoutMale", rac_env.camel("field-scout_male"))
        self.assertEqual("OfficeChairAiV2", rac_env.camel("office-chair-ai-v2"))


if __name__ == "__main__":
    unittest.main()
