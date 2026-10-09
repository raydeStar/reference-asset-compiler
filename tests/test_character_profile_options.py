"""The character profile, not the first character's code, sets these stage options.

rebuild_character.py builds three stages' options from the profile: the mouth
corner lift (transport_face_proportions.py), where the hands begin
(prepare_body_acquisition.py) and the body paint's registration and optional
unmirrored red (paint_body_from_views.py). Ennix's options must stay the ones
his builds recorded, and a second character must not inherit his.
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
