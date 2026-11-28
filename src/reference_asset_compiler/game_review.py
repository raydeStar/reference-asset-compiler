"""The game review road: a finished character GLB to a playable, closeup-checked review in the game.

A recipe names the character, its source GLB and which material slots are skin and hair; everything the first
character (Remora, 2026-11-07) taught is a default here rather than something to rediscover:

- Rest morph weights are baked into the basis (Unreal rests every morph at 0).
- The hands are fitted to the mesh (the landmark route drops Manny's hand in by forearm direction alone).
- The body is heat-weighted on a watertight voxel stand-in (the rig's own bind fell back to envelope capsules).
- The landmark rig is given Manny's bone axes, or every Manny clip rolls the forearms and knees.
- The head is rigid (face, hair, eyes, mouth) and the skin blends head -> neck_02 -> neck_01 below the chin: the
  envelope weights hung the chin on the spine and it stepped whenever the idle tilted the head.
- Skin gets no subsurface scatter in a band under the hair (vertex colour mask): with Substrate and virtual shadow
  maps the hair's shadow edge scattered into a red glow along the hairline.
- glTF normal maps are flipped to Unreal's convention; hair gets Unreal's hair shading along a flow map baked
  from the mesh (default-lit hair read plastic, and at Unreal's specular 0.5 wet).
- Skin is less saturated and slightly darker than the paint, so it does not read flat orange in warm light.
- Faces are judged in the game's own light, in fixed front, three-quarter and low views, plus four body views.

``resolve`` turns a recipe into the job every step reads (absolute paths, every default filled in), so a receipt
shows exactly what ran. Nothing here runs Blender or Unreal; run_game_review.ps1 does.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

RECIPE_SCHEMA = "reference-asset-compiler.game-review-recipe.v1"
JOB_SCHEMA = "reference-asset-compiler.game-review-job.v1"

RIGID_HEAD_MATERIALS = ("hair", "scalp", "eyes", "Eye_Lashes", "Eye_Occlusion", "teeth", "tongue",
                        "Mouth_Interior")
"""Substrings of material names that ride the head bone alone. Expressions are morph targets, so nothing is lost."""

HEAD_WEIGHTS = {
    # Heights below the measured chin (metres, for a ~1.7 m character; scaled by measured height / 1.7).
    # Remora: chin 1.500 -> head 1.495, neck_02 1.465, neck_01 1.430, untouched below 1.410.
    "head_below_chin_m": 0.005,
    "neck_02_below_chin_m": 0.035,
    "neck_01_below_chin_m": 0.070,
    "keep_below_chin_m": 0.090,
}

SKIN_LOOK = {"subsurface": True, "saturation": 0.82, "albedo": 0.92, "specular": 0.35, "scatter": 1.0,
             "scatter_mask": True}
HAIR_LOOK = {"shading": "hair", "roughness": 0.55, "specular": 0.3, "scatter": 0.5}
"""Unreal's hair shading along a flow map baked from the mesh. Mark picked it on Remora (2026-11-07) over the
default-lit roughness 0.55 / specular 0.2, which read plastic; `"shading": "default"` in a look restores that."""
BIND = {"method": "voxel_heat", "voxel_m": 0.006, "hip_release_cm": 20.0, "hip_release_take": 0.75,
        "layer_follow_mm": 20.0, "armhole_hold_cm": 4.0}
"""The landmark rig's own heat bind fails on a layered character and falls back to envelope capsules (Remora's
arms split four ways, trousers and tunic flung out in every stride). voxel_heat rebinds on a watertight stand-in.
The stand-in's heat then gives the buttock to the thigh and gives outfit layers a few millimetres apart slightly
different weights: hip_release and layer_follow correct both (Mark passed them on Remora V22, 2026-11-09: "that looks
really good"). They belong to voxel_heat; method rig leaves the rig's weights alone. shoulder_release_cm stays opt-in:
it made up for a shoulder joint placed too low, and arm_joints measured_shoulder puts the joint right instead.
armhole_hold_cm keeps the outfit round a bare arm's shoulder with the torso (a sleeved arm is detected and left
alone); Mark passed it on Remora V25 (2026-11-10: "Looks right") and it is a default with the other two."""
_VOXEL_ONLY = ("shoulder_release_cm", "hip_release_cm", "hip_release_take", "layer_follow_mm", "armhole_hold_cm")
HAIR_MOTION = {"enabled": True, "sway_m": 0.035, "lift_m": 0.025, "free_from_m": 0.01, "free_at_m": 0.09}
"""Sway shapes on the loose hair in front of the ears (still within 1 cm of skin or scalp, free from 9 cm), which
the review's play script drives with a spring from the head's acceleration."""
TEETH_LOOK = {"albedo": 1.6, "roughness": 0.35, "specular": 0.45}
"""The game installer's teeth for Remora (Tools/Characters/Remora.json teeth_albedo_scale; its Teeth material's
roughness and specular). The stock MakeHuman teeth texture at 1x read grey-brown in the game's shadowed mouth (V9)."""
CLOSED_LIDS = {"clear": "auto"}
"""Step 01 repaint of the upper-lid skin a blink uncovers (scripts/blender/clear_closed_lids.py): a head painted from
reference views carries the reference's lashes and liner on the folded lid, which a blink stretches into a dark smear.
Optional settings: stretch, seen_open, lash_band_m (see that module). "auto" (the default since Mark passed Remora's
face, 2026-11-07) repaints when the head has closure morphs and skips with a note when it has not; true requires it."""
MOUTH = {"fit": "auto"}
"""Step 01 mouth fit (scripts/blender/fit_mouth.py): the teeth and tongue moved together so the upper incisor edge sits
just under the lip line measured from the jaw morph, and the tongue given the lower teeth's motion in every morph that
opens the jaw. Optional settings: show_m, tongue_follow, max_shift_m, rest_tolerance. "auto" (the default since Mark
passed Remora's face) fits when the head has teeth and a jaw morph and records why not otherwise; true requires it."""
FACE = {"mouth_morph_gain": {}}
"""The face's lip-sync gains (the game face component's MouthMorphGain, morph name -> gain). The game's viseme table was
tuned on another face, so a face whose jaw needs more travel, or whose parted lips bare the teeth, scales its own mouth
morphs here; empty keeps the table as tuned. The review sets them on the player's face component at runtime and
reports every morph name the mesh does not carry: the game ignores a missing morph, so a misspelt gain does nothing."""
FACE_STATES = ("rest", "idle", "combat", "hurt", "climb", "hang", "glide", "blink")
"""The face pass (-Face): no expression, then each expression the game's face component plays, then the lids shut."""
VISEMES = ("X", "A", "B", "C", "D", "E", "F", "G", "H")
"""Rhubarb's mouth shapes, the game's lip-sync set, each held by the face component itself."""
SCATTER_MASK_M = (0.02, 0.05)
"""No scatter within 2 cm of hair, full scatter from 5 cm (the wider band Mark picked over 1-3 cm)."""


def _engine_dir() -> str:
    """Where this workstation keeps the engine: RAC_UNREAL_ENGINE_DIR, else Epic's default install of UE 5.8."""
    return os.environ.get("RAC_UNREAL_ENGINE_DIR") or str(
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Epic Games" / "UE_5.8" / "Engine" / "Binaries" / "Win64")


def _game_project() -> str:
    """The game's .uproject: RAC_GAME_PROJECT, else Unreal's default project folder for whoever is signed in."""
    return os.environ.get("RAC_GAME_PROJECT") or str(
        Path.home() / "Documents" / "Unreal Projects" / "TheAetherWars" / "TheAetherWars.uproject")


UNREAL = {
    "game": "the_aether_wars",
    # where the engine and the game live differs by workstation; a recipe's "unreal" block overrides either
    "engine_dir": _engine_dir(),
    "project": _game_project(),
    "level": "/Game/MCP/L_AetherVault_MCP",
    "content_root": "/Game/RAC/GameReview",
    "player_blueprint": "/Game/ThirdPerson/Blueprints/BP_ThirdPersonCharacter",
    "pawn_class": "TheAetherWarsCharacter",
    "resolution": [1440, 900],
    "walk_key": "LeftAlt",
    "walk_speed": 89.180502,
    # the owner of the player's animations that have no Manny source (Aether push, left push, recall)
    "secondary_source_mesh": "/Game/Character02/Hero/SK_Character02_Hero",
    # "manny": Epic's Manny clips; "player": what the player plays now (the game hero's polished set), retargeted
    # from the player Blueprint's own mesh
    "animation_source": "manny",
    # the character's own calibration of the Manny retargeter (docs/GAME_REVIEW.md, "Retarget pose and gait style");
    # None keeps the installer's exact copy of Manny's joint angles
    "retarget_pose": None,
    # a per-frame gait layer on retargeted clips, by source clip name pattern (first match wins); None adds nothing
    "gait_style": None,
    # fit the glide clip's hands to the Sailwing's handles from the hero's own glide, and hang the glider for them
    "glider_grip": False,
    # where the climbing component holds this character's body on walls and ledges, so her hands meet them (CLIMB_REACH);
    # None keeps the hero's numbers
    "climb_reach": None,
}

ARM_JOINTS = ("template", "measured", "measured_shoulder")
"""How the landmark step places the arm's joints. template: the elbow halfway down a template arm, the hand as the outer
10.5% of the height (the original route, kept so earlier builds can be repeated). measured: the elbow where the arm's
centreline bends and the wrist just past the forearm's thinnest girth, the same share of the arm on both sides.
The template put Remora's elbow joint 8 cm below her elbow, which Mark saw as "an extra bone" (2026-11-10).
measured_shoulder: the same, and the shoulder joint found in the shoulder (as far under its top as in from its side,
on the upper arm's own centreline) instead of at a share of the height and of Manny's width; the template put
Remora's 2 cm low and 2-5 cm too far out, and Mark saw the shoulder "just bending wrong" (2026-11-10)."""
ARM_JOINTS_DEFAULT = "measured_shoulder"
"""Mark passed Remora V25, built with measured_shoulder, in the game on 2026-11-10 ("Looks right"), so a recipe that
does not say gets every arm joint measured. A job written before the setting existed was a template rig
(ARM_JOINTS[0]); same_rig_inputs reads it that way, so it cannot be reused for a measured build by mistake."""

CLIMB_REACH = {"hang_feet_below_lip": (150.0, 260.0), "hang_distance": (40.0, 120.0), "wall_distance": (40.0, 100.0)}
"""The game's climbing component (UClimbingComponent) places the body by three numbers matched to the hero's reach in
the traversal clips: feet below a ledge's lip in a hang (hero 207 cm), capsule centre off the face in a hang (82) and
on a wall (62). A character with shorter arms and torso plays the same clips with her hands short of the lip, so her
own numbers go here; the review sets them on the player's component for the session. The capsule is 35 cm wide, so
the distances stay above 40. Remora (Mark, 2026-11-10): 193.5, 74.5, 57."""

PITCH_BONES = ("spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "neck_01", "neck_02", "head")
GAIT_OPS = {"hip_roll": (0.5, 3.0), "hip_yaw": (0.5, 3.0), "hip_shift": (0.5, 3.0), "narrow_cm": (0.0, 6.0),
            "swing_clear": (0.0, 1.0), "arm_in": (-30.0, 30.0), "upright": (-15.0, 15.0), "elbow_bend": (0.5, 1.2),
            "finger_relax": (0.0, 1.0)}

FACE_VIEWS = (("front", 0, -2), ("three_quarter", 35, -2), ("front_low", 0, 10))
BODY_VIEWS = (("front", 0), ("three_quarter", 45), ("side", 90), ("back", 180))

_NAME = re.compile(r"^[A-Z][A-Za-z0-9]{1,31}$")
_VERSION = re.compile(r"^V[0-9]{1,3}$")
_LOOK = re.compile(r"^[a-z][a-z0-9_]{0,23}$")


class GameReviewError(ValueError):
    """A recipe that cannot be run; nothing is started in its place."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def smoothstep(value: float, low: float, high: float) -> float:
    """0 below low, 1 above high, the cubic in between (the mask and weight blends use it)."""
    if high <= low:
        raise GameReviewError("smoothstep needs low < high")
    t = min(max((value - low) / (high - low), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def head_chain(chin_z: float, height_m: float, settings: dict[str, float] | None = None) -> dict[str, float]:
    """Absolute heights for the head -> neck_02 -> neck_01 tent weights, from the measured chin."""
    s = {**HEAD_WEIGHTS, **(settings or {})}
    scale = height_m / 1.7
    chain = {
        "head": chin_z - s["head_below_chin_m"] * scale,
        "neck_02": chin_z - s["neck_02_below_chin_m"] * scale,
        "neck_01": chin_z - s["neck_01_below_chin_m"] * scale,
        "keep_below": chin_z - s["keep_below_chin_m"] * scale,
    }
    if not chain["head"] > chain["neck_02"] > chain["neck_01"] > chain["keep_below"]:
        raise GameReviewError("head weights must step down: head > neck_02 > neck_01 > keep_below")
    return chain


def chain_weights(z: float, chain: dict[str, float]) -> dict[str, float]:
    """Tent weights by height along head -> neck_02 -> neck_01 (each sums to 1)."""
    zh, z2, z1 = chain["head"], chain["neck_02"], chain["neck_01"]
    if z >= zh:
        return {"head": 1.0}
    if z >= z2:
        t = (z - z2) / (zh - z2)
        return {"head": t, "neck_02": 1 - t}
    if z >= z1:
        t = (z - z1) / (z2 - z1)
        return {"neck_02": t, "neck_01": 1 - t}
    return {"neck_01": 1.0}


def blend_weights(z: float, old: dict[str, float], chain: dict[str, float]) -> dict[str, float] | None:
    """The new weights for a skin vertex at height z, or None to leave it as it was (below keep_below).

    Between keep_below and the neck_01 height the chain fades in over the old weights, so the collar seam the
    rig bound stays where it was.
    """
    if z < chain["keep_below"]:
        return None
    s = smoothstep(z, chain["keep_below"], chain["neck_01"])
    total = sum(old.values()) or 1.0
    new = {bone: (1 - s) * weight / total for bone, weight in old.items()}
    for bone, weight in chain_weights(z, chain).items():
        new[bone] = new.get(bone, 0.0) + s * weight
    return {bone: weight for bone, weight in new.items() if weight > 1e-4}


def material_kind(name: str, job: dict[str, Any]) -> str | None:
    """'skin', 'rigid' (head-only) or None (left to the rig), by the job's material lists."""
    if name in job["skin_materials"]:
        return "skin"
    if any(part.lower() in name.lower() for part in job["rigid_head_materials"]):
        return "rigid"
    return None


def is_hair(name: str, job: dict[str, Any]) -> bool:
    hair = job.get("hair_materials")
    if hair:
        return name in hair
    lowered = name.lower()
    return "hair" in lowered or "scalp" in lowered


def _number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= float(value) <= high:
        raise GameReviewError(f"{label} must be a number in [{low}, {high}], not {value!r}")
    return float(value)


def _retarget_pose(raw: Any) -> dict[str, Any] | None:
    """clavicles: 'manny' (the installer's exact copy) or 'own_rest' (her collarbones keep their modelled rest and the
    upper arms are re-aimed so the arms still hang as Manny's); clavicle_drop lowers them further (degrees);
    pitch tilts spine/neck bones in the retarget pose (degrees, + bends forward)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise GameReviewError("unreal.retarget_pose must be an object")
    out: dict[str, Any] = {"clavicles": "manny", "clavicle_drop": 0.0, "pitch": {}}
    for key, value in raw.items():
        if key == "clavicles":
            if value not in ("manny", "own_rest"):
                raise GameReviewError("unreal.retarget_pose.clavicles must be manny or own_rest")
            out[key] = value
        elif key == "clavicle_drop":
            out[key] = _number(value, "unreal.retarget_pose.clavicle_drop", -20, 20)
        elif key == "pitch":
            if not isinstance(value, dict):
                raise GameReviewError("unreal.retarget_pose.pitch must map bone names to degrees")
            for bone, degrees in value.items():
                if bone not in PITCH_BONES:
                    raise GameReviewError(f"unreal.retarget_pose.pitch: {bone!r} is not one of {', '.join(PITCH_BONES)}")
                out["pitch"][bone] = _number(degrees, f"unreal.retarget_pose.pitch.{bone}", -15, 15)
        else:
            raise GameReviewError(f"unreal.retarget_pose has an unknown setting {key!r}")
    if out["clavicle_drop"] and out["clavicles"] != "own_rest":
        raise GameReviewError("unreal.retarget_pose.clavicle_drop needs clavicles own_rest")
    return out


def _gait_style(raw: Any) -> dict[str, dict[str, float]] | None:
    """Source clip name pattern (fnmatch, first match wins) -> gait operations (GAIT_OPS ranges)."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw:
        raise GameReviewError("unreal.gait_style must map clip name patterns to settings")
    out: dict[str, dict[str, float]] = {}
    for pattern, ops in raw.items():
        if not isinstance(pattern, str) or not pattern.strip():
            raise GameReviewError("unreal.gait_style patterns must be clip names or fnmatch patterns")
        if not isinstance(ops, dict) or not ops:
            raise GameReviewError(f"unreal.gait_style.{pattern} must be an object of settings")
        out[pattern] = {}
        for key, value in ops.items():
            if key not in GAIT_OPS:
                raise GameReviewError(f"unreal.gait_style.{pattern} has an unknown setting {key!r}")
            out[pattern][key] = _number(value, f"unreal.gait_style.{pattern}.{key}", *GAIT_OPS[key])
    return out


def _climb_reach(raw: Any) -> dict[str, float] | None:
    """The climbing component settings this character changes (centimetres); any left out keep the hero's."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw:
        raise GameReviewError(f"unreal.climb_reach must set at least one of {', '.join(CLIMB_REACH)}")
    out: dict[str, float] = {}
    for key, value in raw.items():
        if key not in CLIMB_REACH:
            raise GameReviewError(f"unreal.climb_reach has an unknown setting {key!r}")
        out[key] = _number(value, f"unreal.climb_reach.{key}", *CLIMB_REACH[key])
    return out


def _look(raw: Any, label: str) -> dict[str, Any]:
    """A named alternative look: per-slot-kind material overrides (skin / hair / slot name)."""
    if not isinstance(raw, dict) or not raw:
        raise GameReviewError(f"look {label} must map 'skin', 'hair' or a slot name to settings")
    out: dict[str, Any] = {}
    for target, settings in raw.items():
        if not isinstance(settings, dict):
            raise GameReviewError(f"look {label}.{target} must be an object of material settings")
        clean: dict[str, Any] = {}
        for key, value in settings.items():
            if key in ("roughness", "specular", "saturation", "albedo", "scatter", "normal_strength"):
                clean[key] = _number(value, f"look {label}.{target}.{key}", 0.0, 2.0)
            elif key in ("subsurface", "scatter_mask"):
                if not isinstance(value, bool):
                    raise GameReviewError(f"look {label}.{target}.{key} must be true or false")
                clean[key] = value
            elif key in ("roughness_from_texture", "specular_from_base"):
                if not isinstance(value, bool):
                    raise GameReviewError(f"look {label}.{target}.{key} must be true or false")
                clean[key] = value
            elif key == "shading":
                if value not in ("default", "hair"):      # cloth: its Cloth amount pin is not exposed to Python
                    raise GameReviewError(f"look {label}.{target}.shading must be default or hair")
                clean[key] = value
            elif key == "base_tint":
                if (not isinstance(value, list) or len(value) != 3
                        or not all(isinstance(v, (int, float)) and 0 <= v <= 2 for v in value)):
                    raise GameReviewError(f"look {label}.{target}.base_tint must be three numbers in [0, 2]")
                clean[key] = [float(v) for v in value]
            else:
                raise GameReviewError(f"look {label}.{target} has an unknown setting {key!r}")
        out[target] = clean
    return out


def resolve(recipe_path: Path, output_directory: Path, repo_root: Path) -> dict[str, Any]:
    """Validate a recipe and return the job: every default filled in, every path absolute and hashed."""
    recipe_path = Path(recipe_path).resolve()
    try:
        recipe = json.loads(recipe_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as problem:
        raise GameReviewError(f"cannot read the recipe {recipe_path}: {problem}") from problem
    if recipe.get("schema") != RECIPE_SCHEMA:
        raise GameReviewError(f"recipe schema must be {RECIPE_SCHEMA}")
    known = {"schema", "name", "version", "source", "source_sha256", "skin_materials", "hair_materials", "bind",
             "hand_fit", "arm_joints", "hair_motion", "face", "teeth_look", "closed_lids", "mouth",
             "rigid_head_materials", "bake_morphs", "head_weights", "scatter_mask_m", "skin_look", "hair_look",
             "looks", "height_cm", "manny_refpose", "unreal", "notes"}
    unknown = sorted(set(recipe) - known)
    if unknown:
        raise GameReviewError(f"unknown recipe fields: {', '.join(unknown)}")
    name, version = recipe.get("name"), recipe.get("version")
    if not isinstance(name, str) or not _NAME.match(name):
        raise GameReviewError("name must be a CamelCase identifier such as Remora")
    if not isinstance(version, str) or not _VERSION.match(version):
        raise GameReviewError("version must look like V1, V2, ...")

    def locate(value: Any, label: str) -> Path:
        if not isinstance(value, str) or not value:
            raise GameReviewError(f"{label} must be a path")
        path = Path(value)
        for base in (recipe_path.parent, repo_root):
            candidate = path if path.is_absolute() else base / path
            if candidate.exists():
                return candidate.resolve()
        raise GameReviewError(f"{label} does not exist: {value}")

    source = locate(recipe.get("source"), "source")
    if source.suffix.lower() != ".glb":
        raise GameReviewError("source must be a .glb (the polished character)")
    source_hash = sha256(source)
    if recipe.get("source_sha256") and recipe["source_sha256"].lower() != source_hash:
        raise GameReviewError(f"source hash {source_hash} differs from the recipe's {recipe['source_sha256']}")
    skin = recipe.get("skin_materials")
    if not isinstance(skin, list) or not skin or not all(isinstance(s, str) and s for s in skin):
        raise GameReviewError("skin_materials must list the skin slot names (for example ['skin'])")
    hair = recipe.get("hair_materials", [])
    if not isinstance(hair, list) or not all(isinstance(s, str) and s for s in hair):
        raise GameReviewError("hair_materials must be a list of slot names (or omitted to match hair/scalp)")
    rigid = recipe.get("rigid_head_materials", list(RIGID_HEAD_MATERIALS))
    if not isinstance(rigid, list) or not all(isinstance(s, str) and s for s in rigid):
        raise GameReviewError("rigid_head_materials must be a list of name substrings")
    bake = recipe.get("bake_morphs", {})
    if not isinstance(bake, dict):
        raise GameReviewError("bake_morphs must map morph names to weights")
    bake = {str(k): _number(v, f"bake_morphs.{k}", -1.0, 1.0) for k, v in bake.items()}
    weights = dict(HEAD_WEIGHTS)
    for key, value in (recipe.get("head_weights") or {}).items():
        if key not in HEAD_WEIGHTS:
            raise GameReviewError(f"head_weights has an unknown setting {key!r}")
        weights[key] = _number(value, f"head_weights.{key}", 0.0, 0.3)
    head_chain(1.5, 1.7, weights)      # refuses a chain that does not step down
    bind = dict(BIND)
    for key, value in (recipe.get("bind") or {}).items():
        if key == "method":
            if value not in ("voxel_heat", "rig"):
                raise GameReviewError("bind.method must be voxel_heat or rig")
            bind[key] = value
        elif key == "voxel_m":
            bind[key] = _number(value, "bind.voxel_m", 0.002, 0.02)
        elif key == "shoulder_release_cm":      # collarbone weight on the upper arm moves to the arm (0 = off)
            bind[key] = _number(value, "bind.shoulder_release_cm", 0, 10)
        elif key == "hip_release_cm":           # thigh weight on the buttock moves to the pelvis (0 = off)
            bind[key] = _number(value, "bind.hip_release_cm", 0, 30)
        elif key == "hip_release_take":
            bind[key] = _number(value, "bind.hip_release_take", 0, 1)
        elif key == "layer_follow_mm":          # an outfit layer under another takes its weights (0 = off)
            bind[key] = _number(value, "bind.layer_follow_mm", 0, 30)
        elif key == "armhole_hold_cm":          # the outfit round a bare arm's shoulder stays with the torso (0 = off)
            bind[key] = _number(value, "bind.armhole_hold_cm", 0, 8)
        else:
            raise GameReviewError(f"bind has an unknown setting {key!r}")
    if bind["method"] != "voxel_heat":
        asked = [key for key in _VOXEL_ONLY if key != "hip_release_take" and (recipe.get("bind") or {}).get(key)]
        if asked:
            raise GameReviewError("bind.shoulder_release_cm, hip_release_cm, layer_follow_mm and armhole_hold_cm reshape "
                                  "the voxel_heat weights: use method voxel_heat")
        for key in _VOXEL_ONLY:      # the defaults are voxel_heat's; the rig's own weights are kept as they are
            bind.pop(key, None)
    motion = dict(HAIR_MOTION)
    for key, value in (recipe.get("hair_motion") or {}).items():
        if key == "enabled":
            if not isinstance(value, bool):
                raise GameReviewError("hair_motion.enabled must be true or false")
            motion[key] = value
        elif key in ("sway_m", "lift_m", "free_from_m", "free_at_m"):
            motion[key] = _number(value, f"hair_motion.{key}", 0.0, 0.2)
        else:
            raise GameReviewError(f"hair_motion has an unknown setting {key!r}")
    if motion["free_from_m"] >= motion["free_at_m"]:
        raise GameReviewError("hair_motion.free_from_m must be below free_at_m")
    face = {"mouth_morph_gain": dict(FACE["mouth_morph_gain"])}
    raw_face = recipe.get("face") or {}
    if not isinstance(raw_face, dict):
        raise GameReviewError("face must be an object (mouth_morph_gain)")
    for key, value in raw_face.items():
        if key != "mouth_morph_gain":
            raise GameReviewError(f"face has an unknown setting {key!r}")
        if not isinstance(value, dict) or not all(isinstance(k, str) and k for k in value):
            raise GameReviewError("face.mouth_morph_gain must map morph names to gains")
        face["mouth_morph_gain"] = {k: _number(v, f"face.mouth_morph_gain.{k}", 0.0, 4.0) for k, v in value.items()}
    lids = dict(CLOSED_LIDS)
    for key, value in (recipe.get("closed_lids") or {}).items():
        if key == "clear":
            if not (isinstance(value, bool) or value == "auto"):
                raise GameReviewError("closed_lids.clear must be true, false or auto")
            lids[key] = value
        elif key in ("stretch", "seen_open", "lash_band_m"):
            high = 0.01 if key == "lash_band_m" else 50.0
            if (not isinstance(value, list) or len(value) != 2
                    or not _number(value[0], f"closed_lids.{key}[0]", 0, high)
                    < _number(value[1], f"closed_lids.{key}[1]", 0, high)):
                raise GameReviewError(f"closed_lids.{key} must be [low, high] with low < high")
            lids[key] = [float(value[0]), float(value[1])]
        else:
            raise GameReviewError(f"closed_lids has an unknown setting {key!r}")
    mouth = dict(MOUTH)
    limits = {"show_m": (-0.005, 0.005), "tongue_follow": (0.0, 1.0), "max_shift_m": (0.0, 0.02),
              "rest_tolerance": (0.0, 0.1)}
    for key, value in (recipe.get("mouth") or {}).items():
        if key == "fit":
            if not (isinstance(value, bool) or value == "auto"):
                raise GameReviewError("mouth.fit must be true, false or auto")
            mouth[key] = value
        elif key in limits:
            mouth[key] = _number(value, f"mouth.{key}", *limits[key])
        else:
            raise GameReviewError(f"mouth has an unknown setting {key!r}")
    hand_fit = recipe.get("hand_fit", True)
    if not isinstance(hand_fit, bool):
        raise GameReviewError("hand_fit must be true or false")
    arm_joints = recipe.get("arm_joints", ARM_JOINTS_DEFAULT)
    if arm_joints not in ARM_JOINTS:
        raise GameReviewError(f"arm_joints must be one of {', '.join(ARM_JOINTS)}")
    mask = recipe.get("scatter_mask_m", list(SCATTER_MASK_M))
    if (not isinstance(mask, list) or len(mask) != 2
            or not 0 <= _number(mask[0], "scatter_mask_m[0]", 0, 0.2) < _number(mask[1], "scatter_mask_m[1]", 0, 0.2)):
        raise GameReviewError("scatter_mask_m must be [near, far] metres with near < far")
    skin_look = {**SKIN_LOOK, **(_look({"skin": recipe["skin_look"]}, "skin_look")["skin"]
                                 if recipe.get("skin_look") else {})}
    hair_look = {**HAIR_LOOK, **(_look({"hair": recipe["hair_look"]}, "hair_look")["hair"]
                                 if recipe.get("hair_look") else {})}
    teeth_look = {**TEETH_LOOK, **(_look({"teeth": recipe["teeth_look"]}, "teeth_look")["teeth"]
                                   if recipe.get("teeth_look") else {})}
    looks = {}
    for label, raw in (recipe.get("looks") or {}).items():
        if not _LOOK.match(label) or label == "default":
            raise GameReviewError(f"look name {label!r} must be lower_snake_case and not 'default'")
        looks[label] = _look(raw, label)
    if len(looks) > 6:
        raise GameReviewError("at most six looks per run (each adds a set of closeups)")
    height = recipe.get("height_cm", [150, 200])
    if (not isinstance(height, list) or len(height) != 2
            or not 10 <= _number(height[0], "height_cm[0]", 10, 400) < _number(height[1], "height_cm[1]", 10, 400)):
        raise GameReviewError("height_cm must be [low, high] centimetres")
    unreal = dict(UNREAL)
    for key, value in (recipe.get("unreal") or {}).items():
        if key not in UNREAL:
            raise GameReviewError(f"unreal has an unknown setting {key!r}")
        unreal[key] = value
    if unreal["animation_source"] not in ("manny", "player"):
        raise GameReviewError("unreal.animation_source must be manny or player")
    if not isinstance(unreal["glider_grip"], bool):
        raise GameReviewError("unreal.glider_grip must be true or false")
    unreal["retarget_pose"] = _retarget_pose(unreal["retarget_pose"])
    unreal["gait_style"] = _gait_style(unreal["gait_style"])
    unreal["climb_reach"] = _climb_reach(unreal["climb_reach"])
    if unreal["animation_source"] == "player" and (unreal["retarget_pose"] or unreal["gait_style"]):
        raise GameReviewError("unreal.retarget_pose and gait_style calibrate the Manny retargeter: "
                              "use animation_source manny")
    if unreal["game"] != "the_aether_wars":
        raise GameReviewError("only the_aether_wars is wired (its player Blueprint, installer and clips)")
    if not str(unreal["content_root"]).startswith("/Game/"):
        raise GameReviewError("unreal.content_root must be under /Game/")
    refpose = recipe.get("manny_refpose")
    refpose_path = (locate(refpose, "manny_refpose") if refpose
                    else (repo_root / "work" / "_unreal" / "manny_refpose.json").resolve())

    out = Path(output_directory).resolve()
    dest = f"{unreal['content_root'].rstrip('/')}/{name}/{version}"
    job = {
        "schema": JOB_SCHEMA,
        "recipe": str(recipe_path),
        "recipe_sha256": sha256(recipe_path),
        "name": name,
        "version": version,
        "tag": f"{name}{version}",
        "source": str(source),
        "source_sha256": source_hash,
        "skin_materials": skin,
        "hair_materials": hair,
        "rigid_head_materials": rigid,
        "bake_morphs": bake,
        "bind": bind,
        "hand_fit": hand_fit,
        "arm_joints": arm_joints,
        "hair_motion": motion,
        "face": face,
        "face_states": list(FACE_STATES),
        "visemes": list(VISEMES),
        "head_weights": weights,
        "scatter_mask_m": [float(mask[0]), float(mask[1])],
        "skin_look": skin_look,
        "hair_look": hair_look,
        "teeth_look": teeth_look,
        "closed_lids": lids,
        "mouth": mouth,
        "looks": looks,
        "height_cm": [float(height[0]), float(height[1])],
        "manny_refpose": str(refpose_path),
        "unreal": {**unreal, "dest": dest, "mesh": f"{dest}/SK_{name}_{version}"},
        "face_views": [list(v) for v in FACE_VIEWS],
        "body_views": [list(v) for v in BODY_VIEWS],
        "repo_root": str(Path(repo_root).resolve()),
        "output_directory": str(out),
        "paths": {
            "single": str(out / "01-single" / f"{name}_Single.glb"),
            "landmarks": str(out / "02-landmarks"),
            "rig": str(out / "02-rig"),
            "bound": str(out / "02-rig" / f"{name}_bound.blend"),
            "manny": str(out / "03-manny" / f"{name}_manny.blend"),
            "finish": str(out / "04-finish" / f"{name}_game.blend"),
            "fbx": str(out / "05-export" / f"{name}_{version}.fbx"),
            "textures": str(out / "05-export" / "textures"),
            "unreal": str(out / "06-unreal"),
            "closeups": str(out / "07-closeups"),
        },
        "notes": recipe.get("notes", ""),
    }
    return job


def same_rig_inputs(job: dict[str, Any], earlier: dict[str, Any]) -> list[str]:
    """What differs between two jobs in anything steps 01-04 read (empty: the earlier game blend can be reused)."""
    keys = ("source_sha256", "skin_materials", "hair_materials", "rigid_head_materials", "bake_morphs", "bind", "hand_fit",
            "hair_motion", "closed_lids", "mouth",
            "head_weights", "scatter_mask_m", "manny_refpose")
    differs = [key for key in keys if job.get(key) != earlier.get(key)]
    # a job from before the setting existed was rigged with the template elbow and wrist
    if job.get("arm_joints", ARM_JOINTS[0]) != earlier.get("arm_joints", ARM_JOINTS[0]):
        differs.append("arm_joints")
    return differs


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Resolve a game review recipe into its job file.")
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("resolve")
    one.add_argument("recipe", type=Path)
    one.add_argument("output_directory", type=Path)
    one.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    one.add_argument("--reuse-from", type=Path, help="an earlier attempt whose game blend may be reused")
    args = parser.parse_args(argv)
    try:
        job = resolve(args.recipe, args.output_directory, args.repo_root)
        if args.reuse_from:
            earlier = json.loads((args.reuse_from / "job.json").read_text(encoding="utf-8"))
            differs = same_rig_inputs(job, earlier)
            if differs:
                raise GameReviewError("cannot reuse " + str(args.reuse_from) + ": it differs in " + ", ".join(differs))
            job["reused_from"] = str(args.reuse_from.resolve())
    except GameReviewError as problem:
        print(f"RAC_ERROR {problem}", file=sys.stderr)
        return 2
    out = Path(job["output_directory"])
    out.mkdir(parents=True, exist_ok=True)
    (out / "job.json").write_text(json.dumps(job, indent=1), encoding="utf-8")
    print("GAME_REVIEW_JOB", out / "job.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
