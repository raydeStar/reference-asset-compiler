"""The character profile, not the first character's code, sets these stage options.

rebuild_character.py builds three stages' options from the profile: the mouth
corner lift (transport_face_proportions.py), where the hands begin
(prepare_body_acquisition.py) and the body paint's registration and optional
unmirrored red (paint_body_from_views.py). Ennix's options must stay the ones
his builds recorded, and a second character must not inherit his.

The whole runner, with every stage stubbed, must still issue his recorded
commands; a recipe without rig-landmarks.json derives them from its own proxy.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rebuild_character  # noqa: E402
from rebuild_character import (  # noqa: E402
    body_paint_options,
    body_reduction_options,
    face_proportions_options,
)

ENNIX = json.loads((ROOT / "profiles/characters/ennix.json").read_text(encoding="utf-8"))
RECIPE = json.loads((ROOT / "recipes/ennix-open-review-20261011.json").read_text(encoding="utf-8"))

# Copied from work/ennix-character-v1/rebuild-v10-verify-evidence/cpu-build/build-receipt.json
# (the 2026-10-08 build with the profile); rebuild-v10's receipt has the same
# body reduction values in the same order.
ENNIX_BODY = ["--triangles", "48000", "--hand-triangles", "6000", "--hands-beyond-abs-x", "0.8",
              "--measure-samples", "40000"]
ENNIX_PAINT = ["--px-per-m", "538.89", "--front-origin", "765.5", "500.0", "--side-origin", "734.0", "500.0",
               "--side-band", "0.33", "0.45", "--unmirrored-red", "1.7", "1.8", "425", "5"]


def argv(options):
    return [str(x) for x in options]  # as the runner's run() passes them


def test_ennix_keeps_the_options_his_builds_recorded():
    assert argv(body_reduction_options(RECIPE, ENNIX)) == ENNIX_BODY
    assert argv(body_paint_options(ENNIX)) == ENNIX_PAINT
    # The lift that was in the code: 0.0023 m on his right, 0.0010 m on his left.
    assert argv(face_proportions_options(ENNIX)) == ["--mouth-corner-lift", "2.3", "1.0"]
    assert (float("2.3") / 1000, float("1.0") / 1000) == (0.0023, 0.0010)
    # Recipe 20261010 carries the same hand boundary as the profile.
    older = json.loads((ROOT / "recipes/ennix-open-review-20261010.json").read_text(encoding="utf-8"))
    assert argv(body_reduction_options(older, ENNIX)) == ENNIX_BODY


RECEIPTS = ROOT / "work/ennix-character-v1"


@pytest.mark.skipif(not (RECEIPTS / "rebuild-v10/build-receipt.json").is_file(),
                    reason="Ennix's build receipts are kept out of Git")
def test_ennix_options_match_the_recorded_receipts():
    def recorded(receipt, stage):
        for command in json.loads((RECEIPTS / receipt).read_text(encoding="utf-8"))["commands"]:
            if command["script"] == stage:
                return command["argv"]
        raise AssertionError(f"{stage} not in {receipt}")

    v10 = recorded("rebuild-v10/build-receipt.json", "blender/prepare_ennix_body.py")
    assert v10[v10.index("--triangles"):] == ENNIX_BODY
    verify = "rebuild-v10-verify-evidence/cpu-build/build-receipt.json"
    body = recorded(verify, "blender/prepare_body_acquisition.py")
    assert body[body.index("--triangles"):body.index("--body-object")] == ENNIX_BODY
    paint = recorded(verify, "paint_body_from_views.py")
    assert paint[paint.index("--px-per-m"):] == ENNIX_PAINT


def test_a_profile_without_an_unmirrored_red_passes_no_flag():
    character = copy.deepcopy(ENNIX)
    del character["body_paint"]["unmirrored_red"]
    assert argv(body_paint_options(character)) == ENNIX_PAINT[:ENNIX_PAINT.index("--unmirrored-red")]


def test_a_profile_without_a_mouth_corner_lift_passes_no_flag():
    character = copy.deepcopy(ENNIX)
    del character["face_proportions"]
    assert face_proportions_options(character) == []


def test_the_hand_boundary_comes_from_the_profile():
    recipe = copy.deepcopy(RECIPE)
    del recipe["body"]["hands_beyond_abs_x_m"]
    character = copy.deepcopy(ENNIX)
    character["body"]["hands_beyond_abs_x_m"] = 0.62
    options = argv(body_reduction_options(recipe, character))
    assert options[options.index("--hands-beyond-abs-x") + 1] == "0.62"


def test_an_older_profile_takes_the_recipes_hand_boundary():
    character = copy.deepcopy(ENNIX)
    del character["body"]
    assert argv(body_reduction_options(RECIPE, character)) == ENNIX_BODY


def test_two_different_hand_boundaries_stop_the_build():
    character = copy.deepcopy(ENNIX)
    character["body"]["hands_beyond_abs_x_m"] = 0.62
    with pytest.raises(ValueError, match="0.62"):
        body_reduction_options(RECIPE, character)


def test_hand_counts_without_a_hand_boundary_stop_the_build():
    recipe, character = copy.deepcopy(RECIPE), copy.deepcopy(ENNIX)
    del recipe["body"]["hands_beyond_abs_x_m"]
    del character["body"]
    with pytest.raises(ValueError, match="hands_beyond_abs_x_m"):
        body_reduction_options(recipe, character)


def test_a_uniform_count_recipe_ignores_the_hand_boundary():
    recipe = {"body_review_triangles": 120000}
    assert argv(body_reduction_options(recipe, ENNIX)) == ["--triangles", "120000"]


def transport(tmp_path, *options):
    """Run the stage on a five-vertex head whose lower face already matches the source."""
    marks = np.random.default_rng(0).uniform(0, 100, (68, 2)).tolist()
    landmarks = tmp_path / "landmarks.json"
    landmarks.write_text(json.dumps({"landmarks_68": marks}))
    receipt = tmp_path / "head.json"
    receipt.write_text(json.dumps({"picture": {"landmarks": str(landmarks)}}))
    verts = np.array([[-0.030, -0.13, 1.625],   # mouth corner on the character's right
                      [0.030, -0.13, 1.625],    # and on its left
                      [0.032, -0.10, 1.70],     # left eye
                      [-0.032, -0.10, 1.70],    # right eye
                      [0.0, 0.05, 1.0]])
    source = tmp_path / "head.npz"
    np.savez_compressed(source, verts=verts, **{"vg__helper-l-eye": np.array([2]),
                                                "vg__helper-r-eye": np.array([3])})
    out = tmp_path / "out" / "head.npz"
    subprocess.run([sys.executable, str(ROOT / "scripts/transport_face_proportions.py"), str(source),
                    str(receipt), str(landmarks), str(out), *options], check=True, capture_output=True)
    return verts, np.load(out)["verts"]


def test_the_face_stage_lifts_no_corner_by_default(tmp_path):
    before, after = transport(tmp_path)
    assert np.array_equal(before, after)


def test_the_face_stage_lifts_each_corner_by_its_own_millimetres(tmp_path):
    before, after = transport(tmp_path, "--mouth-corner-lift", "2.3", "1.0")
    lift = after[:, 2] - before[:, 2]
    assert lift[0] == pytest.approx(0.0023, abs=1e-12)
    assert lift[1] == pytest.approx(0.0010, abs=1e-12)
    assert np.abs(lift[2:]).max() < 1e-9
    assert np.array_equal(before[:, :2], after[:, :2])


# The whole runner, every stage stubbed: which commands it issues, in what order.

SKELETON = str(ROOT / "profiles/skeletons/ue5_manny.json")


def stub_build(tmp_path, monkeypatch, recipe, *options, blender="blender"):
    """Run rebuild_character.main() on placeholder inputs; return the build directory.

    Each stub stage writes only what the runner reads back: the proxy, the
    derived landmarks and the rig gate's report.
    """
    bundle, recipe = tmp_path / "bundle", copy.deepcopy(recipe)
    for name, info in recipe["inputs"].items():
        path = bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"picture": {}, "image": name}))  # the runner rewrites these pointers
        info["sha256"] = rebuild_character.sha(path)
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(json.dumps(recipe))

    def stage(cmd, **_):
        script = Path(cmd[cmd.index("--python") + 1] if "--python" in cmd else cmd[1]).name
        args = [Path(x) for x in (cmd[cmd.index("--") + 1:] if "--" in cmd else cmd[2:])]
        if script == "export_skinning_proxy.py":
            args[1].parent.mkdir(parents=True, exist_ok=True)
            args[1].write_bytes(b"proxy")
        elif script == "derive_humanoid_landmarks.py":
            args[1].mkdir(parents=True)
            (args[1] / "humanoid-landmarks.json").write_text(json.dumps({
                "skeleton_profile": "ue5_manny", "payload_fbx": str(args[0]),
                "payload_fbx_sha256": rebuild_character.sha(args[0]), "joints": {}, "bones": {},
                "reviewed_by": None, "review_status": "derived_pending_overlay_review"}))
        elif script == "gate_rig.py":
            args[2].parent.mkdir(parents=True, exist_ok=True)
            args[2].write_text(json.dumps({"total_tris": 70000, "tri_budget": 80000,
                                           "tri_budget_rule": {"character_tier": {"id": "hero"}}}))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(rebuild_character.subprocess, "run", stage)
    monkeypatch.setattr(rebuild_character.subprocess, "check_output", lambda *_, **__: "Blender (stub)")
    out = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["rebuild_character.py", "--inputs", str(bundle), "--out", str(out),
                                      "--blender", blender, "--recipe", str(recipe_path), *options])
    rebuild_character.main()
    return out


def receipt_of(out):
    return json.loads((out / "build-receipt.json").read_text(encoding="utf-8"))


def stage_args(receipt, script):
    """The arguments a Blender stage got after `--`."""
    argv = next(c["argv"] for c in receipt["commands"] if c["script"] == script)
    return argv[argv.index("--") + 1:]


VERIFY = RECEIPTS / "rebuild-v10-verify-evidence/cpu-build/build-receipt.json"


@pytest.mark.skipif(not VERIFY.is_file(), reason="Ennix's build receipts are kept out of Git")
def test_ennix_build_issues_the_commands_his_cpu_build_recorded(tmp_path, monkeypatch):
    recorded = json.loads(VERIFY.read_text(encoding="utf-8"))["commands"]
    blender = next(c["argv"][0] for c in recorded if "--python" in c["argv"])
    issued = receipt_of(stub_build(tmp_path, monkeypatch, RECIPE, "--device", "CPU", blender=blender))["commands"]

    def normalised(commands, root, out):
        return [(c["script"], ["{exe}"] + [x.replace(str(out), "{out}").replace(str(root), "{root}")
                                           for x in c["argv"][1:]]) for c in commands]

    # transport_face_proportions.py: python, script, head.npz, head.json, landmarks, out/head.npz
    first = recorded[0]["argv"]
    expected = normalised(recorded, Path(first[1]).parents[1], Path(first[5]).parent)
    # Since that build the mouth-corner lift comes from the profile as arguments (it was in the code).
    expected[0][1].extend(["--mouth-corner-lift", "2.3", "1.0"])
    assert normalised(issued, ROOT, tmp_path / "build") == expected


def test_a_recipe_with_measured_landmarks_rigs_from_them(tmp_path, monkeypatch):
    out = stub_build(tmp_path, monkeypatch, RECIPE, "--device", "CPU")
    receipt = receipt_of(out)
    assert "blender/derive_humanoid_landmarks.py" not in [c["script"] for c in receipt["commands"]]
    proxy, landmarks = out / "rig-input/Ennix_proxy.fbx", out / "rig-input/landmarks.json"
    assert stage_args(receipt, "blender/rig_from_landmarks.py")[:3] == [str(proxy), str(landmarks), SKELETON]
    used = json.loads(landmarks.read_text())
    assert used["based_on_measured_landmarks_sha256"] == receipt["input_hashes"]["rig-landmarks.json"]
    assert used["payload_fbx_sha256"] == rebuild_character.sha(proxy)
    assert not (out / "rig-input/derived").exists() and "rig_landmarks" not in receipt


@pytest.mark.parametrize(("device", "overlays"), [("CPU", ["--no-overlays"]), ("GPU", [])])
def test_a_recipe_without_rig_landmarks_derives_them_from_its_proxy(tmp_path, monkeypatch, device, overlays):
    recipe = copy.deepcopy(RECIPE)
    del recipe["inputs"]["rig-landmarks.json"]
    out = stub_build(tmp_path, monkeypatch, recipe, "--device", device)
    receipt = receipt_of(out)
    scripts = [c["script"] for c in receipt["commands"]]
    at = scripts.index("blender/derive_humanoid_landmarks.py")
    assert scripts[at - 1:at + 2] == ["blender/export_skinning_proxy.py", "blender/derive_humanoid_landmarks.py",
                                      "blender/rig_from_landmarks.py"]
    proxy, derived = out / "rig-input/Ennix_proxy.fbx", out / "rig-input/derived"
    assert stage_args(receipt, "blender/derive_humanoid_landmarks.py") == [
        str(proxy), str(derived), "--profile", SKELETON, *overlays]
    landmarks = out / "rig-input/landmarks.json"
    assert stage_args(receipt, "blender/rig_from_landmarks.py")[:3] == [str(proxy), str(landmarks), SKELETON]
    used = json.loads(landmarks.read_text())
    measured = json.loads((derived / "humanoid-landmarks.json").read_text())
    assert {key: used[key] for key in measured} == measured
    assert "based_on_measured_landmarks_sha256" not in used
    assert "not measured" in used["rebuild_note"] and "not measured" in receipt["rig_landmarks"]
    assert any("derived in this build" in limit for limit in receipt["limits"])
