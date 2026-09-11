"""Every launcher parses under Windows PowerShell and writes receipts without a BOM."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "scripts").rglob("*.ps1"))

# The directory travels in an environment variable: with -Command, anything
# after the script text is appended to it rather than delivered as $args.
PARSE = r"""
$results = @()
foreach ($path in Get-ChildItem -LiteralPath $env:RAC_PARSE_DIR -Filter *.ps1 -Recurse) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($path.FullName, [ref]$tokens, [ref]$errors) | Out-Null
    $results += [pscustomobject]@{
        name = $path.FullName
        errors = @($errors | ForEach-Object { "{0}: {1}" -f $_.Extent.StartLineNumber, $_.Message })
    }
}
ConvertTo-Json -Depth 4 -InputObject @($results)
"""


class PowerShellLauncherTests(unittest.TestCase):
    def test_there_are_launchers_to_check(self):
        self.assertGreater(len(SCRIPTS), 10)

    @unittest.skipUnless(shutil.which("powershell"), "powershell.exe is required")
    def test_every_launcher_parses_without_errors(self):
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", PARSE],
            env={**os.environ, "RAC_PARSE_DIR": str(ROOT / "scripts")},
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        self.assertEqual(0, result.returncode, result.stderr)
        reports = json.loads(result.stdout)
        if isinstance(reports, dict):
            reports = [reports]
        failed = {item["name"]: item["errors"] for item in reports if item["errors"]}
        self.assertEqual({}, failed)
        self.assertEqual({path.resolve() for path in SCRIPTS},
                         {Path(item["name"]).resolve() for item in reports})

    def test_no_launcher_writes_a_bom_or_uses_a_core_only_switch(self):
        offenders = {}
        for path in SCRIPTS:
            text = path.read_text(encoding="utf-8")
            problems = [needle for needle in ("Set-Content -Encoding utf8", "-AsHashtable")
                        if needle in text]
            if problems:
                offenders[path.name] = problems
        self.assertEqual({}, offenders)

    def test_launchers_carry_no_bom(self):
        for path in SCRIPTS:
            with self.subTest(script=path.name):
                self.assertFalse(path.read_bytes().startswith(b"\xef\xbb\xbf"),
                                 "file starts with a BOM")

    def test_no_launcher_calls_a_bare_interpreter(self):
        offenders = []
        for path in SCRIPTS:
            if path.name == "resolve_python.ps1":
                continue
            text = path.read_text(encoding="utf-8")
            if "& python " in text or "& py -3" in text:
                offenders.append(path.name)
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
