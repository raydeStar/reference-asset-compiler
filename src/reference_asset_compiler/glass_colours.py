"""The colour families a person can name, read from the one table that holds them.

Nothing in a mesh says which of its faces are glass: a pane and the frame around
it are the same surface. What says so is the paint, so a caller names the colour
its glass was painted and the faces wearing that colour get a material that
transmits.

The table lives in `profiles/colours/hue-families.json` rather than in this
file, because the Blender stage that applies it cannot import this package --
it runs inside Blender's own interpreter. One table read twice beats two tables
that agree until the day they do not.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .resources import checkout_root

SCHEMA = "reference-asset-compiler.hue-families.v1"
RELATIVE = Path("profiles") / "colours" / "hue-families.json"


class GlassColourError(ValueError):
    """A colour that cannot be resolved, named rather than guessed at."""


def _table(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or checkout_root()
    if root is None:
        raise GlassColourError(
            "The colour families live in a checkout; pass --repo-root to reach them.")
    path = root / RELATIVE
    if not path.is_file():
        raise GlassColourError("This checkout has no {0}.".format(RELATIVE.as_posix()))
    table = json.loads(path.read_text(encoding="utf-8-sig"))
    if table.get("schema") != SCHEMA:
        raise GlassColourError("Unsupported colour family table schema")
    return table


def named_colours(repo_root: Path | None = None) -> list[dict[str, Any]]:
    """Every colour a caller may name, with what it means."""
    return [
        {"colour": family["colour"], "description": family["description"]}
        for family in _table(repo_root)["families"]
    ]


def resolve_colour(colour: str, repo_root: Path | None = None) -> dict[str, Any]:
    """The hue span a named colour means, refused by name if it is not one."""
    families = {family["colour"]: family for family in _table(repo_root)["families"]}
    found = families.get(str(colour).strip().lower())
    if found is None:
        raise GlassColourError(
            "Unknown colour {0!r}. Name the colour the glass was painted: {1}.".format(
                colour, ", ".join(sorted(families))))
    return found
