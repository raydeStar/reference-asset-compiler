import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler.delegated_review import (
    AUTH_SCHEMA, record_delegated_review, validate_delegated_review,
)
from reference_asset_compiler.workspace import validate_passed_stage_contract


class DelegatedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = self.root / "authorization.json"
        self.auth.write_text(json.dumps({"schema": AUTH_SCHEMA, "authorized_by": "Ayric",
            "reviewer": "codex", "source_sha256": "a" * 64,
            "stages": ["modeling_approval"], "mechanical_gates_waived": False,
            "user_instruction": "Judge the demo yourself; do not stop for my input."}))
        self.frame = self.root / "frame.png"
        self.frame.write_bytes(b"exact evidence")

    def record(self):
        return record_delegated_review(self.root / "review.json", self.auth, "codex",
            "a" * 64, "modeling_approval", [self.frame], "Reviewed all directions.")

    def test_exact_scope_passes_without_claiming_human_review(self):
        paths = self.record()
        validate_delegated_review(paths, "codex", "a" * 64, "modeling_approval")
        self.assertFalse(json.loads(paths[-1].read_text())["human_visual_review"])

    def test_missing_delegation_fails(self):
        with self.assertRaises(ValueError):
            validate_delegated_review([self.frame], "codex", "a" * 64, "modeling_approval")

    def test_wrong_source_or_stage_fails(self):
        paths = self.record()
        for source, stage in [("b" * 64, "modeling_approval"), ("a" * 64, "cook")]:
            with self.assertRaises(ValueError):
                validate_delegated_review(paths, "codex", source, stage)

    def test_changed_or_unreviewed_evidence_fails(self):
        paths = self.record()
        self.frame.write_bytes(b"different")
        with self.assertRaises(ValueError):
            validate_delegated_review(paths, "codex", "a" * 64, "modeling_approval")

    def test_self_authorization_and_waiver_fail(self):
        original = json.loads(self.auth.read_text())
        for change in [{"authorized_by": "codex"}, {"mechanical_gates_waived": True}]:
            self.auth.write_text(json.dumps({**original, **change}))
            with self.assertRaises(ValueError):
                self.record()

    def test_cannot_overwrite_review(self):
        self.record()
        with self.assertRaises(ValueError):
            self.record()

    def test_string_stage_list_is_not_scope_authorization(self):
        auth = json.loads(self.auth.read_text())
        auth["stages"] = "modeling_approval"
        self.auth.write_text(json.dumps(auth))
        with self.assertRaises(ValueError):
            self.record()

    def test_malformed_artifact_rows_fail_closed(self):
        paths = self.record()
        original = json.loads(paths[-1].read_text())
        for rows in [None, [None], [{}], [{"path": [], "sha256": "x"}]]:
            paths[-1].write_text(json.dumps({**original, "reviewed_files": rows}))
            with self.assertRaisesRegex(ValueError, "artifact list is malformed"):
                validate_delegated_review(paths, "codex", "a" * 64, "modeling_approval")

    def test_duplicate_artifact_rows_fail_closed(self):
        paths = self.record()
        receipt = json.loads(paths[-1].read_text())
        receipt["reviewed_files"] *= 2
        paths[-1].write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "repeats an artifact"):
            validate_delegated_review(paths, "codex", "a" * 64, "modeling_approval")

    def test_delegation_does_not_waive_stage_evidence(self):
        paths = self.record()
        with self.assertRaisesRegex(ValueError, "mesh and four neutral views"):
            validate_passed_stage_contract("modeling_approval", paths, "Inspected", "codex",
                                           source_sha256="a" * 64)
