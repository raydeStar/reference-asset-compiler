"""A stage that runs out of time stops everything it started, not only itself."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.processes import run_bounded  # noqa: E402

# A parent that starts a long-lived child, as paint-sections starts PowerShell
# and PowerShell starts the painter, then outlives its time limit itself.
PARENT = """
import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
open(sys.argv[1], "w").write(str(child.pid))
time.sleep(120)
"""


def alive(pid: int) -> bool:
    if os.name == "nt":
        listed = subprocess.run(["tasklist", "/FI", "PID eq {0}".format(pid), "/NH"],
                                capture_output=True, text=True, errors="replace")
        return str(pid) in listed.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A killed child waits as a zombie until it is reaped; it holds nothing.
    try:
        with open("/proc/{0}/status".format(pid)) as status:
            return "zombie" not in status.read()
    except OSError:
        return True


class BoundedRunTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.parent = self.root / "parent.py"
        self.parent.write_text(PARENT, encoding="utf-8")
        self.pid_file = self.root / "child.pid"

    def tearDown(self):
        if self.pid_file.is_file():
            pid = int(self.pid_file.read_text() or 0)
            if pid and alive(pid):
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                else:
                    os.kill(pid, 9)

    def test_a_timeout_stops_the_child_the_command_started(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            run_bounded([sys.executable, str(self.parent), str(self.pid_file)], capture_output=True,
                        text=True, stdin=subprocess.DEVNULL, timeout=4)
        pid = int(self.pid_file.read_text())
        deadline = time.monotonic() + 10
        while alive(pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        self.assertFalse(alive(pid), "the child of a timed-out command was left running")

    def test_a_command_that_finishes_answers_as_subprocess_run_does(self):
        finished = run_bounded([sys.executable, "-c", "import sys; print('done'); sys.exit(3)"],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        self.assertEqual(finished.returncode, 3)
        self.assertEqual(finished.stdout.strip(), "done")
        self.assertEqual(finished.stderr, "")


if __name__ == "__main__":
    unittest.main()
