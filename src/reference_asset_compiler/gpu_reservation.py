"""One reservation for direct Pixal workers and RAC stages launched by a studio.

Windows byte locks and Linux locks on /mnt/c do not exclude each other. When
the Pixal distro is installed, Windows takes the very same Linux flock via a
small WSL helper. Its input pipe stays open for the lifetime of the worker.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def lock_path() -> str:
    return os.environ.get("RAC_GPU_LOCK_PATH", "/tmp/reference-asset-compiler-gpu0.lock")


@contextlib.contextmanager
def linux_reservation():
    import fcntl
    with open(lock_path(), "a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[GPU] Waiting for the workstation GPU reservation", file=sys.stderr, flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield handle


def pixal_distro():
    if not shutil.which("wsl.exe"):
        return None
    distro = os.environ.get("RAC_WSL_DISTRO", "Ubuntu-22.04")
    listed = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True, timeout=20)
    if listed.returncode:
        raise RuntimeError("Cannot check WSL GPU ownership: " + listed.stdout.decode("utf-16le", "replace").strip())
    names = listed.stdout.decode("utf-16le").lstrip("\ufeff").splitlines()
    return distro if distro in (name.strip() for name in names) else None


@contextlib.contextmanager
def windows_reservation():
    import msvcrt
    # Native-only installations also serialize across independent RAC processes.
    native_path = Path(tempfile.gettempdir()) / "reference-asset-compiler-gpu0.lock"
    with native_path.open("a+b") as native:
        native.seek(0)
        waiting = False
        while True:
            try:
                msvcrt.locking(native.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except PermissionError:
                if not waiting:
                    print("[GPU] Waiting for the workstation GPU reservation", file=sys.stderr, flush=True)
                    waiting = True
                time.sleep(0.25)
        distro = pixal_distro()
        if not distro:
            yield
            return
        command = ["wsl.exe", "-d", distro, "--", "flock", "-x", lock_path(),
                   "sh", "-c", 'printf "reserved\\n"; cat >/dev/null']
        with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as holder:
            try:
                print("[GPU] Reserving the workstation GPU", file=sys.stderr, flush=True)
                if holder.stdout.readline().strip() != b"reserved":
                    raise RuntimeError("WSL did not grant the workstation GPU reservation")
                yield
            finally:
                holder.stdin.close()
                holder.wait()


def contain_windows_worker():
    """An abrupt queue-worker exit also terminates its native descendants."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class Basic(ctypes.Structure):
        _fields_ = [("process_cpu", ctypes.c_int64), ("job_cpu", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                    ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6), ("memory", ctypes.c_size_t * 4)]

    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(job, wintypes.HANDLE(-1)):
        raise ctypes.WinError(ctypes.get_last_error())
    # The OS closes the sole, non-inheritable handle on process exit.
    return job


def run_windows_tree(command):
    """The program may exit while a painter it spawned is still working."""
    import ctypes
    from ctypes import wintypes
    job = contain_windows_worker()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                wintypes.DWORD, ctypes.c_void_p]

    class Accounting(ctypes.Structure):
        _fields_ = [("times", ctypes.c_int64 * 4), ("pagefaults", wintypes.DWORD),
                    ("total", wintypes.DWORD), ("active", wintypes.DWORD), ("terminated", wintypes.DWORD)]

    code = subprocess.call(command)
    info = Accounting()
    while kernel.QueryInformationJobObject(job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
        if info.active == 1:  # this supervisor alone
            return code
        time.sleep(0.1)
    raise ctypes.WinError(ctypes.get_last_error())


def wait_for_memory(required_mib):
    if not required_mib:
        return
    announced = False
    while True:
        reading = subprocess.run(["nvidia-smi", "-i", "0", "--query-gpu=memory.free",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True,
                                 check=True, timeout=15)
        if int(reading.stdout.strip()) >= required_mib:
            return
        if not announced:
            print(f"[GPU] Waiting for {required_mib} MiB of free VRAM", file=sys.stderr, flush=True)
            announced = True
        time.sleep(2)


def main(argv):
    if argv[0] == "--run-tree":
        return run_windows_tree(argv[1:])
    required = int(argv[0])
    command = argv[1:]
    if os.name == "nt":
        contain_windows_worker()
        with windows_reservation():
            wait_for_memory(required)
            return subprocess.call([sys.executable, __file__, "--run-tree", *command])
    with linux_reservation() as lock:
        wait_for_memory(required)
        os.set_inheritable(lock.fileno(), True)
        os.execvp(command[0], command)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[GPU] FAILED: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
