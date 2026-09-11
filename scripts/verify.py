"""One CPU-only verification sequence for local development and CI."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def checks(wheel_directory: Path):
    return [
        ("contract tests", [sys.executable, "-m", "pytest"]),
        ("lint", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"]),
        ("stage syntax", [sys.executable, "scripts/check_stage_syntax.py"]),
        ("wheel build", [sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
                         "--wheel-dir", str(wheel_directory)]),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel-dir", type=Path, help="Keep the verified wheel in this directory")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="rac-verify-") as raw:
        wheel_directory = Path(raw) / "wheels"
        for label, command in checks(wheel_directory):
            print(f"[VERIFY] {label} ({sys.executable})", flush=True)
            result = subprocess.run(command, cwd=ROOT)
            if result.returncode:
                return result.returncode
        wheels = list(wheel_directory.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Expected exactly one freshly built wheel")
        result = subprocess.run([sys.executable, str(ROOT / "scripts/check_installed_wheel.py"),
                                 str(wheels[0])], cwd=ROOT)
        if result.returncode:
            return result.returncode
        if args.wheel_dir:
            import shutil
            args.wheel_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wheels[0], args.wheel_dir / wheels[0].name)
    print("RAC_VERIFY_OK -- tested, linted, parsed, packed, and unpacked; no inference launched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
