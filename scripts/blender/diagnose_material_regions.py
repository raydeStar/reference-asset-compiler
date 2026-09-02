"""Report where each material actually lands on the body, and where its UVs go.

A face texture that bleeds onto a thigh shows up here as a material whose
polygons are dominated by a leg bone, or as UV islands from a leg bone landing
in the same atlas region as the head. Both are invisible in a front render and
obvious in the numbers.

Usage:
  blender -b --factory-startup --python scripts/blender/diagnose_material_regions.py \
      -- <asset.fbx> <report.json>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Vector

# Coarse body regions, keyed by the bone that dominates a vertex's weights.
REGION_OF = {}
for bone in ("head", "neck_01", "neck_02"):
    REGION_OF[bone] = "head"
for bone in ("spine_01", "spine_02", "spine_03", "spine_04", "spine_05", "pelvis"):
    REGION_OF[bone] = "torso"
for side in ("l", "r"):
    for bone in ("clavicle", "upperarm", "lowerarm"):
        REGION_OF["{0}_{1}".format(bone, side)] = "arm"
    REGION_OF["hand_{0}".format(side)] = "hand"
    for bone in ("thigh", "calf"):
        REGION_OF["{0}_{1}".format(bone, side)] = "leg"
    REGION_OF["foot_{0}".format(side)] = "foot"
    REGION_OF["ball_{0}".format(side)] = "foot"


def region_for_bone(name):
    base = name.lower()
    if base in REGION_OF:
        return REGION_OF[base]
    for token, region in (
        ("thumb", "hand"), ("index", "hand"), ("middle", "hand"),
        ("ring", "hand"), ("pinky", "hand"),
        ("upperarm", "arm"), ("lowerarm", "arm"), ("clavicle", "arm"),
        ("thigh", "leg"), ("calf", "leg"),
        ("spine", "torso"), ("pelvis", "torso"),
        ("neck", "head"), ("head", "head"),
        ("foot", "foot"), ("ball", "foot"),
    ):
        if token in base:
            return region
    return "other"


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    asset_path, report_path = Path(argv[0]), Path(argv[1])

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(asset_path))

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not meshes or not armatures:
        print("[DIAG] FAILED: need a mesh and an armature")
        return 1
    bone_names = {b.name for b in armatures[0].data.bones}

    payload = {"asset": str(asset_path), "meshes": []}
    findings = []

    for obj in meshes:
        me = obj.data
        group_name = {g.index: g.name for g in obj.vertex_groups}

        # Dominant deform bone per vertex -> coarse body region.
        vert_region = []
        for v in me.vertices:
            best_weight = 0.0
            best_group = None
            for g in v.groups:
                name = group_name.get(g.group)
                if name in bone_names and g.weight > best_weight:
                    best_weight = g.weight
                    best_group = name
            vert_region.append(region_for_bone(best_group) if best_group else "other")

        uv_layer = me.uv_layers.active
        entry = {"mesh": obj.name, "materials": []}

        # Atlas region occupied by each body region, to catch a leg island
        # sitting on top of the face island.
        region_uv_boxes = {}
        for poly in me.polygons:
            regions = Counter(vert_region[i] for i in poly.vertices)
            region = regions.most_common(1)[0][0]
            if uv_layer is None:
                continue
            box = region_uv_boxes.setdefault(region, [1e9, 1e9, -1e9, -1e9])
            for loop_index in poly.loop_indices:
                u, v = uv_layer.data[loop_index].uv
                box[0] = min(box[0], u)
                box[1] = min(box[1], v)
                box[2] = max(box[2], u)
                box[3] = max(box[3], v)

        for slot_index, mat in enumerate(me.materials):
            polys = [p for p in me.polygons if p.material_index == slot_index]
            if not polys:
                entry["materials"].append(
                    {"material": mat.name if mat else None, "polygons": 0}
                )
                continue
            regions = Counter()
            for poly in polys:
                counts = Counter(vert_region[i] for i in poly.vertices)
                regions[counts.most_common(1)[0][0]] += 1
            total = sum(regions.values())
            spread = {k: round(100.0 * v / total, 1) for k, v in regions.most_common()}

            centre = Vector((0.0, 0.0, 0.0))
            for poly in polys:
                centre += obj.matrix_world @ poly.center
            centre /= len(polys)

            record = {
                "material": mat.name if mat else None,
                "polygons": total,
                "region_pct": spread,
                "world_centre": [round(c, 4) for c in centre],
            }
            entry["materials"].append(record)

            name = (mat.name if mat else "").lower()
            # A material named for the face has no business on a leg.
            if any(t in name for t in ("face", "eye", "head")):
                stray = sum(
                    v for k, v in spread.items() if k in ("leg", "foot", "arm", "hand")
                )
                if stray > 1.0:
                    findings.append(
                        "{0}: {1:.1f}% of a face/eye material's polygons sit on "
                        "limbs ({2})".format(
                            record["material"], stray,
                            ", ".join(
                                "{0} {1}%".format(k, v) for k, v in spread.items()
                                if k in ("leg", "foot", "arm", "hand")
                            ),
                        )
                    )

        entry["region_uv_bounds"] = {
            k: [round(x, 4) for x in v] for k, v in region_uv_boxes.items()
        }

        # Do the head and leg islands overlap in the atlas? If so, a mip or a
        # gutter bleed puts facial features on the trousers.
        head_box = region_uv_boxes.get("head")
        leg_box = region_uv_boxes.get("leg")
        if head_box and leg_box:
            overlap = not (
                head_box[2] < leg_box[0] or leg_box[2] < head_box[0]
                or head_box[3] < leg_box[1] or leg_box[3] < head_box[1]
            )
            entry["head_leg_uv_bbox_overlap"] = overlap

        payload["meshes"].append(entry)

    payload["findings"] = findings
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    for mesh_entry in payload["meshes"]:
        print("[DIAG] {0}".format(mesh_entry["mesh"]))
        for record in mesh_entry["materials"]:
            if not record.get("polygons"):
                continue
            print("  {0:<34} {1:>7} polys  {2}".format(
                str(record["material"])[:34], record["polygons"],
                ", ".join("{0} {1}%".format(k, v)
                          for k, v in record["region_pct"].items())))
    for f in findings:
        print("[DIAG] FINDING: {0}".format(f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
