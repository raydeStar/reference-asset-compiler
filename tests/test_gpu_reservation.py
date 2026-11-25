"""Exercise GPU admission with sleeping processes only, including WSL on an opted-in host."""
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

from reference_asset_compiler.pixal import linux_path


GUARD = Path(__file__).resolve().parents[1] / "src/reference_asset_compiler/gpu_reservation.py"
HOLD = "import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch(); time.sleep(float(sys.argv[2]))"


def wait_for(path, process):
    deadline = time.monotonic() + 25
    while not path.exists() and time.monotonic() < deadline:
        assert process.poll() is None, process.returncode
        time.sleep(0.05)
    assert path.exists()


@pytest.mark.skipif(os.name == "nt" and not os.environ.get("RAC_TEST_WSL_GPU_LOCK"),
                    reason="Windows/WSL ownership test requires the Pixal distro")
def test_only_one_worker_enters_even_after_the_native_owner_dies(tmp_path):
    lock = "/tmp/rac-test-" + uuid.uuid4().hex + ".lock"
    env = {**os.environ, "RAC_GPU_LOCK_PATH": lock}
    first, second = tmp_path / "first", tmp_path / "second"
    native = [sys.executable, str(GUARD), "0", sys.executable, "-c", HOLD, str(first), "90"]
    if os.name == "nt":
        # Actual WSL worker uses the same Linux flock as a Windows paint stage.
        foreign = ["wsl.exe", "-d", os.environ.get("RAC_WSL_DISTRO", "Ubuntu-22.04"), "--",
                   "env", "RAC_GPU_LOCK_PATH=" + lock, "python3", linux_path(GUARD), "0",
                   "python3", "-c", HOLD, linux_path(second), "0"]
    else:
        foreign = [sys.executable, str(GUARD), "0", sys.executable, "-c", HOLD, str(second), "0"]
    with subprocess.Popen(native, env=env) as owner:
        try:
            wait_for(first, owner)
            with subprocess.Popen(foreign, env=env) as contender:
                try:
                    time.sleep(1)
                    assert contender.poll() is None and not second.exists()
                    owner.kill()
                    owner.wait(timeout=10)
                    assert contender.wait(timeout=25) == 0
                    assert second.exists()
                finally:
                    if contender.poll() is None:
                        contender.kill()
        finally:
            if owner.poll() is None:
                owner.kill()


@pytest.mark.skipif(os.name != "nt" or not os.environ.get("RAC_TEST_WSL_GPU_LOCK"),
                    reason="requires Windows and the Pixal distro")
def test_linux_owner_keeps_windows_painter_waiting_until_linux_exits(tmp_path):
    key = "/tmp/rac-test-" + uuid.uuid4().hex + ".lock"
    env = {**os.environ, "RAC_GPU_LOCK_PATH": key}
    first, release, second = (tmp_path / name for name in ("first", "release", "second"))
    linux = ["wsl.exe", "-d", os.environ.get("RAC_WSL_DISTRO", "Ubuntu-22.04"), "--",
             "env", "RAC_GPU_LOCK_PATH=" + key, "python3", linux_path(GUARD), "0",
             "python3", "-c", "import pathlib,sys,time; pathlib.Path(sys.argv[1]).touch()\n"
             "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(.05)",
             linux_path(first), linux_path(release)]
    native = [sys.executable, str(GUARD), "0", sys.executable, "-c", HOLD, str(second), "0"]
    with subprocess.Popen(linux) as owner:
        try:
            wait_for(first, owner)
            with subprocess.Popen(native, env=env) as contender:
                try:
                    time.sleep(1)
                    assert contender.poll() is None and not second.exists()
                    release.touch()
                    assert owner.wait(timeout=10) == contender.wait(timeout=25) == 0
                    assert second.exists()
                finally:
                    if contender.poll() is None:
                        contender.kill()
        finally:
            release.touch()
