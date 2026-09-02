from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.geometry_request import validate_geometry_request
from reference_asset_compiler.io import sha256_file


class GeometryRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.legacy = self.root / "legacy"
        self.repo = self.root / "repo"
        self.workspace = self.repo / "work" / "fox"
        self.legacy.mkdir()
        (self.workspace / "references").mkdir(parents=True)
        (self.workspace / "candidates").mkdir()
        self.authority = self.legacy / "authority.png"
        self.authority.write_bytes(b"authority")
        self.workspace_authority = self.workspace / "references" / "primary.png"
        self.workspace_authority.write_bytes(b"authority")
        authority_hash = sha256_file(self.authority)
        (self.workspace / "intake.json").write_text(json.dumps({
            "asset_id": "fox",
            "source": {
                "path": "references/primary.png",
                "sha256": authority_hash,
            },
        }), encoding="utf-8")
        self.views = {}
        for view in ("front", "left", "back"):
            path = self.legacy / (view + ".png")
            path.write_bytes(view.encode())
            self.views[view] = path
        self.derivation = self.legacy / "derivation.json"
        self.derivation.write_text(json.dumps({
            "source": str(self.authority),
            "source_sha256": authority_hash,
            "views": [
                {
                    "view": view,
                    "output": str(path),
                    "sha256": sha256_file(path),
                }
                for view, path in self.views.items()
            ],
        }), encoding="utf-8")
        self.request = self.repo / "request.json"
        self.write_request()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_request(self, output: str = "${RAC_REPO_ROOT}/work/fox/candidates/attempt-001") -> None:
        self.request.write_text(json.dumps({
            "schema": "reference-asset-compiler.hy3d-geometry-request.v1",
            "asset_id": "fox",
            "workspace": "${RAC_REPO_ROOT}/work/fox",
            "source_authority": {
                "path": str(self.authority),
                "sha256": sha256_file(self.authority),
            },
            "derivation_report": {
                "path": str(self.derivation),
                "sha256": sha256_file(self.derivation),
            },
            "inputs": [
                {"view": view, "path": str(path), "sha256": sha256_file(path)}
                for view, path in self.views.items()
            ],
            "parameters": {
                "seed": 42,
                "steps": 40,
                "octree_resolution": 512,
                "chunks": 20000,
            },
            "output_directory": output,
        }), encoding="utf-8")

    def test_valid_request_is_launch_ready_without_launching(self) -> None:
        result = validate_geometry_request(self.request, self.legacy, self.repo)
        self.assertTrue(result["launch_ready"])
        self.assertFalse(result["inference_launched"])
        self.assertEqual(["front", "left", "back"], [row["view"] for row in result["inputs"]])

    def test_source_hash_drift_fails(self) -> None:
        self.authority.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "source authority hash changed"):
            validate_geometry_request(self.request, self.legacy, self.repo)

    def test_existing_attempt_directory_refuses_retry(self) -> None:
        (self.workspace / "candidates" / "attempt-001").mkdir()
        with self.assertRaisesRegex(FileExistsError, "do not retry"):
            validate_geometry_request(self.request, self.legacy, self.repo)

    def test_derivation_view_hash_drift_fails(self) -> None:
        payload = json.loads(self.derivation.read_text(encoding="utf-8"))
        payload["views"][0]["sha256"] = "0" * 64
        self.derivation.write_text(json.dumps(payload), encoding="utf-8")
        self.write_request()
        with self.assertRaisesRegex(ValueError, "not bound to view: front"):
            validate_geometry_request(self.request, self.legacy, self.repo)

    def test_output_cannot_escape_workspace(self) -> None:
        self.write_request("${RAC_REPO_ROOT}/work/elsewhere")
        with self.assertRaisesRegex(ValueError, "escapes workspace candidates"):
            validate_geometry_request(self.request, self.legacy, self.repo)


    def write_single_view_request(self, input_path: Path, input_hash: str,
                                  derivation: bool = False) -> None:
        payload = {
            "schema": "reference-asset-compiler.hy3d-geometry-request.v1",
            "mode": "single_view",
            "asset_id": "fox",
            "workspace": "${RAC_REPO_ROOT}/work/fox",
            "source_authority": {
                "path": str(self.authority),
                "sha256": sha256_file(self.authority),
            },
            "inputs": [{"view": "primary", "path": str(input_path), "sha256": input_hash}],
            "parameters": {"seed": 7, "steps": 30, "octree_resolution": 384, "chunks": 20000},
            "output_directory": "${RAC_REPO_ROOT}/work/fox/candidates/single-001",
        }
        if derivation:
            payload["derivation_report"] = {
                "path": str(self.derivation), "sha256": sha256_file(self.derivation)}
        self.request.write_text(json.dumps(payload), encoding="utf-8")

    def test_single_view_request_conditions_on_the_source_itself(self) -> None:
        self.write_single_view_request(self.authority, sha256_file(self.authority))
        result = validate_geometry_request(self.request, self.legacy, self.repo)
        self.assertEqual("single_view", result["mode"])
        self.assertIsNone(result["derivation_report"])
        self.assertEqual(["primary"], [row["view"] for row in result["inputs"]])
        self.assertTrue(result["launch_ready"])

    def test_single_view_input_must_be_the_authority(self) -> None:
        other = self.views["front"]
        self.write_single_view_request(other, sha256_file(other))
        with self.assertRaisesRegex(ValueError, "must be the workspace source authority"):
            validate_geometry_request(self.request, self.legacy, self.repo)

    def test_single_view_request_rejects_a_derivation_report(self) -> None:
        self.write_single_view_request(self.authority, sha256_file(self.authority), derivation=True)
        with self.assertRaisesRegex(ValueError, "omit derivation_report"):
            validate_geometry_request(self.request, self.legacy, self.repo)


if __name__ == "__main__":
    unittest.main()
