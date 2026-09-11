"""The operator driver refuses dead-end attempts and mismatched texture packages."""
from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts import crank_from_image as crank
from reference_asset_compiler.io import sha256_file, write_json

CANDIDATE = "candidates/hy3d-single-seed42-attempt001/candidate.glb"


class AttemptGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.job = Path(self.temporary.name) / "brass-lantern"
        self.job.mkdir()
        self.args = Namespace(asset_id="brass-lantern", seed=42, attempt=1)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def ledger(self, status, evidence=()):
        write_json(self.job / "state.json", {"stages": {"generate_candidates": {
            "status": status,
            "evidence": [{"path": path, "sha256": "0" * 64, "bytes": 1} for path in evidence],
        }}})

    def test_pending_ledger_allows_any_attempt(self):
        self.ledger("pending")
        self.args.attempt = 2
        crank.require_ledgered_attempt(self.args, self.job)

    def test_the_ledgered_attempt_may_resume(self):
        self.ledger("passed", [CANDIDATE, "candidates/hy3d-single-seed42-attempt001/candidate-receipt.json"])
        crank.require_ledgered_attempt(self.args, self.job)

    def test_a_second_attempt_after_a_pass_is_refused_with_a_new_asset_id_message(self):
        self.ledger("passed", [CANDIDATE])
        self.args.attempt = 2
        with self.assertRaisesRegex(ValueError, "new asset id") as caught:
            crank.require_ledgered_attempt(self.args, self.job)
        self.assertIn(CANDIDATE, str(caught.exception))
        self.assertFalse((self.job / "requests").exists(), "no request file may be written")

    def test_a_different_seed_after_a_pass_is_refused(self):
        self.ledger("passed", [CANDIDATE])
        self.args.seed = 7
        with self.assertRaises(ValueError):
            crank.require_ledgered_attempt(self.args, self.job)

    def test_main_exits_two_on_the_guard(self):
        self.ledger("passed", [CANDIDATE])
        image = self.job / "primary.png"
        image.write_bytes(b"approved-image")
        args = Namespace(
            asset_id="brass-lantern", image=image, kind="static_prop", height=0.5,
            height_reason="measured", skeleton_profile=None, studio_root=None, seed=42,
            attempt=2, uv_attempt=1, texture_package_name="prod-v2", paint_map_directory=None,
            steps=40, octree_resolution=512, chunks=20000, maximum_vertices=15000,
            maximum_triangles=20000, target_triangles=18000, texture_views=6,
            texture_resolution=512, approve_modeling_by=None, modeling_note="",
            approve_retopology_by=None, retopology_note="", approve_texture_by=None,
            texture_note="", prepare_only=True, import_ue5=False, ue5_project=None,
        )
        with patch.object(crank, "parse_args", return_value=args), \
                patch.object(crank, "ensure_workspace", return_value=(self.job, {})), \
                patch.object(crank, "generation_request",
                             side_effect=AssertionError("must not reach generation")):
            self.assertEqual(2, crank.main())


class TexturePackageReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.prod = root / "prod-v2"
        self.prod.mkdir()
        self.uv_blend = root / "uv-authority.blend"
        self.uv_blend.write_bytes(b"uv-authority")
        self.maps = {}
        for channel in ("BaseColor", "Metallic", "Roughness"):
            path = root / (channel + ".jpg")
            path.write_bytes(channel.encode())
            self.maps[channel] = path
        self.write_retopo()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_retopo(self, **overrides):
        payload = {
            "source_uv_authority_sha256": sha256_file(self.uv_blend),
            "texture_lineage": {"sources": {
                channel: {"path": str(path), "sha256": sha256_file(path)}
                for channel, path in self.maps.items()}},
        }
        payload.update(overrides)
        (self.prod / "retopo.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_matching_package_is_reused(self):
        crank.require_matching_texture_package(self.prod, self.uv_blend, self.maps, "prod-v2")

    def test_a_bom_prefixed_retopo_is_still_readable(self):
        retopo = self.prod / "retopo.json"
        retopo.write_bytes(b"\xef\xbb\xbf" + retopo.read_bytes())
        crank.require_matching_texture_package(self.prod, self.uv_blend, self.maps, "prod-v2")

    def test_changed_uv_authority_refuses_with_new_package_name(self):
        self.uv_blend.write_bytes(b"a different unwrap")
        with self.assertRaisesRegex(ValueError, "--texture-package-name") as caught:
            crank.require_matching_texture_package(self.prod, self.uv_blend, self.maps, "prod-v2")
        self.assertIn("UV authority", str(caught.exception))

    def test_changed_paint_map_refuses(self):
        self.maps["Roughness"].write_bytes(b"repainted")
        with self.assertRaisesRegex(ValueError, "Roughness"):
            crank.require_matching_texture_package(self.prod, self.uv_blend, self.maps, "prod-v2")

    def test_missing_lineage_refuses(self):
        self.write_retopo(texture_lineage={})
        with self.assertRaises(ValueError):
            crank.require_matching_texture_package(self.prod, self.uv_blend, self.maps, "prod-v2")


class LauncherCommandTests(unittest.TestCase):
    def test_powershell_launches_bypass_policy_without_profile(self):
        with patch.object(crank, "powershell", return_value="powershell.exe"):
            command = crank.powershell_command(Path("scripts/run_x.ps1"), "-Job", "j")
        self.assertEqual("powershell.exe", command[0])
        self.assertIn("-NoProfile", command)
        policy = command.index("-ExecutionPolicy")
        self.assertEqual("Bypass", command[policy + 1])
        self.assertLess(command.index("-File"), command.index("-Job"))

    def test_blender_argv_carries_the_exit_code_flag(self):
        with patch.object(crank.rac_env, "find_blender", return_value=Path("b.exe")):
            command = crank.blender("describe_mesh.py", "a.glb")
        self.assertIn("--python-exit-code", command)
        self.assertIn("--factory-startup", command)


if __name__ == "__main__":
    unittest.main()
