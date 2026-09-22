"""A cat's deformation contract exercises every leg and its independent tail."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deform_poses", ROOT / "scripts/blender/deform_poses.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_quadruped_suite_matches_the_profile_and_exercises_both_sides():
    profile = json.loads((ROOT / "profiles/skeletons/quadruped_cat.json").read_text())
    poses = module.select_poses(profile["profile_id"], {})
    required = set(profile["required_bones"])
    assert len(required) == profile["exact_bone_count"]
    assert {bone for pose in poses.values() for bone in pose} <= required
    for side in "lr":
        assert f"upper_foreleg_{side}" in poses[f"{'left' if side == 'l' else 'right'}_foreleg_lift"]
        assert f"thigh_{side}" in poses[f"{'left' if side == 'l' else 'right'}_hindleg_lift"]
    assert profile["expected_parents"]["tail_01"] == "pelvis"
    assert "tail_04" in poses["tail_tip"]
    assert "jaw" in poses["jaw"]
    assert module.select_poses("ue5_manny", {"existing": {}}) == {"existing": {}}


def test_unknown_species_cannot_pass_an_unrelated_suite():
    with pytest.raises(ValueError, match="No deformation suite"):
        module.select_poses("unsupported_species", {})


@pytest.mark.parametrize('name', ['ue5_manny', 'quadruped_cat'])
def test_browser_budget_does_not_relax_the_canonical_skeleton_contract(name):
    source = json.loads((ROOT / f'profiles/skeletons/{name}.json').read_text())
    browser = json.loads((ROOT / f'profiles/skeletons/{name}_browser.json').read_text())
    assert source['tri_budget'] == 20000
    assert browser['tri_budget'] == 50000
    assert browser['target_runtime'] == 'browser'
    assert browser['tri_budget_waiver'] is None
    assert module.select_poses(browser['profile_id'], {'humanoid': {}}) == module.select_poses(name, {'humanoid': {}})
    for key in ('required_bones', 'expected_parents', 'optional_bones', 'allow_unlisted_bones',
                'root_bone', 'root_may_be_armature_object', 'max_influences', 'exact_bone_count'):
        assert browser.get(key) == source.get(key)
