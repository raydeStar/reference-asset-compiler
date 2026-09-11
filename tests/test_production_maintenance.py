"""Exercise production drivers against real receipt validators, without inference."""
from argparse import Namespace
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_production as builder, promote_production as publisher
from reference_asset_compiler.io import read_json, sha256_file, write_json
from reference_asset_compiler.workspace import create_workspace, promote_stage, audit_workspace
from support import modeling_evidence, promote_generated, promote_cleanup, promote_retopology

ROOT = Path(__file__).resolve().parents[1]


class ProductionMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.asset = "test-prop"
        self.work = self.root / "work" / self.asset
        self.work.mkdir(parents=True)
        self.source = self.root / "out" / self.asset / (self.asset + ".fbx")
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b"source-fbx")
        write_json(self.source.with_suffix(".ue5import.json"), {"asset_kind": "static_prop"})
        write_json(self.work / "resolved-profile.json", {"tri_budget": 20000})
        self.args = Namespace(budget=100, resolution=64, samples=1, no_sweep=True,
                              strategy="passthrough", skip_render=True, production_name="prod-v2")
        self.calls = []
        self.addCleanup(patch.stopall)
        patch.object(builder, "ROOT", self.root).start()
        patch.object(publisher, "ROOT", self.root).start()
        patch.object(builder, "build_texmap", return_value=({}, [])).start()
        patch.object(builder, "blender", side_effect=self.blender).start()
        patch.object(builder.subprocess, "run", side_effect=self.gate).start()

    def blender(self, script, *args, **kwargs):
        self.calls.append(str(script))
        if script == "retopo_bake.py":
            directory, report = args[1:3]
            baked = {}
            for channel in ("BaseColor", "Roughness", "Metallic", "AO"):
                path = directory / (channel + ".png")
                path.write_bytes(channel.encode())
                baked[channel] = path.name
            (directory / (self.asset + "_retopo.fbx")).write_bytes(b"retopo-fbx")
            write_json(report, {"ok": True, "asset_kind": "static_prop", "low_tris": 12,
                                "baked": baked, "deviation": {"p99_m": 0}, "reduced": False})
        elif script == "apply_production_material.py":
            args[-1].write_bytes(b"production-fbx")
        elif script == "export_uv_regions.py":
            args[-1].write_bytes(b"regions")
        return 0, []

    def gate(self, command, **kwargs):
        write_json(Path(command[5]), {"ok": True})
        return subprocess.CompletedProcess(command, 0, "", "")

    def prepare_ledger(self):
        # Preserve the pre-existing compile directory when creating the ledger fixture.
        reference = self.root / "reference.png"
        reference.write_bytes(b"reference")
        registry = read_json(ROOT / "configs/model-adapters.json")
        job = create_workspace(self.root / "ledger", reference, self.asset,
                               "static_prop", "static", registry)
        for path in job.iterdir():
            path.rename(self.work / path.name)
        candidate, _ = promote_generated(self.work)
        views = []
        for name in ("front", "three-quarter", "side", "back"):
            path = self.work / "modeling" / ("matcap-" + name + ".png")
            path.write_bytes(name.encode())
            views.append(path)
        promote_stage(self.work, "modeling_approval",
                      modeling_evidence(self.work, candidate, views), "Approved.", "Ayric")
        return promote_retopology(self.work, promote_cleanup(self.work, candidate))

    def test_builder_emits_the_fields_required_by_the_real_ledger(self):
        approved = self.prepare_ledger()
        result = builder.build(self.asset, self.args)
        self.assertTrue(result["ok"])
        payload = read_json(self.work / "prod-v2/retopo.json")
        self.assertEqual(sha256_file(approved), payload["source_uv_authority_sha256"])
        output = self.work / "prod-v2" / payload["output_fbx"]
        self.assertEqual(sha256_file(output), payload["output_fbx_sha256"])
        self.assertTrue(audit_workspace(self.work)["ok"])
        state = read_json(self.work / "state.json")
        self.assertEqual("passed", state["stages"]["unwrap_and_bake"]["status"])
        self.assertEqual("pending", state["stages"]["texture_approval"]["status"])
        self.assertEqual("Ayric", state["stages"]["production_retopology"]["approved_by"])

    def test_existing_attempt_is_not_changed_even_if_its_old_report_passes(self):
        old = self.work / "prod-v2/gate-rig.json"
        write_json(old, {"ok": True})
        before = old.read_bytes()
        with self.assertRaisesRegex(ValueError, "overwrite retained"):
            builder.build(self.asset, self.args)
        self.assertEqual(before, old.read_bytes())
        self.assertEqual([], self.calls)

    def test_blender_failure_cannot_produce_a_pass_or_trigger_a_retry(self):
        with patch.object(builder, "blender", return_value=(1, ["Traceback: broken export"])) as run:
            result = builder.build(self.asset, self.args)
        self.assertFalse(result["ok"])
        self.assertEqual("retopo", result["stage"])
        self.assertEqual(1, run.call_count)
        self.assertFalse((self.work / "prod-v2/retopo.json").exists())

    def test_failed_gate_process_cannot_certify_a_passing_json_file(self):
        def failed_gate(command, **kwargs):
            self.gate(command)
            return subprocess.CompletedProcess(command, 1, "", "failed")
        with patch.object(builder.subprocess, "run", side_effect=failed_gate):
            result = builder.build(self.asset, self.args)
        self.assertFalse(result["ok"])
        self.assertEqual("gate-texture", result["stage"])

    def test_budget_trials_are_retained_separately(self):
        result = builder.build(self.asset, self.args)
        self.assertTrue(result["ok"])
        trial = self.work / "prod-v2/budget-100/retopo.json"
        self.assertTrue(trial.is_file())
        self.assertNotIn("output_fbx_sha256", read_json(trial))
        self.assertIn("output_fbx_sha256", read_json(self.work / "prod-v2/retopo.json"))

    def test_publisher_refuses_an_existing_authority(self):
        builder.build(self.asset, self.args)
        target = self.root / "out/test-prop-production/test-prop-production.fbx"
        target.parent.mkdir()
        target.write_bytes(b"accepted authority")
        with self.assertRaisesRegex(ValueError, "overwrite published authority"):
            publisher.promote(self.asset)
        self.assertEqual(b"accepted authority", target.read_bytes())

    def test_publisher_keeps_a_failed_static_budget_gate_failed(self):
        builder.build(self.asset, self.args)
        write_json(self.work / "prod-v2/gate-rig.json", {"ok": False, "failures": ["over budget"]})
        self.assertIsNone(publisher.promote(self.asset))
        self.assertFalse((self.root / "out/test-prop-production").exists())

    def test_material_probe_does_not_write_to_source_tree(self):
        with patch.object(builder, "blender", return_value=(0, ["[SLOT] Material"])) as run:
            self.assertEqual(["Material"], builder.material_slots(self.source))
            script = Path(run.call_args.args[0])
        self.assertFalse(script.is_relative_to(self.root))
        self.assertFalse(script.exists())
