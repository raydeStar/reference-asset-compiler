from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler import stages  # noqa: E402
from reference_asset_compiler.stages import (  # noqa: E402
    StageError,
    describe_stages,
    run_stage,
)

# A stand-in for Blender: it takes the same arguments a real stage takes and
# writes the same shape of receipt, so the plumbing can be tested on a machine
# with no Blender and no GPU.
STUB = """
import json, sys
argv = sys.argv[sys.argv.index("--") + 1:]
source, output, report = argv[0], argv[1], argv[2]
mode = {mode!r}
if mode == "fail":
    print("stub refused to export", file=sys.stderr)
    raise SystemExit(3)
if mode != "silent":
    open(output, "wb").write(b"payload")
    json.dump({{"schema": "test.receipt.v1", "payload": output}}, open(report, "w"))
print("stub finished")
"""


class StageRunnerTests(unittest.TestCase):
    def checkout(self, root: Path, mode: str = "ok") -> Path:
        """A checkout carrying one stub stage, registered as a python runner."""
        script = root / "scripts" / "stub_stage.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(STUB.format(mode=mode), encoding="utf-8")
        (root / "source.fbx").write_bytes(b"source")
        return root

    def stub_registry(self) -> dict:
        return {
            "stub": {
                "runner": "python",
                "script": "scripts/stub_stage.py",
                "arguments": ("source", "output", "report"),
                "summary": "A stand-in stage for tests.",
                "produces": "test.receipt.v1",
            }
        }

    def test_a_stage_runs_and_its_receipt_travels_with_the_result(self):
        with tempfile.TemporaryDirectory(prefix="rac-stage-") as raw:
            root = self.checkout(Path(raw))
            with mock.patch.dict(stages.STAGES, self.stub_registry(), clear=True):
                payload = run_stage(
                    "stub", root / "source.fbx", root / "out.glb", root / "report.json",
                    repo_root=root)

            self.assertTrue(payload["ok"], payload)
            self.assertEqual(payload["exit_code"], 0)
            self.assertEqual(payload["stage"], "stub")
            # The receipt comes back inline, so a consumer reads one answer
            # rather than the answer and then a file.
            self.assertEqual(payload["receipt"]["schema"], "test.receipt.v1")
            self.assertTrue((root / "out.glb").is_file())
            self.assertIsInstance(payload["seconds"], float)

    def test_a_failing_stage_carries_its_own_diagnosis(self):
        with tempfile.TemporaryDirectory(prefix="rac-stage-") as raw:
            root = self.checkout(Path(raw), mode="fail")
            with mock.patch.dict(stages.STAGES, self.stub_registry(), clear=True):
                payload = run_stage(
                    "stub", root / "source.fbx", root / "out.glb", root / "report.json",
                    repo_root=root)

            self.assertFalse(payload["ok"])
            self.assertEqual(payload["exit_code"], 3)
            # Hunting a log on another machine is not diagnosis.
            self.assertIn("stub refused to export", " ".join(payload["stderr_tail"]))
            self.assertNotIn("receipt", payload)

    def test_a_stage_that_exits_cleanly_without_a_receipt_is_not_a_success(self):
        with tempfile.TemporaryDirectory(prefix="rac-stage-") as raw:
            root = self.checkout(Path(raw), mode="silent")
            with mock.patch.dict(stages.STAGES, self.stub_registry(), clear=True):
                payload = run_stage(
                    "stub", root / "source.fbx", root / "out.glb", root / "report.json",
                    repo_root=root)

            self.assertFalse(payload["ok"])
            self.assertEqual(payload["exit_code"], 0)
            self.assertIn("wrote no report", payload["error"])

    def test_what_cannot_be_run_is_refused_before_anything_starts(self):
        with tempfile.TemporaryDirectory(prefix="rac-stage-") as raw:
            root = self.checkout(Path(raw))
            with mock.patch.dict(stages.STAGES, self.stub_registry(), clear=True):
                # A caller cannot name a script instead of a stage, even one
                # that really is in the checkout. The registry is the whole
                # point: a name, never a path.
                with self.assertRaises(StageError) as refused_path:
                    run_stage("scripts/stub_stage.py", root / "source.fbx", root / "a",
                              root / "b", repo_root=root)
                self.assertIn("Unknown stage", str(refused_path.exception))
                self.assertFalse((root / "a").exists())
                # A source that does not exist.
                with self.assertRaises(StageError):
                    run_stage("stub", root / "missing.fbx", root / "a", root / "b", repo_root=root)
                # A checkout that does not carry the script.
                with self.assertRaises(StageError) as refused:
                    run_stage("stub", root / "source.fbx", root / "a", root / "b",
                              repo_root=Path(raw) / "elsewhere")
                self.assertIn("checkout", str(refused.exception).lower())

    def test_the_preflight_reports_what_is_missing_and_runs_nothing(self):
        with tempfile.TemporaryDirectory(prefix="rac-stage-") as raw:
            root = self.checkout(Path(raw))
            with mock.patch.dict(stages.STAGES, self.stub_registry(), clear=True):
                available = describe_stages(root, blender=None)
                # The same registry against a checkout that has no scripts.
                empty = describe_stages(Path(raw) / "elsewhere", blender=None)

            self.assertTrue(available["stages"][0]["available"])
            self.assertEqual(available["stages"][0]["missing"], [])
            self.assertFalse(empty["stages"][0]["available"])
            self.assertIn("script", empty["stages"][0]["missing"])
            self.assertFalse((root / "out.glb").exists())

    def test_a_blender_stage_says_so_when_blender_is_not_named(self):
        with tempfile.TemporaryDirectory(prefix="rac-stage-") as raw:
            root = self.checkout(Path(raw))
            registry = self.stub_registry()
            registry["stub"]["runner"] = "blender"
            with mock.patch.dict(stages.STAGES, registry, clear=True):
                with mock.patch.dict("os.environ", {}, clear=False) as environment:
                    environment.pop(stages.BLENDER_ENVIRONMENT, None)
                    described = describe_stages(root, blender=None)
                    self.assertIn("blender", described["stages"][0]["missing"])
                    with self.assertRaises(StageError) as refused:
                        run_stage("stub", root / "source.fbx", root / "a", root / "b",
                                  repo_root=root)
            self.assertIn("Blender", str(refused.exception))

    def test_the_real_registry_names_the_browser_payload_stage(self):
        described = describe_stages(ROOT, blender=None)
        payload = [stage for stage in described["stages"] if stage["stage"] == "browser-payload"]

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["produces"], "reference-asset-compiler.browser-payload.v1")
        # The script it names is really in this checkout.
        self.assertTrue((ROOT / stages.STAGES["browser-payload"]["script"]).is_file())


if __name__ == "__main__":
    unittest.main()
