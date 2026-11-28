"""Run a command with a time limit that stops everything it started.

`subprocess.run(..., timeout=...)` kills the process it launched and nothing
else. A stage is rarely one process: `paint-sections` is Python, which starts
PowerShell, which starts the painter's Python, which starts another. When the
skiff's section pass ran past its hour, the stage was abandoned and its painter
went on painting section 20 on the GPU with nobody waiting for it. A second run
started then would have shared the card with it.

`run_bounded` takes the same arguments `subprocess.run` is given here and
returns the same result. On a timeout it stops the whole tree first, then
raises `subprocess.TimeoutExpired` as `subprocess.run` would.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


def kill_tree(pid: int) -> None:
    """Stop a process and every process it started, by the root's id."""
    if os.name == "nt":
        # /T follows parent links from the root down, so it must run while the
        # root is alive; the caller kills the root only afterwards.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                       capture_output=True, stdin=subprocess.DEVNULL)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_bounded(command: Sequence[str], *, timeout: float | None = None,
                capture_output: bool = False, gpu_mib: int | None = None, **keywords: Any) -> subprocess.CompletedProcess:
    """`subprocess.run`, except that a timeout stops the whole process tree."""
    if capture_output:
        keywords["stdout"] = subprocess.PIPE
        keywords["stderr"] = subprocess.PIPE
    if gpu_mib is not None:
        command = [sys.executable, str(Path(__file__).with_name("gpu_reservation.py")), str(gpu_mib), *command]
    if os.name != "nt":
        # Its own process group, so one signal reaches every descendant.
        keywords.setdefault("start_new_session", True)
    with subprocess.Popen(list(command), **keywords) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(process.pid)
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(process.args, timeout, output=stdout, stderr=stderr)
        except BaseException:
            kill_tree(process.pid)
            process.kill()
            raise
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
