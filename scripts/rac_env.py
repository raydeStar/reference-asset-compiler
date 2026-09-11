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
import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BLENDER_SCRIPTS = REPO_ROOT / "scripts" / "blender"

# Short Blender steps -- describe, gate, export regions, fixed-view renders --
# finish in minutes. A step that has not returned after this long is hung, and
# a hung Blender that nothing ever waits out is a build that never reports.
# Inference and long bakes pass timeout=None and are deliberately unbounded.
BLENDER_STEP_TIMEOUT = 30 * 60

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
        if required:
            raise SystemExit(_report("Blender", BLENDER_ENV, looked))
        return None
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
        if required:
            raise SystemExit(_report("UnrealEditor-Cmd.exe", UNREAL_ENV, looked))
        return None
    installs = _unreal_installs()
    looked.extend(str(path) for path in installs)
    if installs:
        return installs[0]
    on_path = shutil.which("UnrealEditor-Cmd") or shutil.which("UnrealEditor-Cmd.exe")
    if on_path:
        return Path(on_path)
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
    if override:
        if Path(override).is_file():
            return Path(override)
        if required:
            raise SystemExit(_report("UnrealEditor.exe", UNREAL_EDITOR_ENV, [override]))
        return None
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


def child_env(studio_root=None):
    """Environment for a compiler subprocess: src/ on PYTHONPATH, one studio root.

    Every driver used to carry its own copy of this. `pip install -e .` is one
    more step between a person and their first compiled asset, and the tests
    already run without it.
    """
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + (os.pathsep + existing if existing else "")
    if studio_root is not None:
        env[LEGACY_ENV] = str(studio_root)
    return env


def camel(asset_id):
    """field-scout_male -> FieldScoutMale; the name UE material and mesh slugs use."""
    return "".join(part.capitalize() for part in re.split(r"[-_]+", asset_id) if part)


def require_available_gpu(minimum_free_mib):
    """Use the same ownership/queue gate as the direct Windows AI launchers."""
    import json
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise RuntimeError("PowerShell is required to verify GPU ownership on this route")
    result = subprocess.run([
        shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
        str(REPO_ROOT / "scripts/assert_gpu_available.ps1"),
        "-MinimumFreeVramMiB", str(minimum_free_mib), "-Json",
    ], capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    if result.returncode:
        raise RuntimeError("GPU preflight refused inference: " + result.stderr.strip())
    return json.loads(result.stdout)


def blender_script_path(script):
    """A bare stage name resolves under scripts/blender; a path is used as given."""
    candidate = Path(script)
    if candidate.suffix == ".py" and len(candidate.parts) == 1:
        return BLENDER_SCRIPTS / candidate.name
    return candidate


def blender_command(script, *args, blender=None, factory_startup=True, background=True):
    """The argv for one Blender stage, with the two flags a stage must never lose.

    `--python-exit-code 1` is what makes a stage that raised exit non-zero.
    Without it Blender exits 0 having done nothing, and the driver reads the
    report the PREVIOUS run left behind. `--factory-startup` keeps a user's
    add-ons and start-up file out of a pipeline that has to be repeatable on a
    different machine.
    """
    executable = Path(blender) if blender else find_blender()
    command = [str(executable)]
    if background:
        command.append("--background")
    if factory_startup:
        command.append("--factory-startup")
    command += ["--python-exit-code", "1", "--python", str(blender_script_path(script)), "--"]
    command += [str(value) for value in args]
    return command


def run_blender_command(command, timeout=None, capture=True, cwd=None, env=None):
    """Run an already-built Blender argv; return (returncode, stdout, stderr).

    Output is decoded as UTF-8 with replacement: Blender prints file names and
    material names verbatim, and one non-ASCII byte in a warning must not turn a
    finished bake into a UnicodeDecodeError in the driver. A timeout kills the
    child and reports as a failure (exit 124) rather than propagating, so every
    caller's "non-zero means failed" check covers it.
    """
    kwargs = {"cwd": str(cwd or REPO_ROOT), "env": env}
    if capture:
        kwargs.update(capture_output=True, encoding="utf-8", errors="replace")
    try:
        done = subprocess.run([str(part) for part in command], timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as expired:
        def _text(value):
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            return str(value)
        return (124, _text(expired.stdout),
                _text(expired.stderr) + "\nBlender exceeded {0} s and was killed".format(timeout))
    return done.returncode, done.stdout or "", done.stderr or ""


def run_blender(script, *args, blender=None, timeout=None, capture=True, cwd=None, env=None,
                factory_startup=True, background=True):
    """Build and run one Blender stage; return (returncode, stdout, stderr)."""
    command = blender_command(script, *args, blender=blender,
                              factory_startup=factory_startup, background=background)
    return run_blender_command(command, timeout=timeout, capture=capture, cwd=cwd, env=env)


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
