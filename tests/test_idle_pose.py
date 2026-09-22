"""Behavioral controls for the specific failure: an A-pose called an idle."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from reference_asset_compiler.idle_pose import check_relaxed_standing_idle


def samples():
    joints = {"pelvis": [0, 0, 1], "foot_l": [.1, 0, .08], "foot_r": [-.1, 0, .08]}
    for side, sign in (("l", 1), ("r", -1)):
        joints.update({f"upperarm_{side}": [sign * .2, 0, 1.45],
                       f"lowerarm_{side}": [sign * .25, 0, 1.15],
                       f"hand_{side}": [sign * .26, -.06, .92]})
    return [{"time": i / 2, "joints": copy.deepcopy(joints)} for i in range(5)]


def check(frames):
    return check_relaxed_standing_idle(frames, height=1.82)


def test_held_relaxed_pose_passes_without_claiming_approval():
    result = check(samples())
    assert result["checks_passed"]
    assert result["visual_review_required"] and not result["human_approved"]


@pytest.mark.parametrize("bad_frame", [0, 2, 4])
def test_a_pose_rejected_at_start_middle_or_end(bad_frame):
    frames = samples()
    for side, sign in (("l", 1), ("r", -1)):
        frames[bad_frame]["joints"][f"lowerarm_{side}"] = [sign * .35, 0, 1.2]
        frames[bad_frame]["joints"][f"hand_{side}"] = [sign * .43, -.05, .97]
    result = check(frames)
    assert not result["checks_passed"]
    assert "arms_not_relaxed" in {f["code"] for f in result["findings"]}


def test_foot_drift_and_loop_gap_rejected():
    frames = samples()
    frames[-1]["joints"]["foot_l"][0] += .03
    result = check(frames)
    assert {"stationary_idle_drift", "loop_position_discontinuity"} <= {f["code"] for f in result["findings"]}


@pytest.mark.parametrize("bad", [None, [0, 0], [0, float("nan"), 0]])
def test_missing_or_invalid_landmarks_fail_closed(bad):
    frames = samples()
    frames[1]["joints"]["hand_l"] = bad
    with pytest.raises(ValueError, match="joint"):
        check(frames)


def test_duplicate_times_or_sparse_coverage_rejected():
    frames = samples()
    frames[1]["time"] = 0
    with pytest.raises(ValueError, match="times"):
        check(frames)
    with pytest.raises(ValueError, match="five"):
        check(frames[:2])
    frames = samples()
    frames[-1]["time"] = 100
    with pytest.raises(ValueError, match="cover"):
        check(frames)


def test_coordinate_axes_and_scale_are_explicit():
    frames = samples()
    for frame in frames:
        frame["joints"] = {name: [x * 100, z * 100, y * 100]
                           for name, (x, y, z) in frame["joints"].items()}
    assert check_relaxed_standing_idle(frames, height=182, up_axis=1)["checks_passed"]
    with pytest.raises(ValueError, match="height"):
        check_relaxed_standing_idle(frames, height=float("nan"))
