from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from reference_asset_compiler.io import sha256_file  # noqa: E402
from reference_asset_compiler.retopology import record_retopology_receipt  # noqa: E402
from reference_asset_compiler.workspace import create_workspace, promote_stage  # noqa: E402
from support import modeling_evidence, promote_cleanup, promote_generated  # noqa: E402

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text())


class RetopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = self.root / "source.png"
        source.write_bytes(b"source")
        self.job = create_workspace(
            self.root / "work", source, "Hero", "humanoid", "required", REGISTRY,
            skeleton_profile="ue5_manny")
        candidate, _ = promote_generated(self.job)
        views = []
        for name in ("matcap-front.png", "matcap-three-quarter.png",
                     "matcap-side.png", "matcap-back.png"):
            path = self.job / "modeling" / name
            path.write_bytes(name.encode())
            views.append(path)
        promote_stage(
            self.job, "modeling_approval", modeling_evidence(self.job, candidate, views),
            "Approved.", "Ayric")
        self.cleaned = promote_cleanup(self.job, candidate)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def result(
        self, quad_fraction: float = 0.9
    ) -> tuple[Path, Path, list[Path], list[Path]]:
        output = self.job / "retopology" / "runtime.blend"
        report = self.job / "retopology" / "report.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"runtime-retopology")
        report.write_text(json.dumps({
            "schema": "reference-asset-compiler.production-retopology-candidate.v1",
            "status": "mechanical_pass",
            "source": {"sha256": sha256_file(self.cleaned)},
            "output": {
                "sha256": sha256_file(output), "vertices": 10000, "triangles": 19000,
                "quad_fraction": quad_fraction, "boundary_edges": 0,
                "nonmanifold_edges": 0,
            },
            "failures": [],
        }), encoding="utf-8")
        views = []
        for index, name in enumerate(("matcap-front.png", "matcap-three-quarter.png",
                                      "matcap-side.png", "matcap-back.png"), start=1):
            path = output.parent / "fixed-views" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (640, 640), (index * 40, index * 30, index * 20)).save(path)
            views.append(path)
        topology_views = []
        for index, name in enumerate(("wireframe-front.png", "wireframe-three-quarter.png",
                                      "wireframe-side.png", "wireframe-back.png"), start=1):
            path = output.parent / "topology-views" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (640, 640), (index * 25, index * 35, index * 45)).save(path)
            topology_views.append(path)
        return output, report, views, topology_views

    def test_receipt_binds_cleanup_budget_views_and_human_review(self) -> None:
        output, report, views, topology_views = self.result()
        receipt = record_retopology_receipt(
            self.job, self.cleaned, output, report, views, "Ayric", "Loops approved.",
            topology_views)
        receipt_path = Path(receipt["receipt"])
        promote_stage(
            self.job, "production_retopology",
            [self.cleaned, output, report, receipt_path, *views, *topology_views],
            "Loops approved.", "Ayric")
        self.assertEqual("passed", json.loads((self.job / "state.json").read_text())
                         ["stages"]["production_retopology"]["status"])

    def test_humanoid_all_triangle_candidate_is_rejected(self) -> None:
        output, report, views, topology_views = self.result(quad_fraction=0.0)
        with self.assertRaisesRegex(ValueError, "80% quads"):
            record_retopology_receipt(
                self.job, self.cleaned, output, report, views, "Ayric", "Review.",
                topology_views)

    def test_automation_cannot_approve_visible_retopology_gate(self) -> None:
        output, report, views, topology_views = self.result()
        with self.assertRaisesRegex(ValueError, "human reviewer"):
            record_retopology_receipt(
                self.job, self.cleaned, output, report, views, "codex", "Review.",
                topology_views)

    def test_ledger_rejects_receipt_that_contradicts_its_report(self) -> None:
        output, report, views, topology_views = self.result()
        payload = record_retopology_receipt(
            self.job, self.cleaned, output, report, views, "Ayric", "Loops approved.",
            topology_views)
        receipt = Path(payload["receipt"])
        report_payload = json.loads(report.read_text())
        report_payload["output"]["triangles"] = 18000
        report.write_text(json.dumps(report_payload), encoding="utf-8")
        receipt_payload = json.loads(receipt.read_text())
        receipt_payload["report_sha256"] = sha256_file(report)
        receipt.write_text(json.dumps(receipt_payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "contradicts"):
            promote_stage(
                self.job, "production_retopology",
                [self.cleaned, output, report, receipt, *views, *topology_views],
                "Loops approved.", "Ayric")

    def test_articulated_receipt_requires_wireframe_views(self) -> None:
        output, report, views, _topology_views = self.result()
        with self.assertRaisesRegex(ValueError, "four wireframe views"):
            record_retopology_receipt(
                self.job, self.cleaned, output, report, views, "Ayric", "Review.")


if __name__ == "__main__":
    unittest.main()
