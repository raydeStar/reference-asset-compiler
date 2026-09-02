from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from reference_asset_compiler.cleanup import (  # noqa: E402
    record_cleanup_receipt,
    validate_cleanup_input,
)
from reference_asset_compiler.io import sha256_file  # noqa: E402
from reference_asset_compiler.workspace import create_workspace, promote_stage  # noqa: E402
from support import modeling_evidence, promote_generated  # noqa: E402

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text())


class CleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "source.png"
        source.write_bytes(b"source")
        self.job = create_workspace(
            self.root / "work", source, "Hero", "humanoid", "required", REGISTRY,
            skeleton_profile="ue5_manny")
        self.candidate, _ = promote_generated(self.job)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def approve_modeling(self) -> None:
        views = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = self.job / "modeling" / name
            path.write_bytes(name.encode())
            views.append(path)
        promote_stage(
            self.job, "modeling_approval",
            modeling_evidence(self.job, self.candidate, views),
            "Approved.", "Ayric")

    def write_result(self, roundtrip_matches: bool = True) -> tuple[Path, Path]:
        output = self.job / "cleanup" / "cleaned.blend"
        report = self.job / "cleanup" / "topology.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"native-cleanup")
        before = {"faces": 1000, "invalid_vertices": 0,
                  "degenerate_faces": 1, "loose_vertices": 0}
        after = {"faces": 999, "invalid_vertices": 0,
                 "degenerate_faces": 0, "loose_vertices": 0}
        roundtrip = dict(after)
        if not roundtrip_matches:
            roundtrip["faces"] = 998
        report.write_text(json.dumps({
            "schema": "reference-asset-compiler.semantic-cleanup-topology.v1",
            "source_sha256": sha256_file(self.candidate),
            "output_sha256": sha256_file(output),
            "operations": ["remove_degenerate_faces", "recalculate_normals"],
            "before": before,
            "after": after,
            "roundtrip": roundtrip,
            "bbox_max_drift_m": 0.0,
            "ok": True,
        }), encoding="utf-8")
        return output, report

    def test_cleanup_input_requires_modeling_approval(self) -> None:
        with self.assertRaisesRegex(ValueError, "modeling_approval"):
            validate_cleanup_input(self.job, self.candidate)

    def test_cleanup_receipt_binds_approved_input_and_native_roundtrip(self) -> None:
        self.approve_modeling()
        output, report = self.write_result()
        receipt = record_cleanup_receipt(self.job, self.candidate, output, report)
        self.assertEqual(sha256_file(self.candidate), receipt["input_mesh_sha256"])
        self.assertEqual(sha256_file(output), receipt["output_mesh_sha256"])

    def test_cleanup_rejects_serialization_topology_drift(self) -> None:
        self.approve_modeling()
        output, report = self.write_result(roundtrip_matches=False)
        with self.assertRaisesRegex(ValueError, "serialization"):
            record_cleanup_receipt(self.job, self.candidate, output, report)


if __name__ == "__main__":
    unittest.main()
