"""Species-appropriate stress poses; a cat need not pretend to be Manny."""

QUADRUPED_POSES = {
    "left_foreleg_lift": {"upper_foreleg_l": ("X", -40.0), "lower_foreleg_l": ("X", 55.0)},
    "right_foreleg_lift": {"upper_foreleg_r": ("X", -40.0), "lower_foreleg_r": ("X", 55.0)},
    "left_hindleg_lift": {"thigh_l": ("X", 35.0), "shin_l": ("X", -45.0)},
    "right_hindleg_lift": {"thigh_r": ("X", 35.0), "shin_r": ("X", -45.0)},
    "spine_bend": {"spine_02": ("Z", 20.0)},
    "head_turn": {"neck_01": ("Z", 30.0)},
    "tail_sweep": {"tail_01": ("Z", 25.0), "tail_02": ("Z", 25.0), "tail_03": ("Z", 20.0)},
    "tail_tip": {"tail_04": ("X", 35.0)},
    "ears": {"ear_l": ("Z", 20.0), "ear_r": ("Z", -20.0)},
    "jaw": {"jaw": ("X", 20.0)},
}


def select_poses(profile_id, humanoid_poses):
    if profile_id in ("quadruped_cat", "quadruped_cat_browser"):
        return QUADRUPED_POSES
    if profile_id in (None, "ue5_manny", "ue5_manny_browser", "ue4_mannequin", "mascot_biped_tail"):
        return humanoid_poses
    raise ValueError("No deformation suite for skeleton profile: " + profile_id)
