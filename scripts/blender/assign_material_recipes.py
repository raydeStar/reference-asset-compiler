"""Give the parts a painter painted the kind of surface they are supposed to be.

A painter answers in one material. The whole sword arrives as a single opaque
surface: the deep blue body, the bright stone at its throat and the grey grip
are all the same material as far as the mesh is concerned, and all of them
inherit whatever the paint's own roughness and metallic maps happened to say.
On one real asset that was metallic 0.99 across 72% of the surface -- so the
blade, the edges and the gem were all being rendered as rough metal. Metal
cannot transmit light, which is why no amount of adjustment would ever have
made that stone read as a stone.

What says which part is which is the paint. So faces are chosen by the colour
they were given, in a family a person can name, and by where that colour sits
in value -- because a sword's body and its gem are both blue, and tone is what
tells them apart. Each part is then handed a named surface from the compiler's
own table.

The one thing this has to get right, and the one thing that would fail
silently: a texture bound to Roughness or Metallic beats any value set beside
it. A recipe that sets those without unbinding the map does nothing at all and
reports success. So the maps it overrides are disconnected, and the report says
which ones were.

Nothing here moves a vertex, touches a UV, or repaints anything. It changes
which material each face points at, and what those materials say about light.

Usage:
  blender -b --factory-startup --python scripts/blender/assign_material_recipes.py \
      -- <painted.glb> <output.glb> <report.json> \
         --assign blue:dark=crystal --assign cyan:bright=gemstone [--minimum-share 0.004]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
# One place cuts a model into parts. The survey that names them and the stage
# that assigns surfaces to them have to agree exactly, or a proposal would name
# a part this does not produce.
from surface_parts import Surface  # noqa: E402

# Which Principled input each recipe value drives, and therefore which bound
# map has to be let go of for the value to mean anything.
INPUTS = {
    "metallic": "Metallic",
    "roughness": "Roughness",
    "transmission": "Transmission Weight",
    "ior": "IOR",
}


def read_options(argv, name):
    """Every value given for a repeatable flag, in the order they were given."""
    found = []
    for index, item in enumerate(argv):
        if item == name and index + 1 < len(argv):
            found.append(argv[index + 1])
    return found


def read_option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [item for index, item in enumerate(argv)
                  if not item.startswith("--")
                  and (index == 0 or not argv[index - 1].startswith("--"))]
    if len(positional) < 3:
        print("[SURFACE] FAILED: expected <source> <output.glb> <report.json> --assign colour[:tone]=surface")
        return 2

    source, output, report_path = (Path(positional[0]), Path(positional[1]), Path(positional[2]))
    requested = read_options(argv, "--assign")
    minimum_share = float(read_option(argv, "--minimum-share", "0.004"))
    if not requested:
        print("[SURFACE] FAILED: name at least one part and its surface, "
              "for example --assign blue:dark=crystal")
        return 1
    if not source.is_file():
        print("[SURFACE] FAILED: source does not exist: {0}".format(source))
        return 1
    if output.exists():
        print("[SURFACE] FAILED: refusing to overwrite {0}".format(output))
        return 1

    try:
        from surface_parts import load_tables
        families, _, recipes, tones = load_tables()
    except (OSError, ValueError) as problem:
        print("[SURFACE] FAILED: a profile table could not be read: {0}".format(problem))
        return 1

    assignments = []
    for text in requested:
        part, _, recipe = text.strip().lower().partition("=")
        # Some parts colour cannot reach. The stone at a sword's throat and the
        # bright edge down its blade are painted the same, because to a painter
        # they are the same material. Where they are is what separates them.
        part, _, band_text = part.partition("@")
        band = None
        if band_text:
            try:
                low, high = (float(half) for half in band_text.split("-"))
            except ValueError:
                print("[SURFACE] FAILED: a height band is two fractions, low-high, "
                      "for example @0.7-0.85. Got {0!r}".format(band_text))
                return 1
            if not 0.0 <= low < high <= 1.0:
                print("[SURFACE] FAILED: a height band runs from low to high within 0 and 1. "
                      "Got {0!r}".format(band_text))
                return 1
            band = (low, high)
        colour, _, tone = part.partition(":")
        if recipe not in recipes:
            print("[SURFACE] FAILED: there is no {0!r} surface. There is: {1}.".format(
                recipe, ", ".join(sorted(recipes))))
            return 1
        if colour not in families and colour != "grey":
            print("[SURFACE] FAILED: there is no {0!r} colour. There is: {1}, grey.".format(
                colour, ", ".join(sorted(families))))
            return 1
        if tone and tone not in tones:
            print("[SURFACE] FAILED: there is no {0!r} tone. There is: {1}.".format(
                tone, ", ".join(sorted(tones))))
            return 1
        assignments.append({"colour": colour, "tone": tone or None,
                            "band": band, "recipe": recipe})

    keys = [(entry["colour"], entry["tone"], entry["band"]) for entry in assignments]
    if len(set(keys)) != len(keys):
        print("[SURFACE] FAILED: the same part is named twice, so which surface wins would be an accident")
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        print("[SURFACE] FAILED: expected one mesh object, found {0}".format(len(meshes)))
        return 1

    mesh_object = meshes[0]
    mesh = mesh_object.data
    if not mesh.materials:
        print("[SURFACE] FAILED: the mesh carries no material to read")
        return 1
    if not mesh.uv_layers.active:
        print("[SURFACE] FAILED: the mesh has no UVs, so its paint cannot be read per face")
        return 1

    painted = mesh.materials[0]
    surface_of = Surface(mesh_object)
    if surface_of.albedo is None:
        print("[SURFACE] FAILED: the material has no base colour image to read")
        return 1

    wanted = {(entry["colour"], entry["tone"], entry["band"]): entry for entry in assignments}
    chosen: dict[tuple, list[int]] = {key: [] for key in wanted}
    centres: dict[tuple, list] = {key: [] for key in wanted}
    heights: dict[tuple, list] = {key: [] for key in wanted}
    # Most specific first, always, rather than whichever happened to be listed
    # last: a caller naming blue, blue:bright and blue:bright@0.7-0.85 should
    # get the answer they would have predicted.
    order = sorted(wanted, key=lambda key: (key[2] is not None, key[1] is not None), reverse=True)
    for polygon in mesh.polygons:
        family, tone, centre = surface_of.classify(polygon)
        if family is None:
            continue
        # Not `height`: that name already belongs to the base colour image's
        # own height, which classify() closes over. Reusing it turned an image
        # row index into a fraction on the second face.
        elevation = surface_of.elevation(polygon)
        key = next((candidate for candidate in order
                    if candidate[0] == family
                    and (candidate[1] is None or candidate[1] == tone)
                    and (candidate[2] is None or candidate[2][0] <= elevation <= candidate[2][1])), None)
        if key is None:
            continue
        chosen[key].append(polygon.index)
        centres[key].append(centre)
        heights[key].append(elevation)

    total = max(len(mesh.polygons), 1)
    for key, entry in wanted.items():
        share = len(chosen[key]) / total
        if share < minimum_share:
            # Finding almost nothing means the named part is not on this model.
            # Changing four faces and reporting success would be worse than
            # saying so, because the caller would believe it had worked.
            name = key[0] + (":" + key[1] if key[1] else "") + (
                "@{0}-{1}".format(*key[2]) if key[2] else "")
            print("[SURFACE] FAILED: {0} is {1:.2%} of this model's faces, which is not a part. "
                  "Name a part it actually has.".format(name, share))
            return 1

    applied = []
    # One material per surface rather than one per part: three parts asking for
    # crystal are the same crystal, and three identical materials would be
    # three things to keep in step for no reason.
    surfaces: dict[str, Any] = {}
    for key, entry in wanted.items():
        recipe = recipes[entry["recipe"]]
        made_now = entry["recipe"] not in surfaces
        if made_now:
            surface = painted.copy()
            surface.name = "{0}_{1}".format(
                painted.name, entry["recipe"].replace("-", " ").title().replace(" ", ""))
            surfaces[entry["recipe"]] = surface
            mesh.materials.append(surface)
        surface = surfaces[entry["recipe"]]
        index = list(mesh.materials).index(surface)
        principled = next(n for n in surface.node_tree.nodes if n.type == "BSDF_PRINCIPLED")

        released = []
        for field, socket_name in INPUTS.items():
            if field not in recipe or socket_name not in principled.inputs:
                continue
            socket = principled.inputs[socket_name]
            # The whole point. A bound map wins over the value beside it, so a
            # recipe that set Roughness without letting the map go would change
            # nothing and still report success -- which is exactly what an
            # earlier version of this did, because it compared sockets by
            # identity and Blender hands out a new wrapper every time.
            for link in list(surface.node_tree.links):
                if link.to_node.name == principled.name and link.to_socket.name == socket_name:
                    surface.node_tree.links.remove(link)
                    released.append(socket_name)
            socket.default_value = float(recipe[field])
            if principled.inputs[socket_name].is_linked:
                print("[SURFACE] FAILED: {0} is still driven by a map after being released, "
                      "so this recipe would have changed nothing".format(socket_name))
                return 1

        for polygon_index in chosen[key]:
            mesh.polygons[polygon_index].material_index = index

        applied.append({
            "part": key[0] + (":" + key[1] if key[1] else "") + (
                "@{0}-{1}".format(*key[2]) if key[2] else ""),
            "recipe": entry["recipe"],
            "material": surface.name,
            "faces": len(chosen[key]),
            "share": round(len(chosen[key]) / total, 5),
            "values": {field: recipe[field] for field in INPUTS if field in recipe},
            # Named, because a map let go of is paint somebody chose that is no
            # longer being read, and a reader should not have to infer it.
            "released_maps": sorted(set(released)),
            # What this part was made of before it was changed, so a later
            # reader can see what it was rendered as rather than only what it is.
            "was": surface_of.measure(centres[key], heights[key]),
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(output), export_format="GLB", export_yup=True, export_apply=True,
        export_animations=False, export_cameras=False, export_lights=False)
    if not output.is_file():
        print("[SURFACE] FAILED: the exporter wrote no file")
        return 1

    report = {
        "schema": "reference-asset-compiler.material-recipes.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "assigned": applied,
        "faces_total": len(mesh.polygons),
        "materials": [material.name for material in mesh.materials],
        "geometry_unchanged": True,
        "uvs_unchanged": True,
        "requires_fixed_view_review": True,
        "production_grade": False,
        "note": "Which material each face points at, and what those materials say about light. "
                "No vertex moved and no map was repainted.",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for entry in applied:
        was = entry["was"] or {}
        print("[SURFACE] {0}: {1} faces ({2:.1%}) -> {3}{4}".format(
            entry["part"], entry["faces"], entry["share"], entry["recipe"],
            "" if not was else "  (was roughness {0}, metallic {1})".format(
                was["roughness_median"], was["metallic_median"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
