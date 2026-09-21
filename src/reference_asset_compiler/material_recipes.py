"""Named surfaces, and the colour-and-tone parts they get assigned to.

A caller asks for a kind of material -- crystal, brushed metal, leather -- and
not for a set of numbers. The numbers are here, in one table both sides read,
so that a name means the same thing to whoever offers it and whoever applies
it. Two copies would agree until the day they did not.

Parts are named the way a person would point at them: a colour family, and
optionally where it sits in value. A sword's deep blue body and the bright
stone at its throat are both blue, and tone is what tells them apart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .resources import checkout_root

RELATIVE = Path("profiles") / "materials" / "recipes.json"


class MaterialRecipeError(ValueError):
    """A recipe or a part nobody can act on."""


def table_path(repo_root: Path | None = None) -> Path:
    root = repo_root or checkout_root()
    if root is None:
        raise MaterialRecipeError(
            "Material recipes live in the pipeline checkout: pass --repo-root pointing to one.")
    return root / RELATIVE


def load_table(repo_root: Path | None = None) -> dict[str, Any]:
    path = table_path(repo_root)
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as problem:
        raise MaterialRecipeError(
            "The material recipe table could not be read: {0}".format(problem)) from problem


def named_recipes(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Every surface a caller may ask for, in the order the table lists them."""
    table = load_table(repo_root)
    return [
        {
            "recipe": entry["name"],
            "description": entry.get("description", ""),
            "metallic": entry.get("metallic"),
            "roughness": entry.get("roughness"),
            "transmission": entry.get("transmission", 0.0),
        }
        for entry in table.get("recipes", [])
    ]


def named_tones(repo_root: Path | None = None) -> list[str]:
    table = load_table(repo_root)
    return [name for name in table.get("tones", {}) if name != "note"]


def resolve_recipe(name: str, repo_root: Path | None = None) -> dict[str, Any]:
    """The numbers behind one name, or a refusal that lists what there is."""
    wanted = (name or "").strip().lower()
    table = load_table(repo_root)
    for entry in table.get("recipes", []):
        if entry["name"] == wanted:
            return dict(entry)
    raise MaterialRecipeError(
        "There is no {0!r} surface. There is: {1}.".format(
            name, ", ".join(entry["name"] for entry in table.get("recipes", []))))


def parse_assignment(text: str, repo_root: Path | None = None) -> dict[str, Any]:
    """Reads one `colour[:tone]=recipe` into the part and surface it names.

    Refused here rather than inside Blender, so a caller hears about a colour
    or a surface nobody offers in their own terms and before anything runs.
    """
    raw = (text or "").strip()
    if raw.count("=") != 1:
        raise MaterialRecipeError(
            "An assignment reads colour[:tone]=surface, for example blue:dark=crystal. Got {0!r}.".format(text))
    part, recipe = (half.strip().lower() for half in raw.split("="))
    if not part or not recipe:
        raise MaterialRecipeError(
            "An assignment names a part and a surface, for example blue:dark=crystal. Got {0!r}.".format(text))
    if part.count(":") > 1:
        raise MaterialRecipeError(
            "A part is a colour and at most one tone, for example blue:dark. Got {0!r}.".format(part))
    colour, _, tone = part.partition(":")
    tones = named_tones(repo_root)
    if tone and tone not in tones:
        raise MaterialRecipeError(
            "There is no {0!r} tone. There is: {1}.".format(tone, ", ".join(tones)))
    resolved = resolve_recipe(recipe, repo_root)
    return {
        "colour": colour,
        "tone": tone or None,
        "recipe": resolved["name"],
        "values": {key: resolved[key] for key in ("metallic", "roughness", "transmission", "ior")
                   if key in resolved},
    }
