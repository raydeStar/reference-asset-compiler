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

# Identities that may record mechanical passes but never stand in for a human
# visual review. A delegated reviewer needs an explicit hash-bound authorization.
DELEGATED_REVIEWERS = frozenset({"codex", "claude", "agent", "automation"})
AUTOMATION_REVIEWERS = frozenset({
    "build_production.py", "compile_from_image.py", "promote_production.py",
    "record_ue5_import.py", *DELEGATED_REVIEWERS,
})
