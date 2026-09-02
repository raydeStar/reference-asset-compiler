"""Parse every pipeline stage, without importing it.

The Blender and Unreal stages import `bpy` and `unreal`, which exist only
inside those applications. They cannot be imported on a CI runner, or in a
plain Python shell, so nothing that only imports modules will ever look at
them -- and they are most of this pipeline.

They can still be parsed. That catches the whole class of error that otherwise
surfaces as Blender exiting 0 having done nothing, several minutes into a
build, because Blender reports a script that raised the same way it reports one
that succeeded.

Usage:
  python scripts/check_stage_syntax.py [path ...]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(paths):
    failures = []
    checked = 0
    for base in paths:
        for path in sorted(Path(base).rglob("*.py")):
            checked += 1
            try:
                ast.parse(path.read_text(encoding="utf-8"), str(path))
            except SyntaxError as error:
                failures.append("{0}:{1}: {2}".format(
                    path, error.lineno or 0, error.msg))
    return checked, failures


def main(argv):
    paths = argv or [str(ROOT / "scripts")]
    checked, failures = check(paths)
    for failure in failures:
        print(failure)
    print("{0} stage files parsed, {1} failed".format(checked, len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
