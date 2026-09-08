"""The texture packager's argument contract fails before any Blender work starts."""
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_character_texture.py"
ASSET = "definitely-not-a-workspace-in-this-repo"
COMMON = ["--uv-authority", "nowhere.blend", "--base-color", "a.jpg", "--metallic", "m.jpg",
          "--roughness", "r.jpg", "--profile", "p.json"]


def run(*extra):
    return subprocess.run([sys.executable, str(SCRIPT), ASSET, *COMMON, *extra],
                          capture_output=True, text=True)


class PackageCharacterTextureArgumentTests(unittest.TestCase):
    def test_waiver_needs_both_reason_and_approver(self):
        result = run("--waiver-reason", "island count is a known debt")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("both a reason and a human approver", result.stderr)

    def test_waiver_approver_must_be_a_human(self):
        result = run("--waiver-reason", "island count", "--waiver-approved-by", "pipeline")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must name a human approver", result.stderr)

    def test_target_height_needs_a_reason(self):
        result = run("--target-height", "1.0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--target-height needs --height-reason", result.stderr)

    def test_refuses_an_asset_without_a_ledger(self):
        result = run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no workspace ledger", result.stderr)


if __name__ == "__main__":
    unittest.main()
