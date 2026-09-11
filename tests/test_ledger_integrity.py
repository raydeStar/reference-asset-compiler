"""Corrupted ledgers must not turn missing work into production approval."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from reference_asset_compiler.io import read_json, write_json
from reference_asset_compiler.resources import load_registry
from reference_asset_compiler.workspace import audit_workspace, create_workspace, promote_stage


class LedgerIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reference = self.root / "ref.png"
        self.reference.write_bytes(b"test-reference")

    def job(self, kind="static_prop"):
        return create_workspace(self.root, self.reference, kind, kind, "auto", load_registry())

    def assert_bad(self, job):
        before = {p.name: p.read_bytes() for p in job.glob("*.json")}
        result = audit_workspace(job)
        self.assertFalse(result["ok"], result)
        self.assertFalse(result["production_ready"])
        self.assertTrue(result["failures"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in job.glob("*.json")})

    def test_missing_every_pending_stage_does_not_approve_static_or_humanoid(self):
        for kind in ("static_prop", "humanoid"):
            with self.subTest(kind=kind):
                job = self.job(kind)
                state = read_json(job / "state.json")
                for mode in ("only-passed", "empty"):
                    broken = copy.deepcopy(state)
                    broken["stages"] = ({k: v for k, v in state["stages"].items()
                                         if v["status"] == "passed"} if mode == "only-passed" else {})
                    write_json(job / "state.json", broken)
                    self.assert_bad(job)

    def test_each_required_gate_is_checked_even_when_routing_is_also_truncated(self):
        job = self.job()
        state, routing = read_json(job / "state.json"), read_json(job / "routing.json")
        for stage in state["stages"]:
            with self.subTest(stage=stage):
                broken, route = copy.deepcopy(state), copy.deepcopy(routing)
                del broken["stages"][stage]
                route["stages"].remove(stage)
                write_json(job / "state.json", broken)
                write_json(job / "routing.json", route)
                self.assert_bad(job)

    def test_key_order_is_not_pipeline_order(self):
        job = self.job()
        state = read_json(job / "state.json")
        state["stages"] = dict(reversed(list(state["stages"].items())))
        write_json(job / "state.json", state)
        self.assertTrue(audit_workspace(job)["ok"])
        with self.assertRaisesRegex(ValueError, "earlier stages"):
            promote_stage(job, "cook", [], "not done", "Reviewer")

    def test_reordered_keys_cannot_hide_out_of_order_pass(self):
        job = self.job()
        state = read_json(job / "state.json")
        state["stages"]["static_validation"]["status"] = "passed"
        state["stages"] = dict(sorted(state["stages"].items(),
                                      key=lambda pair: pair[1]["status"] != "passed"))
        write_json(job / "state.json", state)
        self.assert_bad(job)

    def test_bad_shapes_identities_and_records_fail_without_tracebacks_or_writes(self):
        job = self.job()
        originals = {p.name: read_json(p) for p in job.glob("*.json")}
        cases = [
            ("state.json", {"stages": []}),
            ("state.json", {"asset_id": "another-asset"}),
            ("state.json", {"schema": "unknown"}),
            ("routing.json", {"articulated": True}),
            ("routing.json", {"geometry_candidates": [None]}),
            ("intake.json", {"budgets": {"maximum_vertices": True}}),
            ("intake.json", {"source": {"path": "ref.png"}}),
        ]
        for file, changes in cases:
            with self.subTest(file=file, changes=changes):
                for name, data in originals.items():
                    write_json(job / name, data)
                write_json(job / file, {**originals[file], **changes})
                self.assert_bad(job)
        for record in (None, [], {"status": []}, {"status": "passed", "evidence": [None]}):
            for name, data in originals.items():
                write_json(job / name, data)
            state = copy.deepcopy(originals["state.json"])
            state["stages"]["intake"] = record
            write_json(job / "state.json", state)
            self.assert_bad(job)
        for data in ("{", "[]", "null"):
            (job / "state.json").write_text(data)
            self.assert_bad(job)

    def test_unexpected_stage_blocks_audit_and_promotion(self):
        job = self.job()
        state = read_json(job / "state.json")
        state["stages"]["skip-everything"] = {"status": "passed", "evidence": []}
        write_json(job / "state.json", state)
        self.assert_bad(job)
        with self.assertRaisesRegex(ValueError, "unexpected"):
            promote_stage(job, "generate_candidates", [], "working", "test", "in_progress")

    def test_atomic_write_failure_preserves_previous_ledger(self):
        target = self.root / "ledger.json"
        write_json(target, {"generation": 1})
        original = target.read_bytes()
        with patch("reference_asset_compiler.io.os.replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                write_json(target, {"generation": 2})
        self.assertEqual(original, target.read_bytes())
        self.assertEqual([], list(self.root.glob(".rac-*")))
        self.assertEqual({"generation": 1}, json.loads(original))
