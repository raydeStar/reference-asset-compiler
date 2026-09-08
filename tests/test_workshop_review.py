from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_workshop_review as review


class WorkshopReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job = self.root / "work/sunset-test"
        self.output = self.root / "review.html"
        self.paths = [self.job / "references/primary.png"] + [
            self.job / "modeling/fixed-views" / ("matcap-" + v + ".png") for v in review.VIEWS]
        for path in self.paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test-fixture-only")
        report = self.job / "candidates/hy3d-single-seed42-attempt001/generation.json"
        report.parent.mkdir(parents=True)
        report.write_text(json.dumps({"faces": 10000, "seconds": 1.5}))
        (report.parent / "candidate.glb").write_bytes(b"mesh-test-fixture")

    def tearDown(self):
        self.temp.cleanup()

    def run_review(self, asset="sunset-test"):
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", asset, "--output", str(self.output)
        ]):
            review.main()

    def test_missing_back_view_refuses_review(self):
        self.paths[-1].unlink()
        with self.assertRaisesRegex(ValueError, "Missing fixed views"):
            self.run_review()
        self.assertFalse(self.output.exists())

    def test_existing_review_is_not_overwritten(self):
        self.output.write_text("retained")
        with self.assertRaisesRegex(ValueError, "Existing evidence"):
            self.run_review()
        self.assertEqual("retained", self.output.read_text())

    def test_review_hashes_every_view_without_approval(self):
        self.run_review()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertEqual("awaits recorded modeling review", record["status"])
        self.assertEqual(5, len(record["files"]))
        self.assertTrue(all(item["sha256"] == hashlib.sha256(b"test-fixture-only").hexdigest()
                            for item in record["files"]))
        self.assertNotIn("approved_by", record)

    def test_asset_path_escape_refused(self):
        with self.assertRaisesRegex(ValueError, "asset id"):
            self.run_review("sunset-../../elsewhere")

    def test_supplemental_top_view_is_bound_when_present(self):
        top = self.job / "modeling/surface-views/matcap-top.png"
        top.parent.mkdir(parents=True)
        top.write_bytes(b"top-view-test-fixture")
        self.run_review()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertEqual(6, len(record["files"]))
        self.assertEqual(hashlib.sha256(top.read_bytes()).hexdigest(), record["files"][-1]["sha256"])

    def test_rejection_is_retained_with_candidate_hash(self):
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output),
            "--reject", "sunset-test=Torn leaves and floating fragments"
        ]):
            review.main()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertTrue(record["status"].startswith("rejected by agent:"))
        self.assertEqual(hashlib.sha256(b"mesh-test-fixture").hexdigest(), record["candidate"]["sha256"])
        self.assertNotIn("approved_by", record)

    def test_unknown_rejection_asset_refused(self):
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--reject", "sunset-other=Broken"
        ]):
            with self.assertRaisesRegex(ValueError, "reviewed asset"):
                review.main()

    def test_topology_review_binds_both_rows_and_reduced_mesh(self):
        reduced = self.job / "retopology/operator-attempt001"
        (reduced / "fixed-views").mkdir(parents=True)
        for view in review.VIEWS:
            (reduced / "fixed-views" / ("matcap-" + view + ".png")).write_bytes(b"reduced-view")
        (reduced / "voxel-qem-candidate.glb").write_bytes(b"reduced-mesh")
        (reduced / "reduction-report.json").write_text(json.dumps({
            "output": {"triangles": 18000}, "status": "mechanical_pass"}))
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "retopology"
        ]):
            review.main()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertEqual("retopology", record["review_stage"])
        self.assertEqual(10, len(record["files"]))
        self.assertEqual(hashlib.sha256(b"reduced-mesh").hexdigest(), record["candidate"]["sha256"])
        self.assertIn("awaits recorded retopology review", record["status"])
        self.assertIn("Approved front", self.output.read_text(encoding="utf-8"))
        self.assertIn("Reduced front", self.output.read_text(encoding="utf-8"))

    def texture_fixture(self):
        prod = self.job / "prod-v2"
        (prod / "turn").mkdir(parents=True)
        for pass_name in ("beauty", "albedo"):
            for view in review.VIEWS:
                (prod / "turn" / (pass_name + "-" + view + ".png")).write_bytes(b"texture-view")
        for name in ("mesh.fbx", "base.png", "rough.png", "metal.png", "gate-tex.json", "texture-payload-binding.json"):
            (prod / name).write_bytes(b"payload-fixture")
        (prod / "retopo.json").write_text(json.dumps({"output_fbx": "mesh.fbx", "resolution": 2048,
            "ok": False, "baked": {"BaseColor": "base.png", "Roughness": "rough.png", "Metallic": "metal.png"}}))
        return prod

    def test_texture_review_binds_maps_and_keeps_failed_gate_visible(self):
        self.texture_fixture()
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture"
        ]):
            review.main()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertEqual("texture", record["review_stage"])
        self.assertEqual(10, len(record["files"]))
        self.assertEqual(6, len(record["payload_files"]))
        self.assertIn("FAILED", record["status"])
        self.assertNotIn("approved_by", record)

    def test_texture_review_requires_unlit_back(self):
        prod = self.texture_fixture()
        (prod / "turn/albedo-back.png").unlink()
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture"
        ]):
            with self.assertRaisesRegex(ValueError, "Missing fixed views"):
                review.main()

    def test_face_review_binds_all_six_closeups(self):
        prod = self.texture_fixture()
        faces = prod / "face-review-v001"
        faces.mkdir()
        for mode in ("beauty", "albedo"):
            for view in ("front", "three-quarter", "side"):
                (faces / (mode + "-face-" + view + ".png")).write_bytes(b"face-fixture")
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture"
        ]):
            review.main()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertEqual(16, len(record["files"]))
        self.assertTrue(all(row["sha256"] == hashlib.sha256(b"face-fixture").hexdigest()
                            for row in record["files"][-6:]))

    def test_partial_face_review_is_refused(self):
        prod = self.texture_fixture()
        (prod / "face-review-v001").mkdir()
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture"
        ]):
            with self.assertRaisesRegex(ValueError, "Incomplete face evidence"):
                review.main()
        self.assertFalse(self.output.exists())

    def test_opposite_face_bundle_is_complete_and_hash_bound(self):
        prod = self.texture_fixture()
        faces = prod / "face-review-v001"
        faces.mkdir()
        for mode in ("beauty", "albedo"):
            for view in ("front", "three-quarter", "side", "opposite-three-quarter", "opposite-side"):
                (faces / (mode + "-face-" + view + ".png")).write_bytes(b"bilateral-fixture")
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture"
        ]):
            review.main()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertEqual(20, len(record["files"]))
        self.assertTrue(all(row["sha256"] == hashlib.sha256(b"bilateral-fixture").hexdigest()
                            for row in record["files"][-4:]))

    def test_partial_opposite_face_bundle_is_refused(self):
        prod = self.texture_fixture()
        faces = prod / "face-review-v001"
        faces.mkdir()
        for mode in ("beauty", "albedo"):
            for view in ("front", "three-quarter", "side"):
                (faces / (mode + "-face-" + view + ".png")).write_bytes(b"fixture")
        (faces / "beauty-face-opposite-side.png").write_bytes(b"fixture")
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture"
        ]):
            with self.assertRaisesRegex(ValueError, "Incomplete opposite-face evidence"):
                review.main()
        self.assertFalse(self.output.exists())

    def test_texture_review_binds_selected_package(self):
        prod = self.texture_fixture()
        prod.rename(self.job / "prod-v3")
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture",
            "--package", "sunset-test=prod-v3"
        ]):
            review.main()
        record = json.loads(self.output.with_suffix(".json").read_text())[0]
        self.assertEqual("prod-v3", record["texture_package"])
        self.assertIn("prod-v3", record["candidate"]["path"])

    def test_texture_package_path_escape_refused(self):
        with patch.object(review, "ROOT", self.root), patch("sys.argv", [
            "review", "sunset-test", "--output", str(self.output), "--stage", "texture",
            "--package", "sunset-test=prod-v3/../../outside"
        ]):
            with self.assertRaisesRegex(ValueError, "local prod"):
                review.main()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
