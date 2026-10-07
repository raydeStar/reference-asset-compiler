"""How many triangles a runtime mesh should cost, decided from what the asset is.

A chest is not a throne and a coin is not a door, but every static object used
to inherit one number -- the profile's 100,000-triangle ceiling -- and a ceiling
read as a target gave a 1 m pipe the same budget as a 6 m door. The answer here
comes from two things any asset already has: a name, and a real size.

- The **role** says what kind of thing it is: a prop, a modular kit piece paid
  for every time it repeats, vegetation, a hero set piece, or a character. An
  explicit role always wins; otherwise the name decides, then the notes, then
  "prop".
- The **size class** comes from the longest real dimension. Characters ignore
  it: a character's **tier** (hero, boss, elite, regular enemy, NPC) says how
  close the camera holds it and how many share the screen, and the strict rig
  gate (``scripts/blender/gate_rig.py``) holds it to that tier's ceiling
  instead of its skeleton profile's flat ``tri_budget``.
- The surface gates scale with the object's diagonal, so a colossus is not held
  to a coin's tolerance, and the **ladder** says what to try next when they
  refuse a budget rather than shipping damage.

The table is `profiles/triangle-budgets.json`. This module uses only the
standard library and imports nothing from its own package, so Blender's
interpreter can load it by path (``scripts/blender/reduce_feature_qem.py``
does) and the rule exists once.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

POLICY_SCHEMA = "reference-asset-compiler.triangle-budgets.v1"
DECISION_SCHEMA = "reference-asset-compiler.triangle-budget.v1"
RELATIVE = Path("profiles") / "triangle-budgets.json"
PACKAGED = Path(__file__).resolve().parent / "data" / "triangle-budgets.json"


class BudgetError(ValueError):
    """A budget that cannot be decided, named rather than guessed at."""


def policy_path(repo_root: Path | None = None) -> Path:
    """The table this run decides from: a named checkout, this checkout, or the wheel's copy."""
    candidates = []
    if repo_root is not None:
        candidates.append(Path(repo_root) / RELATIVE)
    candidates.append(Path(__file__).resolve().parents[2] / RELATIVE)
    candidates.append(PACKAGED)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise BudgetError("No triangle budget table found; looked for {0}.".format(
        ", ".join(str(candidate) for candidate in candidates)))


def load_policy(repo_root: Path | None = None) -> tuple[dict[str, Any], Path]:
    path = policy_path(repo_root)
    policy = json.loads(path.read_text(encoding="utf-8-sig"))
    if policy.get("schema") != POLICY_SCHEMA:
        raise BudgetError("Unsupported triangle budget table schema in {0}".format(path))
    return policy, path


def tokens(text: str | None) -> list[str]:
    """Words in a name or note: 'crystal-hero-6m_cyan' -> crystal, hero, 6m, cyan."""
    return [word for word in re.split(r"[^a-z0-9]+", (text or "").lower()) if word]


def _elongation(dims: tuple[float, float, float] | None) -> float | None:
    if not dims:
        return None
    ordered = sorted(dims, reverse=True)
    return ordered[0] / ordered[1] if ordered[1] > 0 else math.inf


def classify(name: str, notes: str = "", role: str | None = None,
             policy: dict[str, Any] | None = None,
             dims_m: tuple[float, float, float] | None = None) -> tuple[str, str]:
    """The role an asset plays, and a sentence saying why.

    An explicit role wins. Otherwise the name decides; notes may only promote
    to the roles the table lets them (never down to something cheaper), and
    only through that role's notes_keywords: notes describe neighbours and
    parts ("independent leaves" of a door), so a role's broader name keywords
    would misfire there. A role with notes_min_size is reached from notes only
    when the asset is at least that big (a brazier "beside the throne" is not a
    hero piece). A role that requires a shape -- kit pieces must be long and
    thin -- is skipped, with the reason recorded, when the real dimensions say
    otherwise.
    """
    policy = policy or load_policy()[0]
    roles = policy["roles"]
    known = [entry["id"] for entry in roles]
    if role:
        wanted = role.strip().lower()
        if wanted not in known:
            raise BudgetError("Unknown role {0!r}; choose one of {1}.".format(
                role, ", ".join(known)))
        return wanted, "its role was given as {0}".format(wanted)
    promotable = set(policy.get("notes_may_promote_to", []))
    elongation = _elongation(dims_m)
    size_order = [entry["id"] for entry in policy["size_classes"]]
    size = size_class(max(dims_m), policy) if dims_m else None
    skipped: list[str] = []
    for source, words in (("name", tokens(name)), ("notes", tokens(notes))):
        for entry in roles:
            if source == "notes":
                if entry["id"] not in promotable:
                    continue
                at_least = entry.get("notes_min_size")
                if at_least and size and size_order.index(size) < size_order.index(at_least):
                    continue
            keywords = entry.get("notes_keywords", []) if source == "notes" else entry.get("keywords", [])
            for keyword in keywords:
                if keyword not in words:
                    continue
                needed = entry.get("require_elongation")
                if needed and elongation is not None and elongation < needed:
                    skipped.append("its {0} says '{1}', but it is not long and thin enough "
                                   "to be a {2} piece".format(source, keyword, entry["id"]))
                    break
                verb = "says" if source == "name" else "mention"
                return entry["id"], "its {0} {1} '{2}'".format(source, verb, keyword)
    if skipped:
        return "prop", skipped[0] + ", so it is a prop"
    return "prop", "nothing in its name or notes marks it as anything but a prop"


def _character_entry(policy: dict[str, Any]) -> dict[str, Any]:
    return next(entry for entry in policy["roles"] if entry["id"] == "character")


def character_tier(name: str = "", tier: str | None = None,
                   policy: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
    """A character's tier, and a sentence saying why.

    A given tier wins and an unknown one is refused by name. Otherwise a word
    in the name picks one ('ennix-hero', 'goblin-grunt'); with neither, there
    is no tier and the skeleton profile's flat ceiling still applies.
    """
    policy = policy or load_policy()[0]
    tiers = _character_entry(policy).get("tiers", [])
    if tier:
        wanted = tier.strip().lower()
        for entry in tiers:
            if entry["id"] == wanted:
                return entry, "its tier was given as {0}".format(wanted)
        raise BudgetError("Unknown character tier {0!r}; choose one of {1}.".format(
            tier, ", ".join(entry["id"] for entry in tiers)))
    words = tokens(name)
    for entry in tiers:
        for keyword in entry.get("keywords", []):
            if keyword in words:
                return entry, "its name says '{0}'".format(keyword)
    return None, "nothing in its name gives it a tier"


def rig_gate_budget(profile: dict[str, Any], tier: str | None = None,
                    repo_root: Path | None = None) -> dict[str, Any]:
    """The triangle ceiling the strict rig gate holds a skinned asset to.

    ``tier`` (or the profile's ``character_tier``, which a recipe can fold in
    as it folds in a waiver) replaces the skeleton profile's flat
    ``tri_budget`` with the top of that tier's range. Without one the flat
    number stays, so nothing gets more triangles until someone says what it
    is. The waiver rule is the gate's and is unchanged.
    """
    wanted = tier or profile.get("character_tier")
    flat = profile.get("tri_budget")
    flat_text = "{0:,}".format(flat) if flat is not None else "none"
    if not wanted:
        return {"tri_budget": flat, "source": "skeleton_profile", "character_tier": None,
                "summary": "No character tier is declared, so the skeleton profile's flat "
                           "tri_budget ({0}) applies.".format(flat_text)}
    policy, path = load_policy(repo_root)
    entry, reason = character_tier(tier=wanted, policy=policy)
    floor, ceiling = (int(value) for value in entry["range"])
    return {
        "tri_budget": ceiling,
        "source": "character_tier",
        "character_tier": {
            "id": entry["id"],
            "reason": reason,
            "triangles": int(entry["triangles"]),
            "range": [floor, ceiling],
            "counts": _character_entry(policy).get("counts"),
        },
        "replaces_profile_tri_budget": flat,
        "summary": "A {0} character: at most {1:,} triangles at LOD0 (about {2:,}; the tier "
                   "runs {3:,}-{1:,}), in place of the skeleton profile's flat {4}.".format(
                       entry["id"], ceiling, int(entry["triangles"]), floor, flat_text),
        "policy": {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()},
    }


def size_class(longest_m: float, policy: dict[str, Any] | None = None) -> str:
    policy = policy or load_policy()[0]
    for entry in policy["size_classes"]:
        limit = entry.get("below_longest_m")
        if limit is None or longest_m < limit:
            return entry["id"]
    return policy["size_classes"][-1]["id"]


def _round_budget(value: float) -> int:
    return int(max(100, round(value / 100.0) * 100))


def _check_dimensions(dims_m: Iterable[float]) -> tuple[float, float, float]:
    values = tuple(float(value) for value in dims_m)
    if len(values) != 3 or not all(math.isfinite(value) and value >= 0 for value in values):
        raise BudgetError("Dimensions must be three finite, non-negative lengths in metres.")
    if max(values) <= 0:
        raise BudgetError("An object with no extent has no size to budget for.")
    return values  # type: ignore[return-value]


def decide(name: str, dims_m: Iterable[float], role: str | None = None, notes: str = "",
           source_triangles: int | None = None,
           repo_root: Path | None = None, tier: str | None = None) -> dict[str, Any]:
    """The triangle budget, surface gates and fallback ladder for one asset.

    A character's budget comes from its tier (given, or a word in its name);
    a character with no tier has ``triangle_budget`` None and keeps its
    skeleton profile's flat ceiling. A given tier makes the asset a character.
    ``keep_source`` is True when the source is already within reach of the
    budget, so reducing it would cost more than it saves.
    """
    policy, path = load_policy(repo_root)
    dims = _check_dimensions(dims_m)
    longest = max(dims)
    diagonal = math.sqrt(sum(value * value for value in dims))
    if tier and not role:
        role_id, reason = "character", "its tier was given as {0}".format(tier.strip().lower())
    else:
        role_id, reason = classify(name, notes, role, policy, dims)
    if tier and role_id != "character":
        raise BudgetError("A tier budgets a character; {0!r} is a {1}.".format(name, role_id))
    size = size_class(longest, policy)
    entry = next(item for item in policy["roles"] if item["id"] == role_id)

    deviation = policy["deviation"]
    maximum_p99 = max(deviation["p99_floor_m"], deviation["p99_fraction_of_diagonal"] * diagonal)
    maximum_max = max(deviation["max_floor_m"], deviation["max_fraction_of_diagonal"] * diagonal)

    budget: int | None
    floor: int | None = None
    ceiling: int | None = None
    tier_entry: dict[str, Any] | None = None
    tier_reason: str | None = None
    if role_id == "character":
        tier_entry, tier_reason = character_tier(name, tier, policy)
    if tier_entry is not None:
        budget = int(tier_entry["triangles"])
        floor, ceiling = (int(value) for value in tier_entry["range"])
        summary = ("A {0} character: about {1:,} triangles, {2:,}-{3:,} at LOD0 "
                   "with groom strands excluded.".format(tier_entry["id"], budget, floor, ceiling))
    elif entry.get("per_metre"):
        rule = entry["per_metre"]
        budget = _round_budget(min(rule["cap"], rule["base"] + rule["per_metre"] * longest))
        summary = "A modular piece {0:.1f} m long: about {1:,} triangles.".format(longest, budget)
    elif entry.get("budgets"):
        budget = int(entry["budgets"][size])
        noun = {"prop": "prop", "hero": "hero piece", "vegetation": "plant"}.get(role_id, role_id)
        summary = "A {0} {1}: about {2:,} triangles.".format(size, noun, budget)
    else:
        budget = None
        summary = ("A character with no tier keeps its skeleton profile's flat ceiling; "
                   "give it one of {0} to budget it here.".format(
                       ", ".join(item["id"] for item in entry.get("tiers", []))))

    ladder_rule = policy["ladder"]
    ladder: list[int] = []
    keep_source = False
    if budget is not None:
        budget = max(int(ladder_rule["minimum_budget"]), budget)
        rung = budget
        while len(ladder) < int(ladder_rule["maximum_rungs"]):
            ladder.append(rung)
            rung = _round_budget(rung * float(ladder_rule["factor"]))
        if ceiling is not None:
            # A tier's ceiling is the gate's: the ladder may climb to it, never past.
            ladder = [value for value in ladder if value < ceiling] + [ceiling]
        if source_triangles:
            near_source = float(ladder_rule["keep_source_above_fraction"]) * int(source_triangles)
            ladder = [rung for rung in ladder if rung < near_source]
            if not ladder and ceiling is not None and int(source_triangles) > ceiling:
                # Near the source is not near enough when the source is over the gate.
                ladder = [ceiling]
            keep_source = not ladder
            if keep_source:
                summary += " The source ({0:,}) is already close enough; keep it.".format(
                    int(source_triangles))

    return {
        "schema": DECISION_SCHEMA,
        "name": name,
        "role": role_id,
        "role_reason": reason,
        "tier": tier_entry["id"] if tier_entry else None,
        "tier_reason": tier_reason,
        "size_class": size,
        "dimensions_m": [round(value, 4) for value in dims],
        "longest_m": round(longest, 4),
        "diagonal_m": round(diagonal, 4),
        "triangle_budget": budget,
        "triangle_floor": floor,
        "triangle_ceiling": ceiling,
        "maximum_p99_m": round(maximum_p99, 5),
        "maximum_max_m": round(maximum_max, 5),
        "ladder": ladder,
        "source_triangles": int(source_triangles) if source_triangles else None,
        "keep_source": keep_source,
        "summary": summary,
        "policy": {
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
    }
