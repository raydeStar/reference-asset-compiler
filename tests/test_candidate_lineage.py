from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.compile_from_image import validate_candidate_lineage


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CandidateLineageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.image = self.root / "authority.png"
        self.candidate = self.root / "candidate.glb"
        self.report = self.root / "candidate.json"
        self.image.write_bytes(b"approved-image")
        self.candidate.write_bytes(b"ai-generated-mesh")
        self.write_report()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_report(self, **changes) -> None:
        report = {
            "schema": "reference-asset-compiler.geometry-candidate.v1",
            "asset_id": "test-prop",
            "adapter": "pixal3d",
            "ok": True,
            "candidate_sha256": digest(self.candidate),
            "image_sha256": digest(self.image),
            "status": "candidate -- not approved, not an asset",
        }
        report.update(changes)
        self.report.write_text(json.dumps(report), encoding="utf-8")

    def test_image_conditioned_ai_lineage_passes(self) -> None:
        result = validate_candidate_lineage(self.candidate, self.image, self.report)
        self.assertEqual("pixal3d", result["adapter"])

    def test_missing_report_rejects_manual_candidate(self) -> None:
        self.report.unlink()
        with self.assertRaisesRegex(ValueError, "lineage report is missing"):
            validate_candidate_lineage(self.candidate, self.image, self.report)

    def test_reference_hash_drift_fails(self) -> None:
        self.image.write_bytes(b"different-image")
        with self.assertRaisesRegex(ValueError, "approved image hash"):
            validate_candidate_lineage(self.candidate, self.image, self.report)

    def test_non_geometry_adapter_fails(self) -> None:
        self.write_report(adapter="auto_rig_pro")
        with self.assertRaisesRegex(ValueError, "not registered"):
            validate_candidate_lineage(self.candidate, self.image, self.report)


if __name__ == "__main__":
    unittest.main()
