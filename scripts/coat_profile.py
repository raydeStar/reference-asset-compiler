"""A character profile's `coat` block: coat-tail bone chains for a game's cloth physics.

A long coat (knee length) cannot follow the thighs: it needs bones of its own
that the game simulates. scripts/blender/add_coat_chains.py adds them to the
Manny-conformant UE5 blend, skins the coat to them and exports the FBX;
rebuild_character.py runs it when the profile has this block. No block, no
coat: the character's UE5 export is the plain one.

  "coat": {
    "chains": {"front_l": 25, "front_r": -25, "back_l": 150, "back_r": -150},
    "bones_per_chain": 3,
    "top_below_pelvis_m": 0.04,
    "hem_above_knee_m": 0.0,
    "leg_clearance_m": 0.12,
    "open_front": false,
    "top_blend_m": null
  }

Every key is optional (an empty block is the four chains above):

chains             name -> degrees around the body, measured from straight
                   ahead (-Y) toward the character's left (+X): front_l 25 is
                   25 degrees left of the front, back_r -150 is 30 degrees
                   right of the back, side_l 90 is the left hip. A name is
                   <group>_<l|r>; it becomes bones coat_<group>_01_<side> ...
                   coat_<group>_<NN>_<side> plus a non-deforming leaf
                   coat_<group>_end_<side>. Each chain's _01 hangs from pelvis.
bones_per_chain    deforming bones per chain (3: about 15 cm each, belt to knee).
top_below_pelvis_m the chain roots' height: this far below the pelvis joint,
                   just under the belt.
hem_above_knee_m   the hem's height above the knee (the calf joints); negative
                   is below the knee. Or hem_z_m: the hem's absolute height
                   (feet on z=0). Give one, not both. A coat that ends above
                   the knee needs it: at the knee the hem rays only meet the
                   trouser legs. The coat receipt's coat_bottom_z_m (per
                   chain) says where the coat really ends, even when no hem
                   was found.
leg_clearance_m    a vertex is coat when it stands further than this from the
                   nearest leg axis (thigh, calf, foot); closer is trousers or
                   boots and keeps its weights. Full coat weight 3 cm beyond.
open_front         true for a coat open at the front: no vertex blends across
                   the front centre line, so each front panel follows only its
                   own side's chain.
top_blend_m        how far below the roots the coat hands over from the
                   pelvis/thigh weights to the chains (null: one segment).

Read by add_coat_chains.py by path (Blender's Python cannot import the
package) and by rebuild_character.py, which checks the block before a build.
"""
from __future__ import annotations

import re

DEFAULTS = {
    "chains": {"front_l": 25.0, "front_r": -25.0, "back_l": 150.0, "back_r": -150.0},
    "bones_per_chain": 3,
    "top_below_pelvis_m": 0.04,
    "hem_above_knee_m": 0.0,
    "hem_z_m": None,
    "leg_clearance_m": 0.12,
    "open_front": False,
    "top_blend_m": None,
}
CHAIN_NAME = re.compile(r"^([a-z][a-z0-9]*)_([lr])$")


def resolve_coat(block):
    """The block with its defaults filled in, or None when there is no coat.

    Raises ValueError on anything a build should not start with.
    """
    if block is None:
        return None
    if not isinstance(block, dict):
        raise ValueError("The profile's coat block must be an object, not {0!r}.".format(block))
    unknown = sorted(k for k in block if k not in DEFAULTS and not k.startswith("_"))
    if unknown:
        raise ValueError("Unknown coat keys: {0} (known: {1}).".format(
            ", ".join(unknown), ", ".join(DEFAULTS)))
    if "hem_z_m" in block and "hem_above_knee_m" in block:
        raise ValueError("Give the coat's hem as hem_z_m or hem_above_knee_m, not both.")
    coat = {key: block.get(key, value) for key, value in DEFAULTS.items()}
    chains = coat["chains"]
    if not isinstance(chains, dict) or not chains:
        raise ValueError("The coat needs at least one chain (chains: {name: degrees}).")
    resolved = {}
    for name, degrees in chains.items():
        match = CHAIN_NAME.match(name)
        if not match or match.group(1) == "end":
            raise ValueError("Coat chain {0!r}: name it <group>_l or <group>_r, e.g. front_l.".format(name))
        if isinstance(degrees, bool) or not isinstance(degrees, (int, float)) or not -180 <= degrees <= 180:
            raise ValueError("Coat chain {0!r}: degrees must be a number in [-180, 180].".format(name))
        resolved[name] = float(degrees)
    angles = sorted(a % 360.0 for a in resolved.values())
    if len(set(angles)) != len(angles):
        raise ValueError("Two coat chains share an angle.")
    coat["chains"] = resolved
    bones = coat["bones_per_chain"]
    if isinstance(bones, bool) or not isinstance(bones, int) or not 1 <= bones <= 99:
        raise ValueError("bones_per_chain must be a whole number from 1 to 99.")
    for key in ("top_below_pelvis_m", "hem_above_knee_m", "leg_clearance_m"):
        if not isinstance(coat[key], (int, float)) or isinstance(coat[key], bool):
            raise ValueError("Coat {0} must be a number of metres.".format(key))
    for key in ("hem_z_m", "top_blend_m"):
        if coat[key] is not None and (not isinstance(coat[key], (int, float)) or coat[key] <= 0):
            raise ValueError("Coat {0} must be a positive number of metres or null.".format(key))
    if coat["leg_clearance_m"] <= 0:
        raise ValueError("Coat leg_clearance_m must be positive.")
    if not isinstance(coat["open_front"], bool):
        raise ValueError("Coat open_front must be true or false.")
    return coat


def bone_names(chain, bones_per_chain):
    """A chain's bones, root first: the deforming ones, then the non-deforming leaf."""
    group, side = CHAIN_NAME.match(chain).groups()
    return (["coat_{0}_{1:02d}_{2}".format(group, i + 1, side) for i in range(bones_per_chain)]
            + ["coat_{0}_end_{1}".format(group, side)])
