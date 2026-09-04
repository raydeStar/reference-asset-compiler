from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.crank_from_image import generation_request, write_passthrough_retopology
from reference_asset_compiler.io import sha256_file


class CrankFromImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.job = self.root / "brass-lantern"
        self.source = self.job / "references" / "primary.png"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"approved-image")
        self.args = Namespace(
            asset_id="brass-lantern",
            seed=42,
            attempt=1,
            steps=40,
            octree_resolution=512,
            chunks=20000,
        )
        self.intake = {
            "source": {
                "path": "references/primary.png",
                "sha256": sha256_file(self.source),
            }
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_generation_request_uses_the_immutable_single_image(self) -> None:
        request, candidate, receipt = generation_request(self.args, self.job, self.intake)
        payload = json.loads(request.read_text(encoding="utf-8"))
        self.assertEqual("single_view", payload["mode"])
        self.assertEqual(["primary"], [item["view"] for item in payload["inputs"]])
        self.assertEqual(self.intake["source"]["sha256"], payload["inputs"][0]["sha256"])
        self.assertEqual(candidate.parent / "candidate-receipt.json", receipt)

    def test_generation_request_refuses_changed_attempt_settings(self) -> None:
        generation_request(self.args, self.job, self.intake)
        self.args.steps = 30
        with self.assertRaisesRegex(ValueError, "different settings"):
            generation_request(self.args, self.job, self.intake)

    def test_under_budget_passthrough_is_a_hash_bound_mechanical_report(self) -> None:
        cleaned = self.root / "cleaned.blend"
        cleaned.write_bytes(b"cleaned-mesh")
        report = self.root / "retopology.json"
        write_passthrough_retopology(
            cleaned,
            {"roundtrip": {"boundary_edges": 0, "non_manifold_edges": 0}},
            {"vertices": 8000, "tris": 12000},
            report,
        )
        payload = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual("mechanical_pass", payload["status"])
        self.assertEqual(sha256_file(cleaned), payload["output"]["sha256"])
        self.assertEqual(12000, payload["output"]["triangles"])


if __name__ == "__main__":
    unittest.main()
