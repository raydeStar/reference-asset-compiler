"""Fail-closed routing for geometry, texture, and articulation adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .contracts import (
    ARTICULATED_DEFAULTS,
    ARTICULATED_STAGES,
    ARTICULATION_MODES,
    ASSET_KINDS,
    BASE_STAGES,
    STATIC_STAGES,
)


def articulation_required(asset_kind: str, mode: str) -> bool:
    if mode == "required":
        return True
    if mode in {"static", "optional"}:
        return False
    return asset_kind in ARTICULATED_DEFAULTS


def plan(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    asset_id = manifest.get("asset_id")
    if not asset_id:
        raise ValueError("Asset intake requires asset_id")
    asset_kind = manifest.get("asset_kind")
    if asset_kind not in ASSET_KINDS:
        raise ValueError(f"Unsupported asset_kind: {asset_kind}")
    articulation = manifest.get("articulation", "auto")
    if articulation not in ARTICULATION_MODES:
        raise ValueError(f"Unsupported articulation mode: {articulation}")
    if asset_kind == "unknown" and articulation == "auto":
        raise ValueError("Unknown assets require an explicit articulation decision")

    requested = manifest.get("candidate_adapters")
    known = {adapter["id"]: adapter for adapter in registry["adapters"]}
    if requested is not None:
        missing = sorted(set(requested) - set(known))
        if missing:
            raise ValueError(f"Unknown model adapters: {missing}")

    compatible = [
        adapter
        for adapter in registry["adapters"]
        if asset_kind in adapter["supports_asset_kinds"]
        and (requested is None or adapter["id"] in requested)
    ]
    geometry = [
        adapter["id"]
        for adapter in compatible
        if adapter["role"] in {"geometry", "geometry_and_texture"}
    ]
    texture = [
        adapter["id"]
        for adapter in compatible
        if "existing_mesh_texture" in adapter.get("outputs", [])
    ]
    if not geometry:
        raise ValueError(f"No geometry adapter supports {asset_kind}")

    articulated = articulation_required(asset_kind, articulation)
    rig_candidates = (
        [
            adapter["id"]
            for adapter in compatible
            if adapter["role"] in {"articulation", "humanoid_rig_refinement"}
        ]
        if articulated
        else []
    )
    existing_mesh_rig_candidates = [
        adapter["id"]
        for adapter in compatible
        if adapter["role"] in {"articulation", "humanoid_rig_refinement"}
        and adapter.get("input_contract") == "approved_existing_mesh"
    ] if articulated else []
    regenerative_rig_challengers = [
        adapter["id"]
        for adapter in compatible
        if adapter["role"] in {"articulation", "humanoid_rig_refinement"}
        and adapter.get("input_contract") != "approved_existing_mesh"
    ] if articulated else []

    if articulated and asset_kind == "humanoid":
        profile = "humanoid"
        ready = True
        rig_backbone = manifest.get("rig_backbone") or "auto_rig_pro"
        blocker = None
    elif articulated and asset_kind == "mascot":
        profile = "mascot_biped"
        ready = bool(manifest.get("skeleton_profile"))
        rig_backbone = manifest.get("rig_backbone") or "custom_blender"
        blocker = None if ready else "Mascots require an explicit skeleton_profile."
    elif articulated:
        profile = "articulated_nonhumanoid"
        ready = False
        rig_backbone = manifest.get("rig_backbone")
        blocker = "No production deformation profile is registered for this articulated asset kind."
    else:
        profile = "static_object"
        ready = True
        rig_backbone = None
        blocker = None

    automation_ready = ready
    automation_blocker = blocker
    rig_driver = None
    if articulated and ready:
        backbone = known.get(rig_backbone)
        if backbone is None or backbone not in compatible:
            automation_ready = False
            automation_blocker = "Rig backbone is not a compatible registered adapter: {0}".format(
                rig_backbone
            )
        elif backbone.get("input_contract") != "approved_existing_mesh":
            automation_ready = False
            automation_blocker = (
                "Rig backbone would replace the approved mesh instead of skinning it: {0}".format(
                    rig_backbone
                )
            )
        else:
            rig_driver = backbone.get("driver")
            driver_status = backbone.get("driver_status")
            if not rig_driver:
                automation_ready = False
                automation_blocker = (
                    "No portable existing-mesh rig driver is registered for {0}.".format(
                        rig_backbone
                    )
                )
            elif driver_status != "production":
                automation_ready = False
                automation_blocker = (
                    "Registered rig driver is candidate-only and cannot clear downstream gates: "
                    "{0}.".format(rig_backbone)
                )

    stages = [*BASE_STAGES, *(ARTICULATED_STAGES if articulated else STATIC_STAGES)]
    return {
        "schema": "reference-asset-compiler.routing.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "asset_id": asset_id,
        "asset_kind": asset_kind,
        "articulation_mode": articulation,
        "articulated": articulated,
        "execution_profile": profile,
        "execution_ready": ready,
        "blocker": blocker,
        "automation_ready": automation_ready,
        "automation_blocker": automation_blocker,
        "geometry_candidates": geometry,
        "texture_candidates": texture,
        "rig_candidates": rig_candidates,
        "existing_mesh_rig_candidates": existing_mesh_rig_candidates,
        "regenerative_rig_challengers": regenerative_rig_challengers,
        "rig_backbone": rig_backbone,
        "rig_driver": rig_driver,
        "stages": stages,
        "selection_policy": {
            "modeling": "fixed-view human approval against the immutable source image",
            "texture": "topology-locked comparison after modeling approval",
            "rig": "chain completeness, deformation review, clean import, UE motion, and cook",
        },
        "authority_immutable": True,
        "production_ready_requires_completed_runtime_gates": True,
    }
