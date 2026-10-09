"""Turn a generated full-body scan into the rebuild's body-acquisition.blend.

The rebuild (scripts/rebuild_character.py) starts from a frozen
body-acquisition.blend: one mesh, the outfit and both hands, at the character's
real size, centred on z=0 as the generator delivered it, with the scan's own
head and neck taken off so the conformed template head can take their place.
For the first character that blend was made by hand. This stage makes it from
the generator's GLB, the same way every time, and says what it did.

What it does, in order:

1. Imports the GLB (Hunyuan's are Y-up; Blender's glTF importer turns them
   Z-up, front towards -y). Several meshes are joined into one and every
   transform is applied: a body scan is one body. Coincident vertices are
   welded (glTF splits them at UV seams and normals), so the surface is one
   connected sheet rather than islands; step 4 follows that connectivity.
2. Scales it uniformly to --height-m (world-Z extent), as
   stage_generated_mesh.py does for any generated mesh.
3. Keeps it centred as delivered. Hunyuan normalises its output to a bounding
   box centred on the origin; Ennix's scan measured 1.80 m from z -0.89994 to
   +0.90006 after scaling. The pipeline relies on that: the profile's
   body_lift_m raises the centred body onto the floor, and the source camera's
   origin pixels register the body's origin against the painting. So the
   scale is about the origin, z is re-centred only when the box's centre is
   more than 1 mm off (it is recorded either way), and x/y are left exactly as
   delivered (the paintings register against them) unless the box's centre is
   more than 5 cm off the axis, which means the scan is not a centred
   delivery. body_lift_m is then -min z, i.e. half the height.
4. Takes off the head and neck above a cut height, robustly to a collar that
   is not level (one that rises at the back, as coat collars do, would be
   chopped by a single horizontal plane, or a plane low enough to keep it
   would leave neck skin in front):
   - the neck column is an ellipse around the vertical axis: --neck-ellipse-m,
     else the profile's neck_overlap.ellipse_m (the ellipse
     assemble_character.py later cuts inside, already measured for the
     character, centred on the axis as it uses it), else measured on a slice a
     little above the cut (--neck-measure-above-m). Measuring: seen from the
     axis, the innermost surface in each 5 degree direction is the neck (a
     collar or hair is further out, and directions that find only those are
     left out), and an axis-aligned ellipse is fitted to it. Its centre
     follows the neck when the neck is seen all round; when a collar hides
     part of it the centre stays on the axis. A measurement outside believable
     neck radii is refused rather than used. It is recorded either way, as a
     cross-check. It fails on Ennix's scan, whose coat collar hides the back of
     the neck at every height above his cut, which is why a given ellipse
     comes first;
   - faces with a vertex above the cut and inside that ellipse are removed:
     the neck skin, and the middle of the head. A measured ellipse is the
     neck's surface itself, so the cut goes --neck-margin-m (15 mm) outside
     it; a given ellipse is used as given;
   - faces with a vertex above the head level (cut + --head-above-cut-m) are
     removed wherever they are: the rest of the head, ears, hair;
   - with a face box (--face-box-m, else the profile's neck_overlap.face_box_m),
     faces with a vertex above the cut, within |x| of the axis and in front of
     a y are removed too: a chin and lower face that stand wider than the neck
     column and below the head level (character-02's, under a high collar),
     which the column alone leaves in front of the placed head;
   - collar faces outside the column are kept even where they rise above the
     cut;
   - then whatever is left lying wholly above the cut, attached to nothing
     below it, is dropped: the jaw and the back of the skull outside the
     column, once the column between them and the body is gone.
   Loose pieces of the scan below the cut are not this stage's business and
   are kept.
5. Names the object, saves the blend and writes body-scan-receipt.json next
   to it.

The cut height, in floor space (metres above the feet, the profile's
convention), is --cut-z-m, or comes from the character profile's
neck_overlap.above_z_m. That is where the assembly (assemble_character.py)
already cuts whatever skin is left inside the collar, so the rim this stage
leaves and the assembly's cut agree; the template head's neck is extended down
to oral_anatomy.neck_m[1], below it, so the head's neck overlaps the rim and
there is no gap (the stage warns when the profile says otherwise). For Ennix:
cut 1.49 m, head neck down to 1.43 m; the hand surgery on his scan removed the
old skin down to 1.483 m. The head level's default, 0.12 m above the cut,
clears his coat collar, which rises 0.10 m above the cut at the back
(top 1.5915 m).

Calibration: run with --profile on a reconstruction of Ennix's delivered scan
(his frozen acquisition joined with the skin the hand surgery removed), this
stage leaves 1,326,370 triangles against the hand-made 1,326,239. What differs
is small and on purpose: it also takes the patch of old neck the hand surgery
left inside his collar (above 1.49 m, inside the ellipse), which the assembly
cut later anyway; and it keeps the hair resting on the back of his collar
between 1.59 and 1.61 m, which the hand surgery separated
(--head-above-cut-m 0.10 takes it, with the top 1.5 mm of the collar).

The scan is assumed to have both hands free, in a T- or A-pose, below the head
level (no separate hand scan). Nothing is bisected: the rim inside the column
follows the scan's own faces, which the template head's neck covers.

Usage:
  blender -b --factory-startup --python scripts/blender/prepare_body_scan.py \
      -- <scan.glb> <out/body-acquisition.blend> --height-m 1.8 \
      [--cut-z-m Z | --profile profiles/characters/<id>.json] [--object-name N]
      [--neck-ellipse-m RX RY] [--head-above-cut-m 0.12] [--face-box-m ABS_X FRONT_Y]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage_generated_mesh import counts

# Re-centre z when the delivered box's centre is further than this from z=0.
Z_CENTRE_TOLERANCE_M = 0.001
# Re-centre x/y only when the scan is plainly not a centred delivery.
XY_CENTRE_TOLERANCE_M = 0.05
# Directions around the neck's centre in which its innermost surface is found.
NECK_BINS = 72
# An innermost point further out than this times the median is not the neck.
NECK_OUTLIER_RATIO = 1.2
# The share of directions that must see the neck before its centre is followed.
NECK_SURROUND = 0.75
# A measured column is the neck's surface itself; the cut goes a little outside.
MEASURED_MARGIN_M = 0.015
# Neck radii believable on a 1.8 m body (scaled with the height); a measurement
# outside them found a collar, not a neck.
PLAUSIBLE_NECK_RADIUS_M = (0.03, 0.09)
# The body object's name after the asset prefix (the rebuild's convention).
DEFAULT_OBJECT_NAME = "Garment_And_Wrists_Preserved"
# Vertices this close (in the delivered units, before scaling) are one point.
WELD_DISTANCE = 1e-6


def mesh_vertices(mesh) -> np.ndarray:
    verts = np.empty(len(mesh.vertices) * 3)
    mesh.vertices.foreach_get("co", verts)
    return verts.reshape(-1, 3)


def bounds(verts: np.ndarray) -> dict:
    return {"min": [round(float(v), 6) for v in verts.min(axis=0)],
            "max": [round(float(v), 6) for v in verts.max(axis=0)]}


def import_scan(path: Path):
    """Import the GLB and return one mesh object with every transform applied."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    if path.suffix.lower() not in (".glb", ".gltf"):
        raise SystemExit("The body scan must be a glTF/GLB file, got {0}".format(path.name))
    bpy.ops.import_scene.gltf(filepath=str(path), merge_vertices=True)
    meshes = [ob for ob in bpy.context.scene.objects if ob.type == "MESH"]
    if not meshes:
        raise SystemExit("The scan carries no mesh: {0}".format(path))
    bpy.context.view_layer.update()
    for ob in meshes:
        if ob.data.users > 1:
            ob.data = ob.data.copy()
        ob.data.transform(ob.matrix_world)
    for ob in meshes:
        ob.parent = None
        ob.matrix_world = Matrix.Identity(4)
    for ob in list(bpy.data.objects):
        if ob not in meshes:
            bpy.data.objects.remove(ob, do_unlink=True)
    body = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for ob in meshes:
            ob.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.join()
    # The importer can merge only vertices whose normals agree as well, so a
    # surface exported with split normals still arrives in islands. Weld what
    # sits at one position: the floating-piece test below follows connectivity.
    bm = bmesh.new()
    bm.from_mesh(body.data)
    count = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=WELD_DISTANCE)
    welded = count - len(bm.verts)
    bm.to_mesh(body.data)
    bm.free()
    return body, len(meshes), welded


def slice_points(verts: np.ndarray, edges: np.ndarray, z: float) -> np.ndarray:
    """Where the mesh's edges cross the plane at height z, as (x, y) points."""
    a, b = verts[edges[:, 0]], verts[edges[:, 1]]
    da, db = a[:, 2] - z, b[:, 2] - z
    crossing = da * db < 0
    t = da[crossing] / (da[crossing] - db[crossing])
    return (a[crossing] + (b[crossing] - a[crossing]) * t[:, None])[:, :2]


class NeckNotFound(Exception):
    pass


def innermost(near: np.ndarray, centre: np.ndarray) -> np.ndarray:
    """The nearest point to ``centre`` in each direction, less the collar's."""
    offset = near - centre
    radius = np.hypot(offset[:, 0], offset[:, 1])
    bins = ((np.arctan2(offset[:, 1], offset[:, 0]) + math.pi)
            / (2 * math.pi) * NECK_BINS).astype(int) % NECK_BINS
    order = np.lexsort((radius, bins))
    first = order[np.r_[True, bins[order][1:] != bins[order][:-1]]]
    # A direction the neck has no point in finds the collar or hair instead:
    # much further out than its neighbours. Leave those out.
    inner_radius = radius[first]
    return near[first[inner_radius <= NECK_OUTLIER_RATIO * np.median(inner_radius)]]


def measure_neck(points: np.ndarray, search_radius: float) -> dict:
    """Fit the neck's cross-section: the innermost surface seen from the axis."""
    near = points[np.hypot(points[:, 0], points[:, 1]) < search_radius]
    if len(near) < 12:
        raise NeckNotFound("{0} slice points within {1} m of the axis".format(len(near), search_radius))
    centre = np.zeros(2)
    inner = innermost(near, centre)
    centred_on = "the vertical axis (the neck is not seen all round)"
    # Follow the neck's own centre only when it is seen all round: the centre
    # of a partial arc is pulled towards the arc.
    for _ in range(8):
        if len(inner) < NECK_SURROUND * NECK_BINS:
            break
        centred_on = "the neck's own centre (seen all round)"
        moved = inner.mean(axis=0)
        if np.allclose(moved, centre, atol=1e-5):
            break
        centre = moved
        inner = innermost(near, centre)
    if len(inner) < 6:
        raise NeckNotFound("only {0} directions see the neck".format(len(inner)))
    offset = inner - centre
    # (dx / rx)^2 + (dy / ry)^2 = 1, linear in 1 / rx^2 and 1 / ry^2.
    solution = np.linalg.lstsq(offset ** 2, np.ones(len(offset)), rcond=None)[0]
    if np.all(solution > 0):
        radii = 1.0 / np.sqrt(solution)
    else:
        radii = np.full(2, float(np.median(np.hypot(offset[:, 0], offset[:, 1]))))
    return {"centre_xy_m": [round(float(v), 6) for v in centre],
            "radii_xy_m": [round(float(v), 6) for v in radii],
            "centred_on": centred_on, "directions_found": int(len(inner)), "directions": NECK_BINS}


def face_flags(mesh, vertex_flag: np.ndarray) -> np.ndarray:
    """True for each face with at least one flagged vertex."""
    loop_verts = np.empty(len(mesh.loops), dtype=np.int64)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    starts = np.empty(len(mesh.polygons), dtype=np.int64)
    mesh.polygons.foreach_get("loop_start", starts)
    return np.logical_or.reduceat(vertex_flag[loop_verts], starts)


def delete_faces(mesh, doomed: np.ndarray) -> None:
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.flatnonzero(doomed)], context="FACES")
    bm.to_mesh(mesh)
    bm.free()


def drop_floating(body, seed: np.ndarray) -> None:
    """Delete every piece of the mesh not connected to a seed vertex."""
    mesh = body.data
    mesh.vertices.foreach_set("select", seed.astype(bool))
    mesh.edges.foreach_set("select", np.zeros(len(mesh.edges), dtype=bool))
    mesh.polygons.foreach_set("select", np.zeros(len(mesh.polygons), dtype=bool))
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    bpy.ops.mesh.select_linked(delimit=set())
    bpy.ops.mesh.select_all(action="INVERT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")


def load_profile(path: str | None) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else {}


def choose_cut(args, profile: dict) -> tuple[float, str]:
    if args.cut_z_m is not None:
        return args.cut_z_m, "argument --cut-z-m"
    above = (profile.get("neck_overlap") or {}).get("above_z_m")
    if above is None:
        raise SystemExit("No cut height: pass --cut-z-m, or a --profile with neck_overlap.above_z_m.")
    return float(above), "profile {0}: neck_overlap.above_z_m".format(args.profile)


def choose_name(args, profile: dict) -> str:
    if args.object_name:
        return args.object_name
    if (profile.get("inputs") or {}).get("body_object"):
        return profile["inputs"]["body_object"]
    prefix = profile.get("asset_prefix")
    return "{0}_{1}".format(prefix, DEFAULT_OBJECT_NAME) if prefix else DEFAULT_OBJECT_NAME


def main() -> int:
    p = argparse.ArgumentParser(description="Generated body scan GLB -> body-acquisition.blend")
    p.add_argument("scan", help="the generator's body GLB")
    p.add_argument("out", help="the body-acquisition.blend to write (must not exist)")
    p.add_argument("--height-m", type=float, required=True, help="the character's height, feet to crown")
    p.add_argument("--cut-z-m", type=float,
                   help="remove the head and neck above this height, in metres above the feet")
    p.add_argument("--profile", help="character profile: the cut (neck_overlap.above_z_m) and the object name")
    p.add_argument("--object-name", help="the body object's name (default: the profile's inputs.body_object, "
                                         "else <asset_prefix>_" + DEFAULT_OBJECT_NAME + ")")
    p.add_argument("--head-above-cut-m", type=float, default=0.12,
                   help="everything this far above the cut is head, wherever it is")
    p.add_argument("--measure-neck", action="store_true",
                   help="cut inside the measured neck column even when the profile has neck_overlap.ellipse_m")
    p.add_argument("--neck-measure-above-m", type=float, default=0.03,
                   help="measure the neck column on a slice this far above the cut")
    p.add_argument("--neck-ellipse-m", type=float, nargs=2, metavar=("RADIUS_X", "RADIUS_Y"),
                   help="the neck column, on the axis (default: the profile's neck_overlap.ellipse_m, "
                        "else measured)")
    p.add_argument("--face-box-m", type=float, nargs=2, metavar=("ABS_X", "FRONT_Y"),
                   help="also cut above the cut within |x| < ABS_X and y < FRONT_Y (the scan's chin and face; "
                        "default: the profile's neck_overlap.face_box_m, else none)")
    p.add_argument("--neck-margin-m", type=float,
                   help="grow the neck column by this much before cutting inside it "
                        "(default: {0} m for a measured column, 0 for a given one)".format(MEASURED_MARGIN_M))
    p.add_argument("--neck-search-radius-m", type=float, default=0.25,
                   help="look for the neck within this distance of the vertical axis")
    p.add_argument("--receipt", help="default: body-scan-receipt.json next to the blend")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

    scan, out = Path(a.scan).resolve(), Path(a.out).resolve()
    receipt_path = Path(a.receipt).resolve() if a.receipt else out.parent / "body-scan-receipt.json"
    if not scan.is_file():
        raise SystemExit("The scan does not exist: {0}".format(scan))
    if out.exists():
        raise SystemExit("Refusing to overwrite {0}; a frozen acquisition is evidence.".format(out))
    if not 0.3 <= a.height_m <= 3.0:
        raise SystemExit("A body {0} m tall is not plausible.".format(a.height_m))
    profile = load_profile(a.profile)
    cut_floor, cut_source = choose_cut(a, profile)
    name = choose_name(a, profile)
    if not 0.0 < cut_floor < a.height_m:
        raise SystemExit("The cut at {0} m is not within a body {1} m tall.".format(cut_floor, a.height_m))
    gap_note = None
    neck_m = (profile.get("oral_anatomy") or {}).get("neck_m")
    if neck_m and neck_m[1] > cut_floor:
        gap_note = ("The template head's neck stops at {0} m, above the cut at {1} m: "
                    "there will be a gap at the collar.".format(neck_m[1], cut_floor))
        print("WARNING: " + gap_note)

    body, imported_meshes, welded = import_scan(scan)
    mesh = body.data
    before = counts([body])

    verts = mesh_vertices(mesh)
    delivered = bounds(verts)
    extent = verts[:, 2].max() - verts[:, 2].min()
    if extent <= 0:
        raise SystemExit("The scan has no vertical extent to scale.")
    factor = a.height_m / extent
    mesh.transform(Matrix.Scale(factor, 4))
    verts = mesh_vertices(mesh)
    centre = (verts.min(axis=0) + verts.max(axis=0)) / 2
    shift = np.zeros(3)
    if abs(centre[2]) > Z_CENTRE_TOLERANCE_M:
        shift[2] = -centre[2]
    if np.hypot(centre[0], centre[1]) > XY_CENTRE_TOLERANCE_M:
        shift[:2] = -centre[:2]
    if shift.any():
        mesh.transform(Matrix.Translation(shift.tolist()))
        verts = verts + shift
    lift = float(-verts[:, 2].min())
    cut = cut_floor - lift
    head_level = cut + a.head_above_cut_m

    edges = np.empty(len(mesh.edges) * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", edges)
    measure_z = cut + a.neck_measure_above_m
    try:
        measured = measure_neck(slice_points(verts, edges.reshape(-1, 2), measure_z), a.neck_search_radius_m)
    except NeckNotFound as error:
        measured = {"error": str(error)}
    measured["at_z_m"] = {"floor": round(measure_z + lift, 6), "centred": round(measure_z, 6)}
    if "error" not in measured:
        low, high = (bound * a.height_m / 1.8 for bound in PLAUSIBLE_NECK_RADIUS_M)
        measured["plausible"] = all(low <= r <= high for r in measured["radii_xy_m"])
    profile_ellipse = (profile.get("neck_overlap") or {}).get("ellipse_m")
    margin = a.neck_margin_m
    if a.neck_ellipse_m:
        centre_xy, radii = np.zeros(2), np.array(a.neck_ellipse_m, dtype=float)
        column_source = "argument --neck-ellipse-m, on the axis"
    elif profile_ellipse and not a.measure_neck:
        centre_xy, radii = np.zeros(2), np.array(profile_ellipse, dtype=float)
        column_source = "profile {0}: neck_overlap.ellipse_m, on the axis".format(a.profile)
    elif measured.get("plausible"):
        centre_xy, radii = np.array(measured["centre_xy_m"]), np.array(measured["radii_xy_m"])
        column_source = "measured"
        margin = MEASURED_MARGIN_M if margin is None else margin
    else:
        raise SystemExit("No neck column to cut inside: the slice at {0:.3f} m above the feet found {1}. "
                         "Pass --neck-ellipse-m or a --profile with neck_overlap.ellipse_m.".format(
                             measure_z + lift, measured.get("error") or "radii {0} m".format(
                                 measured["radii_xy_m"])))
    margin = 0.0 if margin is None else margin
    column = radii + margin
    neck = {"source": column_source, "centre_xy_m": [round(float(v), 6) for v in centre_xy],
            "radii_xy_m": [round(float(v), 6) for v in radii], "margin_m": margin,
            "cut_radii_xy_m": [round(float(v), 6) for v in column], "measured": measured}

    offset = verts[:, :2] - centre_xy
    inside = ((offset / column) ** 2).sum(axis=1) < 1.0
    above = verts[:, 2] > cut
    in_column = face_flags(mesh, inside & above)
    in_head = face_flags(mesh, verts[:, 2] > head_level)
    removed = {"neck_column": int(in_column.sum()), "above_head_level": int((in_head & ~in_column).sum())}
    face_box = a.face_box_m or (profile.get("neck_overlap") or {}).get("face_box_m")
    in_face = np.zeros_like(in_column)
    if face_box:
        abs_x, front_y = (float(v) for v in face_box)
        in_face = face_flags(mesh, above & (np.abs(verts[:, 0]) < abs_x) & (verts[:, 1] < front_y))
        removed["face_box"] = int((in_face & ~in_column & ~in_head).sum())
    delete_faces(mesh, in_column | in_head | in_face)

    faces_before_floating = len(mesh.polygons)
    drop_floating(body, mesh_vertices(mesh)[:, 2] <= cut)
    removed["floating_above_cut"] = faces_before_floating - len(mesh.polygons)
    removed["faces_total"] = sum(removed.values())

    body.name = name
    mesh.name = name
    after = counts([body])
    verts = mesh_vertices(mesh)
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))

    receipt = {
        "schema": "rac.body-scan-preparation.v1",
        "blender_version": bpy.app.version_string,
        "source": str(scan),
        "source_sha256": hashlib.sha256(scan.read_bytes()).hexdigest(),
        "output": str(out),
        "object": name,
        "imported_meshes_joined": imported_meshes,
        "coincident_vertices_welded": welded,
        "triangles": {"before": before["triangles"], "after": after["triangles"]},
        "vertices": {"before": before["vertices"], "after": after["vertices"]},
        "height_m": a.height_m,
        "scale": {"factor": round(factor, 8), "delivered_bounds_m": delivered},
        "centre": {"bbox_centre_after_scale_m": [round(float(v), 6) for v in centre],
                   "shift_applied_m": [round(float(v), 6) for v in shift],
                   "rule": "z re-centred beyond {0} m, x/y beyond {1} m".format(
                       Z_CENTRE_TOLERANCE_M, XY_CENTRE_TOLERANCE_M)},
        "bounds_after_m": bounds(verts),
        "top_floor_z_m": round(float(verts[:, 2].max()) + lift, 6),
        "cut_z_m": {"floor": round(cut_floor, 6), "centred": round(cut, 6), "source": cut_source},
        "head_level_z_m": {"floor": round(head_level + lift, 6), "centred": round(head_level, 6)},
        "neck_column": neck,
        "face_box_m": [float(v) for v in face_box] if face_box else None,
        "faces_removed": removed,
        "body_lift_m": round(lift, 9),
        "profile": str(Path(a.profile).resolve()) if a.profile else None,
        "head_neck_gap": gap_note,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("cut source: {0} (cut at {1:.4f} m above the feet)".format(cut_source, cut_floor))
    print("neck column: {0}, radii {1} m + {2} m margin".format(
        column_source, neck["radii_xy_m"], margin))
    print("body_lift_m: {0:.9f}".format(lift))
    print("BODY_SCAN_RECEIPT " + json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
