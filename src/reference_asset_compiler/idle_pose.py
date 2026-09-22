"""Reject obvious standing-idle pose failures; never substitute for visual review.

This contract is deliberately specific to an arms-down humanoid standing idle.
It does not apply to quadrupeds, seated idles, weapon holds, or gestures.
Coordinates are evaluated world-space joint positions in consistent units.
"""
from __future__ import annotations

import math


JOINTS = (
    "pelvis", "upperarm_l", "lowerarm_l", "hand_l",
    "upperarm_r", "lowerarm_r", "hand_r", "foot_l", "foot_r",
)


def check_relaxed_standing_idle(samples, *, height, up_axis=2):
    """Check sampled joint positions, returning measurements and explicit findings.

    Each sample has ``time`` and ``joints`` (canonical names mapped to xyz).
    Sample the delivered clip at its start, end and throughout its duration.
    Thresholds are a conservative default for this declared pose, not universal
    animation-quality scores. A passing receipt still requires visual review.
    """
    if not math.isfinite(height) or height <= 0 or up_axis not in (0, 1, 2):
        raise ValueError("A positive finite character height and xyz up axis are required.")
    if len(samples) < 5:
        raise ValueError("Idle checks need at least five samples including both loop endpoints.")
    previous = -math.inf
    for sample in samples:
        time = sample["time"]
        if not math.isfinite(time) or time <= previous:
            raise ValueError("Sample times must be finite and strictly increasing.")
        previous = time
        for name in JOINTS:
            point = sample["joints"].get(name)
            if point is None or len(point) != 3 or not all(math.isfinite(v) for v in point):
                raise ValueError(f"Missing or nonfinite joint: {name}")
    start, end = samples[0]["time"], samples[-1]["time"]
    if any(b["time"] - a["time"] > (end - start) * .26
           for a, b in zip(samples, samples[1:])):
        raise ValueError("Samples must cover the clip, not cluster at its endpoints.")

    findings = []
    measured = []
    horizontal = [i for i in range(3) if i != up_axis]

    def flag(code, sample, detail):
        findings.append({"code": code, "time": sample["time"], "detail": detail})

    for sample in samples:
        joints = sample["joints"]
        frame = {"time": sample["time"], "arms": {}}
        for side in ("l", "r"):
            shoulder, elbow, wrist = (joints[f"{part}_{side}"]
                                       for part in ("upperarm", "lowerarm", "hand"))
            upper = [b - a for a, b in zip(shoulder, elbow)]
            lower = [b - a for a, b in zip(elbow, wrist)]
            length = math.sqrt(sum(v * v for v in upper))
            lower_length = math.sqrt(sum(v * v for v in lower))
            if min(length, lower_length) < height * .02:
                raise ValueError(f"Degenerate arm chain: {side}")
            angle = math.degrees(math.acos(max(-1, min(1, -upper[up_axis] / length))))
            elbow_bend = math.degrees(math.acos(max(-1, min(1,
                sum(a * b for a, b in zip(upper, lower)) / (length * lower_length)))))
            reach = math.sqrt(sum((wrist[i] - shoulder[i]) ** 2 for i in horizontal)) / height
            wrist_height = (wrist[up_axis] - joints["pelvis"][up_axis]) / height
            frame["arms"][side] = {
                "upper_arm_degrees_from_down": angle, "elbow_bend_degrees": elbow_bend,
                "wrist_horizontal_reach_over_height": reach,
                "wrist_above_pelvis_over_height": wrist_height,
            }
            if angle > 20:
                flag("arms_not_relaxed", sample, f"{side} upper arm is {angle:.1f} degrees from down")
            if reach > .09 or wrist_height > .06:
                flag("hands_not_beside_hips", sample, f"{side} wrist is outside the standing-idle envelope")
            if not 3 <= elbow_bend <= 35:
                flag("elbow_not_softly_bent", sample, f"{side} elbow bend is {elbow_bend:.1f} degrees")
        for name in ("pelvis", "foot_l", "foot_r"):
            drift = math.dist(joints[name], samples[0]["joints"][name]) / height
            if drift > .003:
                flag("stationary_idle_drift", sample, f"{name} moved {drift:.4f} character heights")
        measured.append(frame)
    for name in JOINTS:
        if math.dist(samples[0]["joints"][name], samples[-1]["joints"][name]) / height > .001:
            flag("loop_position_discontinuity", samples[-1], f"{name} does not return to its idle baseline")
    return {
        "contract": "relaxed_humanoid_standing_idle_v1",
        "checks_passed": not findings, "visual_review_required": True,
        "human_approved": False, "findings": findings, "measurements": measured,
    }
