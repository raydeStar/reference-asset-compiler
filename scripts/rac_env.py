"""Find the tools this pipeline shells out to, on a machine that is not mine.

Blender and Unreal are not Python packages. They are large applications
installed wherever the person installing them chose, and every stage here is a
subprocess call to one of them. Hard-coding the two paths that happened to be
right on the machine this was built on is the single thing that makes the repo
unrunnable for anyone else, and it fails in the least helpful way available: a
`FileNotFoundError` on an executable, several stages into a build.

Order of resolution, for each tool:

  1. The environment variable. Explicit, and the only thing a CI runner or a
     different install layout can use.
  2. The usual install locations for this platform.
  3. PATH.

If none of those find it, say which environment variable to set and what was
looked at. A missing tool is a setup problem and should read like one.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

BLENDER_ENV = "RAC_BLENDER"
UNREAL_ENV = "RAC_UNREAL_CMD"
UNREAL_EDITOR_ENV = "RAC_UNREAL_EDITOR"
LEGACY_ENV = "RAC_LEGACY_ROOT"

# Ordered by how likely they are to be right, not alphabetically. The Steam
# install is first because that is what this was developed against.
BLENDER_CANDIDATES = (
    r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/Applications/Blender.app/Contents/MacOS/Blender",
)

UNREAL_GLOB = (
    (r"C:\Program Files\Epic Games", "Engine/Binaries/Win64/UnrealEditor-Cmd.exe"),
)


def _first_existing(candidates):
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def _report(tool, env_var, looked_at):
    lines = [
        "Could not find {0}.".format(tool),
        "",
        "Set {0} to its full path, for example:".format(env_var),
        '    $env:{0} = "C:\\path\\to\\{1}"'.format(env_var, Path(looked_at[0]).name
                                                    if looked_at else "tool.exe"),
        "",
        "Looked at:",
    ]
    lines.extend("    " + str(path) for path in looked_at)
    return "\n".join(lines)


def find_blender(required=True):
    """The Blender executable every geometry and bake stage is run through."""
    looked = []
    override = os.environ.get(BLENDER_ENV)
    if override:
        looked.append(override)
        if Path(override).is_file():
            return Path(override)
    looked.extend(BLENDER_CANDIDATES)
    found = _first_existing([override, *BLENDER_CANDIDATES])
    if found is None:
        on_path = shutil.which("blender")
        looked.append("blender (on PATH)")
        if on_path:
            found = Path(on_path)
    if found is None and required:
        raise SystemExit(_report("Blender", BLENDER_ENV, looked))
    return found


def _unreal_installs():
    """Every UnrealEditor-Cmd under the standard Epic Games root, newest first.

    Sorted by version rather than taken alphabetically, so a machine with both
    UE_5.4 and UE_5.8 does not silently compile against the older one.
    """
    found = []
    for root, suffix in UNREAL_GLOB:
        base = Path(root)
        if not base.is_dir():
            continue
        for entry in sorted(base.glob("UE_*"), reverse=True):
            candidate = entry / suffix
            if candidate.is_file():
                found.append(candidate)
    return found


def find_unreal_cmd(required=True):
    """UnrealEditor-Cmd.exe -- the headless editor used for import and cook."""
    looked = []
    override = os.environ.get(UNREAL_ENV)
    if override:
        looked.append(override)
        if Path(override).is_file():
            return Path(override)
    installs = _unreal_installs()
    looked.extend(str(path) for path in installs)
    if installs:
        return installs[0]
    if required:
        raise SystemExit(_report("UnrealEditor-Cmd.exe", UNREAL_ENV,
                                 looked or [r"C:\Program Files\Epic Games\UE_*"]))
    return None


def find_unreal_editor(required=True):
    """UnrealEditor.exe -- the full editor, needed for real viewport screenshots.

    Separate from the -Cmd build on purpose: `take_high_res_screenshot` needs a
    render thread that actually draws, and the commandlet does not have one.
    """
    override = os.environ.get(UNREAL_EDITOR_ENV)
    if override and Path(override).is_file():
        return Path(override)
    cmd = find_unreal_cmd(required=required)
    if cmd is None:
        return None
    editor = cmd.with_name("UnrealEditor.exe")
    if editor.is_file():
        return editor
    if required:
        raise SystemExit(_report("UnrealEditor.exe", UNREAL_EDITOR_ENV, [str(editor)]))
    return None


def legacy_root(required=False):
    """The read-only studio the authority meshes and textures come from.

    Only recipes that name `${RAC_LEGACY_ROOT}` need this, and none of the
    compiler's own stages do. It is a separate tree of large generated assets
    that is not, and should not be, in this repository.
    """
    value = os.environ.get(LEGACY_ENV)
    if value:
        return Path(value)
    if required:
        raise SystemExit(
            "This recipe reads from the legacy studio, so {0} must be set to "
            "its root.\n"
            "    $env:{0} = \"C:\\path\\to\\blender-reference-studio\"".format(
                LEGACY_ENV))
    return None


def expand(value):
    """Expand ${RAC_LEGACY_ROOT} and friends inside a recipe path.

    Recipes are checked in, and a checked-in absolute path is a path that is
    right on exactly one machine.
    """
    if not isinstance(value, str):
        return value
    if "${" not in value:
        return value
    for name in (LEGACY_ENV, BLENDER_ENV, UNREAL_ENV):
        token = "${" + name + "}"
        if token in value:
            root = os.environ.get(name)
            if not root:
                if name == LEGACY_ENV:
                    legacy_root(required=True)
                raise SystemExit(
                    "A recipe refers to {0} but it is not set.".format(token))
            value = value.replace(token, str(root).replace("\\", "/"))
    return value


def expand_tree(node):
    """Expand every string in a loaded recipe, at any depth."""
    if isinstance(node, dict):
        return {key: expand_tree(item) for key, item in node.items()}
    if isinstance(node, list):
        return [expand_tree(item) for item in node]
    return expand(node)


def _main(argv):
    """Answer one question, for the PowerShell drivers.

    They need the same answer this module gives Python, and two
    implementations of "where is Blender" would drift apart the first time one
    of them was fixed.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", action="store_true")
    parser.add_argument("--unreal-cmd", action="store_true")
    parser.add_argument("--unreal-editor", action="store_true")
    parser.add_argument("--legacy-root", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)

    if args.all or not any(vars(args).values()):
        for label, finder in (("blender", find_blender),
                              ("unreal_cmd", find_unreal_cmd),
                              ("unreal_editor", find_unreal_editor)):
            found = finder(required=False)
            print("{0:<14} {1}".format(label, found or "NOT FOUND"))
        print("{0:<14} {1}".format("legacy_root", legacy_root() or "not set"))
        return 0

    if args.blender:
        print(find_blender())
    if args.unreal_cmd:
        print(find_unreal_cmd())
    if args.unreal_editor:
        print(find_unreal_editor())
    if args.legacy_root:
        print(legacy_root(required=True))
    return 0


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(_main(_sys.argv[1:]))
