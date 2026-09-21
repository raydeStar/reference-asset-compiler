"""How a model is cut into parts, and what each part currently reads as.

One place, because two scripts need the same answer and two copies would agree
until the day they did not: the survey that says what a model's parts are, and
the stage that assigns surfaces to them, have to cut it up identically or a
proposal would name a part that does not exist.

Parts are named the way somebody points at them -- a colour family, where that
colour sits in value, and optionally a band of the model's height. Nothing here
imports the compiler package, because a Blender script cannot.
"""

from __future__ import annotations

import colorsys
import json
import statistics
from pathlib import Path

import numpy as np

# Nothing here imports mathutils or bpy at module level, because these tables
# and the judgement below are exercised by tests that have no Blender. The only
# thing mathutils was ever used for was adding up two floats.

ROOT = Path(__file__).resolve().parents[2]
HUES = ROOT / "profiles" / "colours" / "hue-families.json"
RECIPES = ROOT / "profiles" / "materials" / "recipes.json"


def load_tables():
    hue_table = json.loads(HUES.read_text(encoding="utf-8-sig"))
    recipe_table = json.loads(RECIPES.read_text(encoding="utf-8-sig"))
    families = {entry["colour"]: tuple(entry["span"]) for entry in hue_table["families"]}
    minimum_saturation = float(hue_table.get("minimum_saturation", 0.12))
    recipes = {entry["name"]: entry for entry in recipe_table["recipes"]}
    tones = {name: tuple(span) for name, span in recipe_table["tones"].items() if name != "note"}
    return families, minimum_saturation, recipes, tones


def in_family(hue: float, span) -> bool:
    low, high = span
    # A family may wrap past 1.0, because red does.
    return low <= hue <= high or low <= hue + 1.0 <= high


def bound_image(material, socket_name):
    """The image feeding one input, if anything is.

    Matched by name rather than by object identity. Blender hands out a fresh
    Python wrapper for the same underlying socket each time it is asked, so
    comparing with `is` finds nothing even when it is the same socket.
    """
    for link in material.node_tree.links:
        if link.to_socket.name != socket_name:
            continue
        node = link.from_node
        if node.type == "SEPARATE_COLOR":
            for inner in material.node_tree.links:
                if inner.to_node.name == node.name and inner.from_node.type == "TEX_IMAGE":
                    return inner.from_node.image
        if node.type == "TEX_IMAGE":
            return node.image
    return None


def base_colour_image(material):
    tree = material.node_tree
    for link in tree.links:
        if link.to_socket.name == "Base Color":
            node = link.from_node
            if node.type == "TEX_IMAGE" and node.image:
                return node.image
    return next((n.image for n in tree.nodes if n.type == "TEX_IMAGE" and n.image), None)


def pixels_of(image):
    if image is None or not image.size[0] or not image.size[1]:
        return None
    return np.asarray(image.pixels[:], dtype=np.float32).reshape(image.size[1], image.size[0], 4)


def part_of(red, green, blue, families, minimum_saturation, tones):
    """Which part one painted texel belongs to: a colour family and a tone.

    Pulled out of the mesh walk because it is the judgement, and the mesh walk
    is only bookkeeping. A sword's body and the stone at its throat are both
    blue; without the tone half of this, one recipe swallows the other and
    nothing says why.
    """
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    family = "grey" if saturation < minimum_saturation else next(
        (name for name, span in families.items() if in_family(hue, span)), None)
    tone = next((name for name, (low, high) in tones.items() if low <= value < high), "bright")
    return family, tone


def nearest_recipe(recipes, roughness, metallic, transmission=0.0):
    """The named surface these measurements are nearest to.

    Said in the same words a caller uses to ask for one, so judging a part is a
    comparison -- is this what it should be? -- rather than an invention. A
    reviewer asked to invent roughness values from a picture will invent them
    badly; one asked whether "rough metal" is right for a crystal blade is
    doing something a person or a vision model does well.

    Metallic is weighted hardest because it is the one thing no adjustment
    recovers from: metal does not transmit light at all, so a crystal marked
    metallic can never be made to read as a crystal however it is tuned.
    """
    if roughness is None or metallic is None:
        return None
    best, distance = None, None
    for entry in recipes.values():
        cost = (4.0 * abs(entry.get("metallic", 0.0) - metallic)
                + abs(entry.get("roughness", 0.5) - roughness)
                + 2.0 * abs(entry.get("transmission", 0.0) - transmission))
        if distance is None or cost < distance:
            best, distance = entry["name"], cost
    return best


class Surface:
    """A mesh cut into named parts, with what each part is currently made of."""

    def __init__(self, mesh_object):
        self.object = mesh_object
        self.mesh = mesh_object.data
        self.families, self.minimum_saturation, self.recipes, self.tones = load_tables()

        self.material = self.mesh.materials[0]
        self.albedo = pixels_of(base_colour_image(self.material))
        orm_image = (bound_image(self.material, "Roughness")
                     or bound_image(self.material, "Metallic"))
        self.orm = pixels_of(orm_image)
        self.uv = self.mesh.uv_layers.active.data

        heights = [(mesh_object.matrix_world @ vertex.co).z for vertex in self.mesh.vertices]
        self.floor, self.ceiling = min(heights), max(heights)
        self.span = (self.ceiling - self.floor) or 1.0

    def uv_centre(self, polygon):
        u = v = 0.0
        for loop in polygon.loop_indices:
            uv = self.uv[loop].uv
            u += uv[0]
            v += uv[1]
        count = len(polygon.loop_indices)
        return (u / count, v / count)

    def elevation(self, polygon) -> float:
        """Where this face sits between the model's foot and its crown."""
        return ((self.object.matrix_world @ polygon.center).z - self.floor) / self.span

    def sample(self, plane, centre):
        if plane is None:
            return None
        rows, columns = plane.shape[0], plane.shape[1]
        x = min(columns - 1, max(0, int(centre[0] * columns)))
        y = min(rows - 1, max(0, int(centre[1] * rows)))
        return plane[y, x]

    def classify(self, polygon):
        """The colour family and tone this face was painted, or None."""
        centre = self.uv_centre(polygon)
        texel = self.sample(self.albedo, centre)
        if texel is None:
            return None, None, centre
        family, tone = part_of(*(float(v) for v in texel[:3]),
                               self.families, self.minimum_saturation, self.tones)
        return family, tone, centre

    def measure(self, centres, elevations):
        """What these faces are currently made of, read from the paint itself."""
        summary = {}
        if elevations:
            summary["height_range"] = [round(min(elevations), 3), round(max(elevations), 3)]
        if self.orm is not None and centres:
            rough = [float(self.sample(self.orm, centre)[1]) for centre in centres]
            metal = [float(self.sample(self.orm, centre)[2]) for centre in centres]
            summary["roughness_median"] = round(statistics.median(rough), 4)
            summary["metallic_median"] = round(statistics.median(metal), 4)
        return summary

    def reads_as(self, roughness, metallic, transmission=0.0):
        return nearest_recipe(self.recipes, roughness, metallic, transmission)

    def parts(self, minimum_share: float = 0.004):
        """Every part worth naming, with what it is currently made of."""
        groups: dict[tuple, dict] = {}
        for polygon in self.mesh.polygons:
            family, tone, centre = self.classify(polygon)
            if family is None:
                continue
            group = groups.setdefault((family, tone), {"faces": [], "centres": [], "heights": []})
            group["faces"].append(polygon.index)
            group["centres"].append(centre)
            group["heights"].append(self.elevation(polygon))

        total = max(len(self.mesh.polygons), 1)
        found = []
        for (family, tone), group in groups.items():
            share = len(group["faces"]) / total
            if share < minimum_share:
                continue
            measured = self.measure(group["centres"], group["heights"])
            found.append({
                "part": "{0}:{1}".format(family, tone),
                "colour": family,
                "tone": tone,
                "faces": len(group["faces"]),
                "share": round(share, 5),
                **measured,
                "reads_as": self.reads_as(
                    measured.get("roughness_median"), measured.get("metallic_median")),
            })
        found.sort(key=lambda entry: entry["share"], reverse=True)
        return found
