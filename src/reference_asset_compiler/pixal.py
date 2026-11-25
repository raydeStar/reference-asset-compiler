"""Where Pixal3D runs: its checkout and Python inside a Linux environment (WSL on Windows).

Pixal3D (TencentARC) needs CUDA libraries that are built for Linux, so on a
Windows workstation it runs in a WSL distribution, and on Linux in place. Each
piece can be named through the environment:

- RAC_PIXAL3D_ROOT: the Pixal3D checkout, as a Linux path;
- RAC_PIXAL3D_PYTHON: the Python of its environment, as a Linux path;
- RAC_WSL_DISTRO: the WSL distribution that holds them (Windows only).

The defaults are the original workstation's and exist nowhere else.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path, PureWindowsPath

DEFAULT_ROOT = "/home/raydestar/ai/Pixal3D"
DEFAULT_PYTHON = "/home/raydestar/ai/envs/pixal3d/bin/python"
DEFAULT_DISTRO = "Ubuntu-22.04"


def pixal_paths(root: str | None = None, python: str | None = None, distro: str | None = None) -> dict[str, str]:
    return {
        "root": root or os.environ.get("RAC_PIXAL3D_ROOT") or DEFAULT_ROOT,
        "python": python or os.environ.get("RAC_PIXAL3D_PYTHON") or DEFAULT_PYTHON,
        "distro": distro or os.environ.get("RAC_WSL_DISTRO") or DEFAULT_DISTRO,
    }


def pixal_missing() -> list[str]:
    """What the stage listing reports missing, without starting WSL (a listing must stay fast).

    On Windows that is only whether WSL itself is installed; a run checks the
    checkout and the Python inside it, and refuses in plain words if either is
    absent. On Linux both are checked directly.
    """
    paths = pixal_paths()
    if sys.platform == "win32":
        return [] if shutil.which("wsl.exe") else ["wsl"]
    missing = []
    if not Path(paths["root"]).is_dir():
        missing.append("pixal3d-checkout")
    if not Path(paths["python"]).is_file():
        missing.append("pixal3d-python")
    return missing


def linux_path(path: str | Path) -> str:
    """A Windows path as WSL sees it (C:\\a\\b -> /mnt/c/a/b); a POSIX path is returned as it is."""
    text = str(path)
    match = re.match(r"^([A-Za-z]):[\\/](.*)$", text)
    if not match:
        return text.replace("\\", "/")
    drive, rest = match.groups()
    return "/mnt/{0}/{1}".format(drive.lower(), PureWindowsPath(rest).as_posix())


def pixal_command(arguments: list[str], paths: dict[str, str], on_windows: bool | None = None) -> list[str]:
    """The command that runs `python <arguments>` inside Pixal3D's checkout and environment.

    The environment's own site-packages only: a WSL login can put ~/.local
    ahead of it, which once selected an old Transformers build.
    """
    on_windows = sys.platform == "win32" if on_windows is None else on_windows
    quoted = " ".join("'{0}'".format(str(item).replace("'", "'\\''")) for item in [paths["python"], *arguments])
    script = "export PYTHONNOUSERSITE=1 PIXAL3D_ROOT='{0}'; cd \"$PIXAL3D_ROOT\" && exec {1}".format(
        paths["root"].replace("'", "'\\''"), quoted)
    if on_windows:
        return ["wsl.exe", "-d", paths["distro"], "--", "bash", "-c", script]
    return ["bash", "-c", script]
