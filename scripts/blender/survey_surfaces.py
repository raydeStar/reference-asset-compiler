"""What a model is made of, part by part, said in the words used to change it.

This is what a proposal is made against. An agent looking at a render can say
"the blade reads like plastic", and be right, and still have no way to say
which faces it means or what they are currently made of. This names every part
a caller could address, counts it, measures what it is actually made of, and
says which named surface those numbers are nearest to.

That last part is the point. `reads_as` is in the same vocabulary a caller uses
to ask for a surface, so judging a part becomes a comparison -- is this what it
is supposed to be? -- rather than an invention. A reviewer who has to invent
roughness values from a picture will invent them badly; one who has to say
"that reads as rough metal and it is supposed to be crystal" is doing something
a person or a vision model can actually do well.

Nothing here changes the model. It reads, counts, measures, and stops.

Usage:
  blender -b --factory-startup --python scripts/blender/survey_surfaces.py \
      -- <painted.glb> <survey.json> <report.json> [--minimum-share 0.004]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_parts import Surface  # noqa: E402


def read_option(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = [item for index, item in enumerate(argv)
                  if not item.startswith("--")
                  and (index == 0 or not argv[index - 1].startswith("--"))]
    if len(positional) < 3:
        print("[SURVEY] FAILED: expected <source> <survey.json> <report.json>")
        return 2

    source, output, report_path = (Path(positional[0]), Path(positional[1]), Path(positional[2]))
    minimum_share = float(read_option(argv, "--minimum-share", "0.004"))
    if not source.is_file():
        print("[SURVEY] FAILED: source does not exist: {0}".format(source))
        return 1

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(meshes) != 1:
        print("[SURVEY] FAILED: expected one mesh object, found {0}".format(len(meshes)))
        return 1

    mesh_object = meshes[0]
    if not mesh_object.data.materials:
        print("[SURVEY] FAILED: the mesh carries no material to read")
        return 1
    if not mesh_object.data.uv_layers.active:
        print("[SURVEY] FAILED: the mesh has no UVs, so its paint cannot be read per face")
        return 1

    surface = Surface(mesh_object)
    if surface.albedo is None:
        print("[SURVEY] FAILED: the material has no base colour image to read")
        return 1
    parts = surface.parts(minimum_share)
    if not parts:
        print("[SURVEY] FAILED: no part of this model is {0:.1%} of it, so there is "
              "nothing worth naming".format(minimum_share))
        return 1

    survey = {
        "schema": "reference-asset-compiler.surface-survey.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "faces_total": len(mesh_object.data.polygons),
        "materials": [material.name for material in mesh_object.data.materials],
        "minimum_share": minimum_share,
        "parts": parts,
        # Said plainly, because a survey that looks like a verdict invites
        # somebody to act on it without looking at the model.
        "judged": False,
        "note": "What each part is currently made of, measured from its own paint. "
                "Nothing here says what any part should be; a person or an agent "
                "looking at the fixed views says that, and a person accepts it.",
        "vocabulary": {
            "surfaces": sorted(surface.recipes),
            "tones": sorted(surface.tones),
            "assign": "colour[:tone][@low-high]=surface",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(survey, indent=2) + "\n", encoding="utf-8")

    report = dict(survey)
    report["survey"] = str(output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for part in parts:
        print("[SURVEY] {0:<16} {1:>6} faces {2:>6.1%}  roughness {3}  metallic {4}  reads as {5}".format(
            part["part"], part["faces"], part["share"],
            part.get("roughness_median"), part.get("metallic_median"), part["reads_as"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
