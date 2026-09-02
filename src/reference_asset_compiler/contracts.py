"""Stable contracts shared by the planner, workspace, and CLI."""

from __future__ import annotations

ASSET_KINDS = {
    "humanoid",
    "mascot",
    "creature",
    "mechanical_articulated",
    "static_prop",
    "wearable",
    "environment_structure",
    "vegetation",
    "unknown",
}

ARTICULATION_MODES = {"auto", "required", "optional", "static"}
ARTICULATED_DEFAULTS = {"humanoid", "mascot", "creature", "mechanical_articulated"}

BASE_STAGES = (
    "intake",
    "route",
    "generate_candidates",
    "modeling_approval",
    "semantic_cleanup",
    "production_retopology",
    "unwrap_and_bake",
    "texture_approval",
)

ARTICULATED_STAGES = (
    "rig_and_skin",
    "deformation_validation",
    "ue5_import",
    "ue5_motion_review",
    "cook",
)

STATIC_STAGES = (
    "collision_optional",
    "static_validation",
    "ue5_import",
    "ue5_runtime_review",
    "cook",
)

TERMINAL_STATUSES = {"passed", "rejected", "blocked"}
STAGE_STATUSES = {"pending", "in_progress", *TERMINAL_STATUSES}
