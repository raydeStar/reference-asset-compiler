"""The game review road's recipe, defaults and weight rules (reference_asset_compiler.game_review).

The defaults are the fixes Remora needed on 2026-11-07 (docs/GAME_REVIEW.md); these tests pin them so a later
character inherits them rather than rediscovering the glow, the gaunt orange skin and the stepping chin.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from reference_asset_compiler import game_review as gr

ROOT = Path(__file__).resolve().parents[1]


def recipe(tmp_path, **fields):
    source = tmp_path / "Hero.glb"
    source.write_bytes(b"glTF-not-really")
    body = {"schema": gr.RECIPE_SCHEMA, "name": "Hero", "version": "V1", "source": "Hero.glb",
            "skin_materials": ["skin"], **fields}
    path = tmp_path / "recipe.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_defaults_are_the_remora_fixes(tmp_path):
    job = gr.resolve(recipe(tmp_path), tmp_path / "attempt", ROOT)
    assert job["schema"] == gr.JOB_SCHEMA
    assert job["tag"] == "HeroV1"
    assert job["skin_look"] == {"subsurface": True, "saturation": 0.82, "albedo": 0.92, "specular": 0.35,
                                "scatter": 1.0, "scatter_mask": True}
    assert job["hair_look"] == {"shading": "hair", "roughness": 0.55, "specular": 0.3, "scatter": 0.5}
    assert job["scatter_mask_m"] == [0.02, 0.05]
    assert job["bind"] == {"method": "voxel_heat", "voxel_m": 0.006, "hip_release_cm": 20.0, "hip_release_take": 0.75,
                           "layer_follow_mm": 20.0, "armhole_hold_cm": 4.0}      # not the rig's envelope fallback; the
    #                                                                              buttock, layer and armhole fixes
    assert job["arm_joints"] == "measured_shoulder"                 # elbow, wrist and shoulder found on the mesh
    assert job["hair_motion"]["enabled"] and job["hair_motion"]["sway_m"] == 0.035
    assert "Eye_Lashes" in job["rigid_head_materials"] and "teeth" in job["rigid_head_materials"]
    assert job["unreal"]["dest"] == "/Game/RAC/GameReview/Hero/V1"
    assert job["unreal"]["mesh"] == "/Game/RAC/GameReview/Hero/V1/SK_Hero_V1"
    assert [v[0] for v in job["face_views"]] == ["front", "three_quarter", "front_low"]
    assert [v[0] for v in job["body_views"]] == ["front", "three_quarter", "side", "back"]
    assert job["source_sha256"] == gr.sha256(tmp_path / "Hero.glb")
    assert Path(job["paths"]["finish"]).parent.name == "04-finish"


def test_remora_neck_heights_from_her_chin():
    chain = gr.head_chain(1.500, 1.70)
    assert chain == pytest.approx({"head": 1.495, "neck_02": 1.465, "neck_01": 1.430, "keep_below": 1.410})
    taller = gr.head_chain(1.700, 1.94)
    assert taller["head"] - taller["neck_01"] == pytest.approx(0.065 * 1.94 / 1.7)


def test_chain_weights_sum_to_one_and_blend_above_the_collar():
    chain = gr.head_chain(1.5, 1.7)
    for z in (1.40, 1.42, 1.44, 1.47, 1.49, 1.51):
        assert sum(gr.chain_weights(z, chain).values()) == pytest.approx(1.0)
    assert gr.chain_weights(1.52, chain) == {"head": 1.0}
    assert gr.blend_weights(1.40, {"spine_05": 1.0}, chain) is None          # below the blend: untouched
    mid = gr.blend_weights(1.42, {"spine_05": 1.0}, chain)
    assert 0 < mid["spine_05"] < 1 and sum(mid.values()) == pytest.approx(1.0)
    assert gr.blend_weights(1.50, {"spine_05": 0.3, "neck_01": 0.7}, chain) == {"head": 1.0}


def test_material_kinds(tmp_path):
    job = gr.resolve(recipe(tmp_path, skin_materials=["skin", "Neck"]), tmp_path / "a", ROOT)
    assert gr.material_kind("Neck", job) == "skin"
    assert gr.material_kind("RAC_Eye_Lashes", job) == "rigid"
    assert gr.material_kind("Hero_BraidedKnot_hair_56", job) == "rigid"
    assert gr.material_kind("Outfit", job) is None
    assert gr.is_hair("Hero_BraidedKnot_scalp-cap_56", job)
    named = gr.resolve(recipe(tmp_path, hair_materials=["Fringe"]), tmp_path / "b", ROOT)
    assert gr.is_hair("Fringe", named) and not gr.is_hair("hair", named)


@pytest.mark.parametrize("fields, message", [
    ({"schema": "nope"}, "schema"),
    ({"name": "hero"}, "CamelCase"),
    ({"version": "2"}, "V1"),
    ({"skin_materials": []}, "skin_materials"),
    ({"surprise": 1}, "unknown recipe fields"),
    ({"head_weights": {"neck_01_below_chin_m": 0.001}}, "step down"),
    ({"scatter_mask_m": [0.05, 0.02]}, "near < far"),
    ({"looks": {"Shiny": {"hair": {"roughness": 0.4}}}}, "lower_snake_case"),
    ({"looks": {"shiny": {"hair": {"gloss": 0.4}}}}, "unknown setting"),
    ({"looks": {"shiny": {"hair": {"roughness": 9}}}}, "roughness"),
    ({"unreal": {"game": "other"}}, "the_aether_wars"),
    ({"bind": {"method": "envelope"}}, "voxel_heat or rig"),
    ({"hair_motion": {"free_from_m": 0.1, "free_at_m": 0.05}}, "free_from_m"),
    ({"hair_motion": {"springiness": 2}}, "unknown setting"),
    ({"bind": {"voxel_m": 0.5}}, "bind.voxel_m"),
    ({"looks": {"soft": {"hair": {"shading": "cloth"}}}}, "default or hair"),
    ({"source_sha256": "0" * 64}, "differs"),
    ({"face": {"expression_gain": {}}}, "unknown setting"),
    ({"closed_lids": {"clear": "yes"}}, "true, false or auto"),
    ({"closed_lids": {"stretch": [2.5, 1.3]}}, "low < high"),
    ({"closed_lids": {"blur": 3}}, "unknown setting"),
    ({"teeth_look": {"albedo": 5}}, "albedo"),
    ({"mouth": {"fit": 1}}, "true, false or auto"),
    ({"mouth": {"show_m": 0.05}}, "mouth.show_m"),
    ({"mouth": {"jaw": "x"}}, "unknown setting"),
    ({"unreal": {"animation_source": "mixamo"}}, "manny or player"),
    ({"bind": {"shoulder_release_cm": 30}}, "bind.shoulder_release_cm"),
    ({"bind": {"hip_release_cm": 50}}, "bind.hip_release_cm"),
    ({"bind": {"hip_release_take": 2}}, "bind.hip_release_take"),
    ({"bind": {"layer_follow_mm": 80}}, "bind.layer_follow_mm"),
    ({"bind": {"method": "rig", "hip_release_cm": 20}}, "use method voxel_heat"),
    ({"bind": {"method": "rig", "shoulder_release_cm": 4}}, "use method voxel_heat"),
    ({"bind": {"armhole_hold_cm": 20}}, "bind.armhole_hold_cm"),
    ({"bind": {"method": "rig", "armhole_hold_cm": 4}}, "use method voxel_heat"),
    ({"arm_joints": "guessed"}, "arm_joints must be one of"),
    ({"unreal": {"glider_grip": "yes"}}, "glider_grip must be true or false"),
    ({"unreal": {"climb_reach": {}}}, "at least one of"),
    ({"unreal": {"climb_reach": {"arm_length": 60}}}, "unknown setting"),
    ({"unreal": {"climb_reach": {"wall_distance": 30}}}, "climb_reach.wall_distance"),      # inside the capsule
    ({"unreal": {"climb_reach": {"hang_feet_below_lip": 1.935}}}, "climb_reach.hang_feet_below_lip"),   # metres
    ({"unreal": {"retarget_pose": {"clavicles": "shrug"}}}, "manny or own_rest"),
    ({"unreal": {"retarget_pose": {"clavicle_drop": 8}}}, "needs clavicles own_rest"),
    ({"unreal": {"retarget_pose": {"pitch": {"thigh_l": 3}}}}, "not one of"),
    ({"unreal": {"retarget_pose": {"pitch": {"spine_01": 40}}}}, "pitch.spine_01"),
    ({"unreal": {"retarget_pose": {"twist": 1}}}, "unknown setting"),
    ({"unreal": {"gait_style": {"MM_Idle": {"hip_roll": 9}}}}, "MM_Idle.hip_roll"),
    ({"unreal": {"gait_style": {"MM_Idle": {"strut": 1}}}}, "unknown setting"),
    ({"unreal": {"gait_style": {}}}, "clip name patterns"),
    ({"unreal": {"animation_source": "player", "gait_style": {"MM_Idle": {"arm_in": 4}}}}, "use animation_source manny"),
    ({"face": {"mouth_morph_gain": {"mouth-open": 9}}}, "mouth_morph_gain.mouth-open"),
    ({"face": {"mouth_morph_gain": ["mouth-open"]}}, "map morph names"),
])
def test_refusals(tmp_path, fields, message):
    with pytest.raises(gr.GameReviewError, match=message):
        gr.resolve(recipe(tmp_path, **fields), tmp_path / "a", ROOT)


def test_retarget_pose_and_gait_style(tmp_path):
    job = gr.resolve(recipe(tmp_path), tmp_path / "plain", ROOT)
    assert job["unreal"]["retarget_pose"] is None and job["unreal"]["gait_style"] is None   # the installer's copy
    unreal = {"retarget_pose": {"clavicles": "own_rest", "pitch": {"spine_01": -3, "neck_01": -2}},
              "gait_style": {"MF_Unarmed_Walk_Left": {"hip_roll": 1.8}, "MF_Unarmed_Walk_*": {"narrow_cm": 3}}}
    job = gr.resolve(recipe(tmp_path, unreal=unreal), tmp_path / "styled", ROOT)
    assert job["unreal"]["retarget_pose"] == {"clavicles": "own_rest", "clavicle_drop": 0.0,
                                              "pitch": {"spine_01": -3.0, "neck_01": -2.0}}
    assert list(job["unreal"]["gait_style"]) == ["MF_Unarmed_Walk_Left", "MF_Unarmed_Walk_*"]    # order kept
    assert gr.same_rig_inputs(job, gr.resolve(recipe(tmp_path), tmp_path / "again", ROOT)) == []  # Blender reuse


def test_looks_and_reuse(tmp_path):
    looks = {"hair_matte": {"hair": {"roughness": 0.72, "specular": 0.1}},
             "hair_strands": {"hair": {"specular": 0.3, "specular_from_base": True}}}
    job = gr.resolve(recipe(tmp_path, looks=looks), tmp_path / "a", ROOT)
    assert job["looks"]["hair_strands"]["hair"]["specular_from_base"] is True
    again = gr.resolve(recipe(tmp_path, looks={}), tmp_path / "b", ROOT)
    assert gr.same_rig_inputs(again, job) == []                     # a look-only change reuses the game blend
    other = gr.resolve(recipe(tmp_path, scatter_mask_m=[0.01, 0.03]), tmp_path / "c", ROOT)
    assert gr.same_rig_inputs(other, job) == ["scatter_mask_m"]
    rebound = gr.resolve(recipe(tmp_path, bind={"method": "rig"}), tmp_path / "d", ROOT)
    assert gr.same_rig_inputs(rebound, job) == ["bind"]
    released = gr.resolve(recipe(tmp_path, bind={"shoulder_release_cm": 4}), tmp_path / "e", ROOT)
    assert released["bind"] == {**gr.BIND, "shoulder_release_cm": 4.0}
    assert rebound["bind"] == {"method": "rig", "voxel_m": 0.006}     # the weight fixes are voxel_heat's
    plain = gr.resolve(recipe(tmp_path, bind={"hip_release_cm": 0, "layer_follow_mm": 0}), tmp_path / "f", ROOT)
    assert plain["bind"]["hip_release_cm"] == 0 and plain["bind"]["layer_follow_mm"] == 0     # and can be turned off
    assert gr.same_rig_inputs(released, job) == ["bind"]                # new weights: the Blender half reruns


def test_cli_writes_the_job(tmp_path, capsys):
    path = recipe(tmp_path)
    assert gr.main(["resolve", str(path), str(tmp_path / "attempt"), "--repo-root", str(ROOT)]) == 0
    assert json.loads((tmp_path / "attempt" / "job.json").read_text())["name"] == "Hero"
    bad = recipe(tmp_path, name="x")
    assert gr.main(["resolve", str(bad), str(tmp_path / "other"), "--repo-root", str(ROOT)]) == 2
    assert "RAC_ERROR" in capsys.readouterr().err


def test_face_gains_are_runtime_only(tmp_path):
    job = gr.resolve(recipe(tmp_path), tmp_path / "a", ROOT)
    assert job["face"] == {"mouth_morph_gain": {}}       # the game's viseme table as tuned
    assert job["face_states"][0] == "rest" and job["face_states"][-1] == "blink"
    assert job["visemes"] == ["X", "A", "B", "C", "D", "E", "F", "G", "H"]
    gains = {"mouth-open": 1.5, "mouth-parling": 0.3}
    tuned = gr.resolve(recipe(tmp_path, face={"mouth_morph_gain": gains}), tmp_path / "b", ROOT)
    assert tuned["face"]["mouth_morph_gain"] == gains
    assert gr.same_rig_inputs(tuned, job) == []                     # set on the face component in game, no rebuild


def test_climb_reach_is_runtime_only(tmp_path):
    job = gr.resolve(recipe(tmp_path), tmp_path / "a", ROOT)
    assert job["unreal"]["climb_reach"] is None                     # the hero's numbers on the climbing component
    remora = {"hang_feet_below_lip": 193.5, "hang_distance": 74.5, "wall_distance": 57}
    fitted = gr.resolve(recipe(tmp_path, unreal={"climb_reach": remora}), tmp_path / "b", ROOT)
    assert fitted["unreal"]["climb_reach"] == remora
    one = gr.resolve(recipe(tmp_path, unreal={"climb_reach": {"hang_distance": 78}}), tmp_path / "c", ROOT)
    assert one["unreal"]["climb_reach"] == {"hang_distance": 78.0}  # the settings left out keep the hero's
    assert gr.same_rig_inputs(fitted, job) == []                    # set on the component in game, no rebuild


def test_measured_arm_joints_need_a_fresh_rig(tmp_path):
    job = gr.resolve(recipe(tmp_path, arm_joints="template"), tmp_path / "a", ROOT)
    assert job["arm_joints"] == "template"                          # earlier builds repeat when the recipe says so
    measured = gr.resolve(recipe(tmp_path, arm_joints="measured"), tmp_path / "b", ROOT)
    assert measured["arm_joints"] == "measured"
    assert gr.same_rig_inputs(measured, job) == ["arm_joints"]      # the joints move: steps 01-04 rerun
    before_the_setting = {key: value for key, value in job.items() if key != "arm_joints"}
    assert gr.same_rig_inputs(job, before_the_setting) == []        # an older job was a template rig
    assert gr.same_rig_inputs(measured, before_the_setting) == ["arm_joints"]
    shoulder = gr.resolve(recipe(tmp_path), tmp_path / "c", ROOT)
    assert shoulder["arm_joints"] == gr.ARM_JOINTS_DEFAULT == "measured_shoulder"     # the default since Remora V25
    assert gr.same_rig_inputs(shoulder, measured) == ["arm_joints"]
    assert gr.same_rig_inputs(shoulder, before_the_setting) == ["arm_joints"]         # never reused from a template rig


def test_armhole_hold_is_a_default_of_voxel_heat_and_can_be_turned_off(tmp_path):
    job = gr.resolve(recipe(tmp_path), tmp_path / "a", ROOT)
    assert job["bind"]["armhole_hold_cm"] == 4.0                    # a default since Mark passed Remora V25
    off = gr.resolve(recipe(tmp_path, bind={"armhole_hold_cm": 0}), tmp_path / "b", ROOT)
    assert off["bind"] == {**gr.BIND, "armhole_hold_cm": 0.0}
    assert gr.same_rig_inputs(off, job) == ["bind"]                 # the weights change: steps 01-04 rerun
    before_the_setting = dict(job, bind={k: v for k, v in job["bind"].items() if k != "armhole_hold_cm"})
    assert gr.same_rig_inputs(job, before_the_setting) == ["bind"]  # an older job's weights were not held


def test_teeth_and_closed_lids(tmp_path):
    job = gr.resolve(recipe(tmp_path), tmp_path / "a", ROOT)
    assert job["teeth_look"] == {"albedo": 1.6, "roughness": 0.35, "specular": 0.45}     # the game's own Remora teeth
    assert job["closed_lids"] == {"clear": "auto"}                   # on since Mark passed Remora's face
    lids = gr.resolve(recipe(tmp_path, closed_lids={"clear": True, "lash_band_m": [0.0004, 0.001]}), tmp_path / "b", ROOT)
    assert lids["closed_lids"] == {"clear": True, "lash_band_m": [0.0004, 0.001]}
    assert gr.same_rig_inputs(lids, job) == ["closed_lids"]        # the skin texture is repainted in step 01


def test_mouth_fit_is_a_rig_input(tmp_path):
    job = gr.resolve(recipe(tmp_path), tmp_path / "a", ROOT)
    assert job["mouth"] == {"fit": "auto"}
    fitted = gr.resolve(recipe(tmp_path, mouth={"fit": True, "show_m": 0.0015}), tmp_path / "b", ROOT)
    assert fitted["mouth"] == {"fit": True, "show_m": 0.0015}
    assert gr.same_rig_inputs(fitted, job) == ["mouth"]           # teeth and tongue move in step 01
