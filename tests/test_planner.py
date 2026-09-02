from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.planner import plan

REGISTRY = json.loads((ROOT / "configs" / "model-adapters.json").read_text(encoding="utf-8"))


class PlannerTests(unittest.TestCase):
    def test_humanoid_separates_geometry_texture_and_rig_roles(self) -> None:
        result = plan(
            {"asset_id": "operative", "asset_kind": "humanoid", "articulation": "required"},
            REGISTRY,
        )
        self.assertTrue(result["execution_ready"])
        self.assertEqual("humanoid", result["execution_profile"])
        self.assertIn("pixal3d", result["geometry_candidates"])
        self.assertIn("trellis2", result["texture_candidates"])
        self.assertIn("anigen", result["rig_candidates"])
        self.assertIn("auto_rig_pro", result["existing_mesh_rig_candidates"])
        self.assertIn("anigen", result["regenerative_rig_challengers"])
        self.assertEqual("auto_rig_pro", result["rig_backbone"])
        self.assertFalse(result["automation_ready"])
        self.assertEqual("scripts/run_arp_rig_candidate.ps1", result["rig_driver"])
        self.assertIn("candidate-only", result["automation_blocker"])

    def test_static_prop_never_enters_rigging(self) -> None:
        result = plan(
            {"asset_id": "sword", "asset_kind": "static_prop", "articulation": "auto"},
            REGISTRY,
        )
        self.assertFalse(result["articulated"])
        self.assertEqual([], result["rig_candidates"])
        self.assertTrue(result["automation_ready"])
        self.assertNotIn("rig_and_skin", result["stages"])
        self.assertIn("static_validation", result["stages"])

    def test_mascot_requires_an_explicit_skeleton_profile(self) -> None:
        blocked = plan(
            {"asset_id": "fox", "asset_kind": "mascot", "articulation": "required"},
            REGISTRY,
        )
        self.assertFalse(blocked["execution_ready"])
        ready = plan(
            {
                "asset_id": "fox",
                "asset_kind": "mascot",
                "articulation": "required",
                "skeleton_profile": "biped-with-one-tail",
            },
            REGISTRY,
        )
        self.assertTrue(ready["execution_ready"])
        self.assertEqual("mascot_biped", ready["execution_profile"])

    def test_arbitrary_creature_articulation_fails_closed(self) -> None:
        result = plan(
            {"asset_id": "spider", "asset_kind": "creature", "articulation": "required"},
            REGISTRY,
        )
        self.assertFalse(result["execution_ready"])
        self.assertIsNotNone(result["blocker"])

    def test_regenerative_challenger_cannot_be_the_post_approval_rig_backbone(self) -> None:
        result = plan(
            {
                "asset_id": "operative",
                "asset_kind": "humanoid",
                "articulation": "required",
                "rig_backbone": "anigen",
            },
            REGISTRY,
        )
        self.assertTrue(result["execution_ready"])
        self.assertFalse(result["automation_ready"])
        self.assertIn("replace the approved mesh", result["automation_blocker"])

    def test_unknown_asset_requires_explicit_articulation(self) -> None:
        with self.assertRaises(ValueError):
            plan(
                {"asset_id": "mystery", "asset_kind": "unknown", "articulation": "auto"},
                REGISTRY,
            )


if __name__ == "__main__":
    unittest.main()
