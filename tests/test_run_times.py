"""`rac time-to-model`: a model's stages laid out front to back from their receipts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.run_times import models_under, render, stage_runs, summarise  # noqa: E402


def receipt(folder: Path, name: str, stage: str, seconds: float, started: str | None = None,
            finished: str | None = None, ok: bool = True, mtime: float | None = None, banner: str = "") -> Path:
    payload = {"ok": ok, "schema": "reference-asset-compiler.stage-run.v1", "stage": stage,
               "seconds": seconds, "report": str(folder / (name + ".json"))}
    if started:
        payload["started_utc"] = started
    if finished:
        payload["finished_utc"] = finished
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(banner + json.dumps(payload, indent=2), encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class TimeToModelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_front_to_back_counts_gaps_and_leaves_out_pauses(self):
        model = self.root / "PR-01"
        receipt(model, "geometry.log", "geometry", 40, "2026-11-26T10:00:00+00:00", "2026-11-26T10:00:40+00:00")
        receipt(model, "uv.log", "uv-unwrap", 30, "2026-11-26T10:01:40+00:00", "2026-11-26T10:02:10+00:00")
        # Overnight, then the paint: a pause, not time the model took.
        receipt(model, "painted.log", "texture", 150, "2026-11-26T20:00:00+00:00", "2026-11-26T20:02:30+00:00")
        # Something that is not a receipt is passed over.
        (model / "painted.json").write_text(json.dumps({"schema": "other"}), encoding="utf-8")
        summary = summarise(model)
        self.assertEqual([run["stage"] for run in summary["runs"]], ["geometry", "uv-unwrap", "texture"])
        self.assertEqual(summary["seconds"]["in_stages"], 220.0)
        self.assertEqual(summary["seconds"]["between_stages"], 60.0)
        self.assertEqual(summary["seconds"]["front_to_back"], 280.0)
        self.assertEqual(len(summary["pauses"]), 1)
        self.assertEqual(summary["timed_by_file_time"], 0)
        self.assertEqual(next(iter(summary["by_stage"])), "texture")

    def test_overlapping_stages_count_once(self):
        model = self.root / "M"
        receipt(model, "a.log", "remesh", 100, "2026-11-26T10:00:00+00:00", "2026-11-26T10:01:40+00:00")
        receipt(model, "b.log", "uv-unwrap", 50, "2026-11-26T10:01:00+00:00", "2026-11-26T10:01:50+00:00")
        summary = summarise(model)
        self.assertEqual(summary["seconds"]["in_stages"], 110.0)
        self.assertEqual(summary["seconds"]["sum_of_stages"], 150.0)

    def test_older_receipts_are_timed_by_their_file(self):
        model = self.root / "old"
        receipt(model, "a.log", "geometry", 40, mtime=1_800_000_040)
        receipt(model, "b.log", "remesh", 20, mtime=1_800_000_100, banner="launcher banner\n")
        runs = stage_runs(model)
        self.assertEqual([run["stage"] for run in runs], ["geometry", "remesh"])
        self.assertTrue(all(run["timed_by"] == "file time" for run in runs))
        summary = summarise(model)
        self.assertEqual(summary["seconds"]["between_stages"], 40.0)
        self.assertIn("timed by their file's time", render([summary]))

    def test_each_finds_the_models_under_a_folder(self):
        receipt(self.root / "one", "g.log", "geometry", 10, "2026-11-26T10:00:00+00:00", "2026-11-26T10:00:10+00:00")
        receipt(self.root / "two" / "seed41", "g.log", "geometry", 10,
                "2026-11-26T11:00:00+00:00", "2026-11-26T11:00:10+00:00")
        (self.root / "empty").mkdir()
        self.assertEqual([path.name for path in models_under(self.root)], ["one", "two"])

    def test_the_command_prints_and_writes(self):
        model = self.root / "PR-02"
        receipt(model, "g.log", "geometry", 10, "2026-11-26T10:00:00+00:00", "2026-11-26T10:00:10+00:00")
        receipt(model, "t.log", "texture", 100, "2026-11-26T10:00:20+00:00", "2026-11-26T10:02:00+00:00",
                ok=False)
        written = self.root / "times.json"
        environment = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
        finished = subprocess.run([sys.executable, "-m", "reference_asset_compiler.cli", "time-to-model",
                                   str(model), "--output", str(written)],
                                  capture_output=True, text=True, env=environment)
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("front to back 2m 00s", finished.stdout)
        self.assertIn("(failed)", finished.stdout)
        payload = json.loads(written.read_text(encoding="utf-8"))
        self.assertEqual(payload["models"][0]["failed_runs"], 1)


if __name__ == "__main__":
    unittest.main()
