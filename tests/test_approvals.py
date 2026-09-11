from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from reference_asset_compiler.approvals import (  # noqa: E402
    MODELING_VIEW_NAMES,
    texture_evidence_paths,
    validate_generated_candidate,
    validate_modeling_approval,
    validate_texture_approval,
)
from reference_asset_compiler.workspace import create_workspace, promote_stage  # noqa: E402
from support import (  # noqa: E402
    modeling_evidence,
    promote_cleanup,
    promote_generated,
    promote_retopology,
    promote_unwrap_and_bake,
    texture_payload_evidence,
)

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text())


class ApprovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "source.png"
        source.write_bytes(b"source")
        self.job = create_workspace(
            self.root / "work", source, "Test Prop", "static_prop", "static", REGISTRY
        )
        self.candidate, self.report = promote_generated(self.job)
        self.views = self.job / "modeling"
        for name in MODELING_VIEW_NAMES:
            (self.views / name).write_bytes(name.encode())

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def approve(self, evidence: list[Path] | None = None) -> None:
        default_evidence = modeling_evidence(
            self.job, self.candidate, [self.views / name for name in MODELING_VIEW_NAMES])
        promote_stage(
            self.job,
            "modeling_approval",
            evidence or default_evidence,
            "Approved in neutral fixed views.",
            "Ayric",
        )

    def test_generated_candidate_is_bound_to_ledger(self) -> None:
        record = validate_generated_candidate(self.job, self.candidate, self.report)
        self.assertEqual("passed", record["status"])

    def test_modeling_approval_requires_candidate_and_four_views(self) -> None:
        self.approve()
        record = validate_modeling_approval(self.job, self.candidate, self.views)
        self.assertEqual("Ayric", record["approved_by"])

    def test_missing_side_view_fails(self) -> None:
        evidence = [
            path for path in modeling_evidence(
                self.job, self.candidate, [self.views / name for name in MODELING_VIEW_NAMES])
            if path.name != "matcap-side.png"
        ]
        with self.assertRaisesRegex(ValueError, "matcap-side.png"):
            self.approve(evidence)

    def test_changed_evidence_fails_workspace_audit(self) -> None:
        self.approve()
        (self.views / "matcap-back.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "workspace audit failed"):
            validate_modeling_approval(self.job, self.candidate, self.views)

    def prepare_texture_gate(self) -> tuple[Path, dict]:
        self.approve()
        cleaned = promote_cleanup(self.job, self.candidate)
        retopology = promote_retopology(self.job, cleaned)
        production, retopo = promote_unwrap_and_bake(self.job, retopology)
        texture_payload_evidence(production, retopo)
        return production, retopo

    def test_texture_approval_requires_payload_maps_and_lit_views(self) -> None:
        production, retopo = self.prepare_texture_gate()
        promote_stage(
            self.job,
            "texture_approval",
            texture_evidence_paths(production, retopo),
            "Approved PBR response.",
            "Ayric",
        )
        record = validate_texture_approval(self.job, production, retopo)
        self.assertEqual("Ayric", record["approved_by"])

    def test_texture_approval_missing_lit_side_fails(self) -> None:
        production, retopo = self.prepare_texture_gate()
        evidence = [
            path for path in texture_evidence_paths(production, retopo)
            if path.name != "beauty-side.png"
        ]
        with self.assertRaisesRegex(ValueError, "beauty-side.png"):
            promote_stage(self.job, "texture_approval", evidence, "Approved.", "Ayric")


if __name__ == "__main__":
    unittest.main()
