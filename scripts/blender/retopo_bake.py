"""Retopologise a character and bake the detail back onto it.

The dense meshes are 54k-70k triangles with a per-patch UV layout, no normal
map, and every island edge a seam. This produces the game-ready version:

  1. Heal    Weld the export's split vertices, drop stray shells, fill holes,
             make normals consistent. This is the step that makes everything
             else possible -- field-scout-female reads as 664 disconnected
             components until it is welded, at which point it is exactly one
             clean manifold.
  2. Remesh  QuadriFlow to the triangle budget. Never Decimate, and never a
             voxel pre-pass: voxels melt fur and fine silhouette. QuadriFlow
             on the healed surface keeps the shape.
  3. Unwrap  Coherent islands with a real gutter, replacing the confetti.
  4. Skin    Transfer weights from the dense original, so the existing UE5
             skeleton still drives it.
  5. Bake    Normal, AO and BaseColor from the dense original onto the new
             UVs. The normal map is what puts the sculpted detail back; the
             low-poly only has to carry the silhouette and deform well.

Fails rather than shipping a character that lost its shape, and refuses to
call an unchanged mesh a successful remesh.

Usage:
  blender -b --factory-startup --python scripts/blender/retopo_bake.py \
      -- <in.fbx> <out_dir> <report.json> [--budget 12000] [--resolution 2048]
      [--basecolor path] [--samples 24] [--cage 0.02]
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from collections import Counter, defaultdict
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def arg(argv, name, default, cast=str):
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def tri_count(mesh):
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


def measure(obj):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen, shells = set(), []
    for vert in bm.verts:
        if vert.index in seen:
            continue
        stack, size = [vert], 0
        seen.add(vert.index)
        while stack:
            current = stack.pop()
            size += 1
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        shells.append(size)
    out = {
        "verts": len(bm.verts),
        "faces": len(bm.faces),
        "components": len(shells),
        "non_manifold_edges": sum(1 for e in bm.edges if not e.is_manifold),
        "boundary_edges": sum(1 for e in bm.edges if e.is_boundary),
    }
    bm.free()
    return out


def edit_op(action):
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    action()
    bpy.ops.object.mode_set(mode="OBJECT")


def _boundary(bm):
    return [e for e in bm.edges if len(e.link_faces) == 1]


def _excess(bm):
    return [e for e in bm.edges if len(e.link_faces) > 2]


def _bowties(bm):
    return [v for v in bm.verts if v.link_faces and not v.is_manifold]


def drop_excess_faces(bm):
    """An edge shared by three or more faces is not a surface. Keep the two
    largest and drop the rest; the extras are export slivers."""
    removed = 0
    for edge in list(bm.edges):
        while edge.is_valid and len(edge.link_faces) > 2:
            worst = min(edge.link_faces, key=lambda f: f.calc_area())
            bmesh.ops.delete(bm, geom=[worst], context="FACES")
            removed += 1
    return removed


def close_boundary_loops(bm):
    """Cap every simple boundary loop with a face.

    fill_holes only closes holes it can fan-triangulate and gives up on the
    rest -- on field-scout-male it plateaus at 124 open edges however many
    times it is called. Tracing the loops explicitly closes what it cannot.
    """
    boundary = _boundary(bm)
    if not boundary:
        return 0
    incident = defaultdict(list)
    for edge in boundary:
        incident[edge.verts[0]].append(edge)
        incident[edge.verts[1]].append(edge)

    used, created, new_faces = set(), 0, []
    for start in boundary:
        if start in used:
            continue
        verts, edge, vert, simple = [], start, start.verts[0], True
        while True:
            used.add(edge)
            verts.append(vert)
            vert = edge.other_vert(vert)
            if len(incident[vert]) != 2:
                simple = False       # pinched: a vertex on three boundaries
                break
            nxt = [e for e in incident[vert] if e is not edge and e not in used]
            if not nxt:
                break                # walked back to the start
            edge = nxt[0]
        if not simple or len(verts) < 3 or len(set(verts)) != len(verts):
            continue
        try:
            new_faces.append(bm.faces.new(verts))
            created += 1
        except ValueError:
            pass                     # the face already exists
    if new_faces:
        bmesh.ops.triangulate(bm, faces=new_faces)
    return created


def tear_out_bowties(bm):
    """Delete the face fans around vertices that are not a single surface.

    A bowtie -- two cones meeting at a point -- has no quad flow through it and
    no amount of hole filling removes one. There are two on field-scout-male
    and sixteen on ninja-man, so this costs a few dozen triangles and the next
    closing pass caps the holes left behind.
    """
    bad = _bowties(bm)
    faces = {f for v in bad for f in v.link_faces}
    if faces:
        bmesh.ops.delete(bm, geom=list(faces), context="FACES")
    return len(bad)


def make_manifold(obj, max_passes=8):
    """Close holes, drop surplus faces and tear out bowties until stable.

    One pass is never enough: capping a loop can lay a face across a chord that
    already carried two, and dropping that face reopens a smaller hole.

    This is a RESCUE, not a preparation step. Running it on a mesh QuadriFlow
    would have accepted makes things worse -- fox-mascot remeshed cleanly at
    69,545 -> 23,002 triangles until this ran first, after which QuadriFlow
    refused its body outright. So it is only ever applied to a shell that has
    already been rejected.
    """
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    history = []
    for _ in range(max_passes):
        state = (len(_boundary(bm)), len(_excess(bm)), len(_bowties(bm)))
        history.append(state)
        if state == (0, 0, 0):
            break
        dropped = drop_excess_faces(bm)
        filled = bmesh.ops.holes_fill(bm, edges=_boundary(bm), sides=0)
        closed = close_boundary_loops(bm)
        torn = tear_out_bowties(bm)
        if (dropped, len(filled.get("faces", [])), closed, torn) == (0, 0, 0, 0):
            break
    final = (len(_boundary(bm)), len(_excess(bm)), len(_bowties(bm)))
    bm.to_mesh(obj.data)
    bm.free()
    edit_op(lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    return {"passes": [list(h) for h in history], "boundary_edges": final[0],
            "edges_over_two_faces": final[1], "bowtie_verts": final[2]}


def sanitise_normal_map(pixels):
    """Force every texel to be a plausible tangent-space normal.

    The bake writes whatever direction the ray found, and where it found the
    wrong surface that is a direction no tangent-space normal can legally take
    -- the saturated green and red patches in an otherwise lavender sheet.
    Renormalising fixes length; a normal facing away from the surface (z <= 0)
    cannot be right at all and is replaced with flat.

    Returns how many texels had to be replaced.
    """
    vectors = pixels[..., :3] * 2.0 - 1.0
    lengths = np.linalg.norm(vectors, axis=2)
    bad = (lengths < 0.2) | (vectors[..., 2] <= 0.05)
    safe = np.maximum(lengths, 1e-6)[..., None]
    vectors = vectors / safe
    vectors[bad] = (0.0, 0.0, 1.0)
    pixels[..., :3] = (vectors + 1.0) * 0.5
    return int(bad.sum())


def fill_unbaked(pixels, rounds=12):
    """Grow baked colour into texels the rays never reached.

    A texel with no hit keeps the clear value, which is transparent black, and
    black is exactly the colour that reads as damage. They cluster along island
    edges and -- once the mesh is cut into body regions and stitched back --
    along every region seam, which is why the per-region male arrived speckled
    with dark blotches across an otherwise correct jacket.

    Blender's bake margin already dilates, but only outward from an island into
    its gutter; it does nothing for a hole INSIDE one. This grows the nearest
    written colour into anything still unwritten, which also gives mip-mapping
    something better than black to average with.

    Takes and returns HxWx4 float32 with alpha as the written mask.
    """
    rgb = pixels[..., :3]
    known = pixels[..., 3] > 0.5
    filled = int((~known).sum())
    for _ in range(rounds):
        if known.all():
            break
        total = np.zeros_like(rgb)
        count = np.zeros(known.shape, dtype=np.float32)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            shifted_rgb = np.roll(np.roll(rgb, dy, axis=0), dx, axis=1)
            shifted_known = np.roll(np.roll(known, dy, axis=0), dx, axis=1)
            total += shifted_rgb * shifted_known[..., None]
            count += shifted_known
        grow = (~known) & (count > 0)
        if not grow.any():
            break
        rgb[grow] = total[grow] / count[grow][..., None]
        known |= grow
    pixels[..., :3] = rgb
    pixels[..., 3] = 1.0
    return filled


def remesh_outcome(obj):
    """Did QuadriFlow actually produce a usable mesh?

    It signals refusal as a log warning plus CANCELLED, never an exception, so
    the only reliable check is the result. It can also "succeed" and return
    coordinates that are entirely NaN -- fox-mascot's body does exactly that
    when remeshed on its own -- and NaN propagates silently: the KD-tree
    returns None for the nearest vertex to a NaN point, so every weight lookup
    misses and the whole body ships unweighted.
    """
    faces = len(obj.data.polygons)
    quads = sum(1 for f in obj.data.polygons if len(f.vertices) == 4)
    finite = all(math.isfinite(c) for v in obj.data.vertices for c in v.co)
    # A real quad remesh comes back essentially all quads. A refusal leaves the
    # input untouched, which on a triangulated character means a handful of
    # incidental quads -- ninja-man came back with 5 out of 54,212 and a bare
    # "did any quad appear" test called that a success.
    if quads < 0.9 * max(faces, 1):
        return False, "QuadriFlow left {0} quads in {1} faces".format(quads, faces)
    if not finite:
        return False, "QuadriFlow returned non-finite coordinates"
    return True, None


def try_remesh(obj, target, preserve_boundary=False):
    """One QuadriFlow attempt, reporting what actually came back."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.quadriflow_remesh(
            mode="FACES", target_faces=target, use_mesh_symmetry=False,
            use_preserve_sharp=False, use_preserve_boundary=preserve_boundary)
    except RuntimeError as error:
        return False, str(error)
    return remesh_outcome(obj)


def snap_boundary_to_seam(piece, seam_tree, seam_points, tolerance=0.03):
    """Pull a remeshed piece's open edges back onto the original cut vertices."""
    if seam_tree is None:
        return 0
    bm = bmesh.new()
    bm.from_mesh(piece.data)
    moved = 0
    for vert in bm.verts:
        if all(len(e.link_faces) != 1 for e in vert.link_edges):
            continue
        _, index, distance = seam_tree.find(vert.co)
        if index is not None and distance is not None and distance <= tolerance:
            vert.co = seam_points[index]
            moved += 1
    bm.to_mesh(piece.data)
    bm.free()
    return moved


def remesh_per_region(obj, budget, report, armature, min_faces=400):
    """Remesh body region by body region, keeping whatever QuadriFlow refuses.

    The third strategy, and the only one that can protect a head.

    QuadriFlow accepts OPEN meshes when use_preserve_boundary is set -- proven
    on field-scout-male, whose torso remeshed cleanly with 5,092 boundary edges
    -- so a character can be cut along body regions and reassembled. Preserving
    the boundary keeps the cut vertices in place, so welding after the join
    closes the seams exactly.

    What that buys: the regions QuadriFlow refuses are kept at full density
    instead of dragging the whole character down with them, and a region it
    refuses is very often the head. ninja-man's head is 50% of his triangles
    and the part that reads worst when reduced; per shell it rides inside a
    22,000-face body shell that gets cut 4.8x, and comes out as flat grey
    tiles.
    """
    regions = face_regions_by_bone(obj, armature)
    names = sorted(set(regions))
    if len(names) < 2:
        return None

    # Record where the cuts run, before making them.
    #
    # use_preserve_boundary keeps the SHAPE of a boundary, not its vertices --
    # QuadriFlow re-samples along the same curve with its own spacing. So two
    # pieces that were cut apart no longer share vertices, a 0.1mm weld cannot
    # stitch them, and the character ships with tears along every seam. They
    # are real holes, not a texture artifact: they show in a matcap.
    #
    # Keeping the original cut vertices gives every piece the same set of
    # points to snap back onto afterwards.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    seam_points = []
    for edge in bm.edges:
        linked = edge.link_faces
        if len(linked) == 2 and regions[linked[0].index] != regions[linked[1].index]:
            seam_points.append(edge.verts[0].co.copy())
            seam_points.append(edge.verts[1].co.copy())
    bm.free()
    seam_tree = None
    if seam_points:
        seam_tree = KDTree(len(seam_points))
        for index, point in enumerate(seam_points):
            seam_tree.insert(point, index)
        seam_tree.balance()

    pieces = []
    remaining = list(regions)
    for name in names:
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")
        hits = 0
        for index, poly in enumerate(obj.data.polygons):
            if remaining[index] == name:
                poly.select = True
                hits += 1
        if hits == 0 or hits == len(obj.data.polygons):
            continue
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.separate(type="SELECTED")
        bpy.ops.object.mode_set(mode="OBJECT")
        for new in [o for o in bpy.context.selected_objects
                    if o.type == "MESH" and o is not obj and o not in pieces]:
            new["region"] = name
            pieces.append(new)
        # separate() just renumbered the polygons still on obj.
        remaining = [r for r in remaining if r != name]
    obj["region"] = "rest"
    pieces.append(obj)

    total = sum(len(p.data.polygons) for p in pieces) or 1
    outcomes, kept_faces, snapped = [], 0, 0
    for piece in pieces:
        before = len(piece.data.polygons)
        share = max(int(budget * before / total), 60)
        ok, reason = False, "below the region floor"
        if before >= min_faces:
            ok, reason = try_remesh(piece, share, preserve_boundary=True)
            if not ok:
                # Repair WITHOUT sealing: the region cut has to stay open or
                # the pieces cannot be welded back together.
                bm = bmesh.new()
                bm.from_mesh(piece.data)
                for _ in range(6):
                    if not (drop_excess_faces(bm) + tear_out_bowties(bm)):
                        break
                bm.to_mesh(piece.data)
                bm.free()
                bpy.ops.object.select_all(action="DESELECT")
                piece.select_set(True)
                bpy.context.view_layer.objects.active = piece
                edit_op(lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
                ok, reason = try_remesh(piece, share, preserve_boundary=True)
        if not ok:
            kept_faces += len(piece.data.polygons)
        else:
            snapped += snap_boundary_to_seam(piece, seam_tree, seam_points)
        outcomes.append({"region": piece.get("region"), "faces_in": before,
                         "faces_out": len(piece.data.polygons),
                         "kept": not ok, "reason": reason})

    bpy.ops.object.select_all(action="DESELECT")
    for piece in pieces:
        piece.select_set(True)
    bpy.context.view_layer.objects.active = pieces[-1]
    if len(pieces) > 1:
        bpy.ops.object.join()
    joined = pieces[-1]
    bpy.ops.object.select_all(action="DESELECT")
    joined.select_set(True)
    bpy.context.view_layer.objects.active = joined
    # Every remeshed boundary vertex now sits on an original cut vertex, so the
    # pieces share points again and a weld closes the seam. Collapsing several
    # remeshed vertices onto one original leaves slivers, which dissolve away.
    edit_op(lambda: bpy.ops.mesh.remove_doubles(threshold=0.0002))

    # Snapping alone cannot close a seam: the kept side still carries every
    # original vertex along the cut while the remeshed side has a handful, so
    # between two snapped points the fine polyline bulges away from the coarse
    # edge and the gap stays open.
    #
    # Welding only the OPEN vertices closes it. Restricting the selection to
    # the boundary is what makes a 6mm threshold safe -- interior geometry is
    # never touched, so nothing collapses except the two lips of a seam.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="VERT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.mesh.select_non_manifold(
        extend=False, use_wire=True, use_boundary=True, use_multi_face=False,
        use_non_contiguous=False, use_verts=True)
    bpy.ops.mesh.remove_doubles(threshold=0.006)
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.dissolve_degenerate(threshold=0.0002)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    bm = bmesh.new()
    bm.from_mesh(joined.data)
    report["seam_boundary_edges_left"] = sum(
        1 for e in bm.edges if len(e.link_faces) == 1)
    bm.free()
    report["seam_vertices_snapped"] = snapped
    print("[RETOPO] snapped {0} boundary vertices; {1} open edges left".format(
        snapped, report["seam_boundary_edges_left"]))

    report["regions"] = outcomes
    report["region_faces_kept"] = kept_faces
    print("[RETOPO] {0} regions: {1} remeshed, {2} kept ({3} faces)".format(
        len(outcomes), sum(1 for o in outcomes if not o["kept"]),
        sum(1 for o in outcomes if o["kept"]), kept_faces))
    return joined


def remesh(obj, budget, report, min_faces=2000, armature=None,
           strategy="auto"):
    """Remesh the whole mesh if it will take it, otherwise shell by shell.

    Whole-mesh is strictly better when it works: one continuous quad field
    across the character, and small parts get remeshed along with everything
    else instead of being rationed by a proportional budget. field-scout-female
    and fox-mascot both take it.

    field-scout-male and ninja-man do not -- they heal into 8 and 24 shells and
    QuadriFlow refuses the lot -- so they fall back to per shell, which it
    accepts. The fallback is second because it is worse: fox-mascot's body
    remeshes to NaN when handed over on its own, having remeshed perfectly well
    as part of the whole.
    """
    if strategy == "passthrough":
        # Deliberately keep the geometry. For a character whose remesh is
        # measurably worse than its original -- ninja-man's head comes out as
        # flat grey tiles at any budget -- the rest of the stage is still
        # worth having, and a smaller triangle count is not worth a worse
        # likeness.
        report["remesh_mode"] = "passthrough"
        report["shells"] = []
        report["shells_refused"] = 0
        report["shells_preserved"] = 0
        report["faces_preserved"] = len(obj.data.polygons)
        print("[RETOPO] passthrough: keeping {0} faces as authored".format(
            len(obj.data.polygons)))
        return obj

    if strategy == "region":
        report["remesh_mode"] = "per_region"
        report["shells"] = []
        report["shells_refused"] = 0
        report["shells_preserved"] = 0
        report["faces_preserved"] = 0
        return remesh_per_region(obj, budget, report, armature)

    snapshot = obj.data.copy()
    ok, reason = try_remesh(obj, budget)
    report["remesh_mode"] = "whole"
    if ok:
        bpy.data.meshes.remove(snapshot)
        report["shells"] = []
        report["shells_refused"] = 0
        report["shells_preserved"] = 0
        report["faces_preserved"] = 0
        print("[RETOPO] whole-mesh remesh -> {0} faces".format(
            len(obj.data.polygons)))
        return obj

    # Put the healed mesh back before trying the other way.
    old = obj.data
    obj.data = snapshot
    bpy.data.meshes.remove(old)
    report["remesh_mode"] = "per_shell"
    report["whole_mesh_refusal"] = reason
    print("[RETOPO] whole-mesh remesh refused ({0}); falling back to shells".format(
        reason))
    return remesh_per_shell(obj, budget, report, min_faces)


def remesh_per_shell(obj, budget, report, min_faces=2000):
    """QuadriFlow each connected shell, at a budget proportional to its size.

    Whole-mesh remeshing only works on characters that heal into one shell.
    field-scout-male splits into 11 and ninja-man into 29 -- eyes, buttons and
    paired straps that were never connected to the body -- and QuadriFlow
    refuses the lot. Per shell it succeeds on every one of ninja-man's, and on
    all but one of field-scout-male's.

    A shell it still refuses is kept at full density rather than dropped or
    decimated: the likeness is the thing being protected, and the triangles it
    costs are recorded rather than hidden.

    Shells under `min_faces` are never remeshed. They are the eyes, buttons,
    straps and hair cards -- small in area, large in what the eye reads, and a
    proportional budget rations them to nothing. Remeshing fox-mascot's eyes
    into forty quads is what turned them into speckled fur. They cost few
    triangles, so keeping them verbatim is close to free and removes a whole
    class of damage.
    """
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="LOOSE")
    bpy.ops.object.mode_set(mode="OBJECT")

    shells = sorted([o for o in bpy.context.selected_objects if o.type == "MESH"],
                    key=lambda o: -len(o.data.polygons))
    # Preserving whole shells classified as "head" was tried, on the theory
    # that ninja-man's head was a small shell being starved by a proportional
    # budget. It is not -- his head is part of a 22,000-face body shell, so the
    # rule never fired for him -- and on field-scout-male it preserved his hair,
    # which was the only shell QuadriFlow would take, leaving nothing remeshed
    # at all. Removed rather than kept as a knob that measured nothing.
    remeshable = [s for s in shells if len(s.data.polygons) >= min_faces]
    # The budget belongs to the shells that will actually spend it.
    total = sum(len(s.data.polygons) for s in remeshable) or 1
    outcomes, refused, preserved = [], 0, 0
    for shell in shells:
        before = len(shell.data.polygons)
        if before < min_faces:
            preserved += before
            outcomes.append({"faces_in": before, "faces_out": before,
                             "kept": True, "reason": "below the remesh floor"})
            continue
        share = max(int(budget * before / total), 40)

        snapshot = shell.data.copy()
        ok, reason = try_remesh(shell, share)
        repair = None
        if not ok:
            # Only now is it worth disturbing the geometry.
            old = shell.data
            shell.data = snapshot
            snapshot = old.copy()
            bpy.data.meshes.remove(old)
            repair = make_manifold(shell)
            ok, reason = try_remesh(shell, share)
        if ok:
            bpy.data.meshes.remove(snapshot)
        else:
            # Keep the shell rather than ship whatever came back.
            old = shell.data
            shell.data = snapshot
            bpy.data.meshes.remove(old)
            refused += 1
        outcomes.append({
            "faces_in": before, "target": share,
            "faces_out": len(shell.data.polygons), "kept": not ok,
            "repaired": repair, "reason": reason})

    bpy.ops.object.select_all(action="DESELECT")
    for shell in shells:
        shell.select_set(True)
    bpy.context.view_layer.objects.active = shells[0]
    if len(shells) > 1:
        bpy.ops.object.join()
    report["shells"] = outcomes
    report["shells_refused"] = refused
    report["shells_preserved"] = len(shells) - len(remeshable)
    report["faces_preserved"] = preserved
    print("[RETOPO] {0} shells: {1} remeshed, {2} refused, {3} preserved "
          "({4} faces)".format(
              len(shells), len(remeshable) - refused, refused,
              len(shells) - len(remeshable), preserved))
    return shells[0]


def strip_non_finite(obj):
    """Delete vertices whose coordinates are NaN or infinite.

    fox-mascot carries a handful in its small shells. Remeshing the whole mesh
    used to erase them as a side effect; now that small shells are preserved
    verbatim they survive, and they poison everything downstream -- the
    silhouette grid casts NaN to int, and the KD-tree returns None for the
    nearest vertex to a NaN point, which reads as a confusing TypeError a
    hundred lines later.
    """
    bad = [v.index for v in obj.data.vertices
           if not all(math.isfinite(c) for c in v.co)]
    if not bad:
        return 0
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bpy.ops.object.mode_set(mode="OBJECT")
    for index in bad:
        obj.data.vertices[index].select = True
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.delete(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(bad)


def heal(obj, weld, min_shell_frac, report):
    """Undo export vertex-splitting, then repair what genuinely remains."""
    report["heal"] = {"imported": measure(obj)}
    report["heal"]["non_finite_verts_removed"] = strip_non_finite(obj)
    edit_op(lambda: bpy.ops.mesh.remove_doubles(threshold=weld))
    report["heal"]["welded"] = measure(obj)

    total = report["heal"]["welded"]["verts"]
    threshold = max(int(total * min_shell_frac), 8)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    seen, drop = set(), []
    for vert in bm.verts:
        if vert.index in seen:
            continue
        stack, group = [vert], []
        seen.add(vert.index)
        while stack:
            current = stack.pop()
            group.append(current.index)
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other.index not in seen:
                    seen.add(other.index)
                    stack.append(other)
        if len(group) < threshold:
            drop.extend(group)
    bm.free()
    if drop:
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.mode_set(mode="OBJECT")
        for index in drop:
            obj.data.vertices[index].select = True
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.delete(type="VERT")
        bpy.ops.object.mode_set(mode="OBJECT")

    edit_op(lambda: bpy.ops.mesh.fill_holes(sides=64))
    edit_op(lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    report["heal"]["repaired"] = measure(obj)
    return report["heal"]["repaired"]


# Where the player actually looks. A uniform pack rations the face like a boot,
# and the shipped art came from a dedicated 1024 head projection at roughly 721
# texels/cm2 -- so a flat layout halves it and the eyes and mouth go soft.
# Density goes as the square of these, and the cost is shared by every other
# region, so aim them at small regions: the face material is 5.9% of the sheet.
DEFAULT_REGION_WEIGHT = json.dumps({
    "head": 1.28, "hand_l": 1.15, "hand_r": 1.15,
})

# How much the face chart may grow the whole UV sheet. Everything else pays
# for it through the common pack factor, so this is the real knob: 12% means
# every other region loses about 6% of its density, whatever size the face is.
FACE_AREA_BUDGET = 0.12

# How far above the source's own texel density the output may go before the
# atlas is stepped down. Some headroom is right: the new layout packs tighter
# than the one it replaces, and clamping to exactly the old density would
# throw that away.
ATLAS_HEADROOM = 1.4

# Below this much difference between the retopo and the original, a normal map
# has nothing real to encode and ships bake noise instead.
NORMAL_MAP_MIN_DETAIL_MM = 1.5

# How much of the mesh a remesh has to actually replace before the UV layout is
# rebuilt. Below this the original layout still fits the original geometry, and
# replacing it costs more than the triangles saved.
REMESH_COVERAGE_MIN = 0.5

# UV area, as a multiple of the unit square, beyond which a material's faces
# are piled rather than laid out. Anything near or above 1.0 from a handful of
# faces is a defect in the source asset.
UV_AREA_LIMIT = 1.0

REGION_TOKENS = (
    ("thumb", "hand"), ("index", "hand"), ("middle", "hand"), ("ring", "hand"),
    ("pinky", "hand"), ("hand", "hand"),
    ("upperarm", "arm"), ("lowerarm", "arm"), ("clavicle", "arm"),
    ("thigh", "leg"), ("calf", "leg"),
    ("ball", "foot"), ("foot", "foot"),
    ("spine", "torso"), ("pelvis", "torso"),
    ("neck", "head"), ("head", "head"),
)


def _shells(bm):
    """Connected components, largest first."""
    seen, groups = set(), []
    for vert in bm.verts:
        if vert in seen:
            continue
        stack, group = [vert], []
        seen.add(vert)
        while stack:
            current = stack.pop()
            group.append(current)
            for edge in current.link_edges:
                other = edge.other_vert(current)
                if other not in seen:
                    seen.add(other)
                    stack.append(other)
        groups.append(group)
    groups.sort(key=len, reverse=True)
    return groups


def _probe_axes(count=48):
    """Evenly spread axes on the sphere, used as opposing pairs."""
    axes, golden = [], math.pi * (3.0 - math.sqrt(5.0))
    for index in range(count):
        z = 1.0 - 2.0 * (index + 0.5) / count
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        theta = golden * index
        axes.append(Vector((math.cos(theta) * radius,
                            math.sin(theta) * radius, z)))
    return axes


def _outside_silhouette(verts, tree, axes, offset=Vector((0.0, 0.0, 0.0))):
    """Count vertices that lie outside the host's outline from some direction.

    Visibility on its own is the wrong test. An eye is MEANT to be visible --
    that is what the lid aperture is for -- and a wide aperture leaks rays a
    long way off the forward axis. What is never correct is a point with open
    air on BOTH sides along one axis: such a point is not framed by the head,
    it is beside it, and that is exactly what reads as a shard stuck in the
    face.
    """
    count = 0
    for vert in verts:
        origin = vert.co + offset
        for axis in axes:
            if (tree.ray_cast(origin + axis * 1e-4, axis, 2.0)[0] is None
                    and tree.ray_cast(origin - axis * 1e-4, -axis, 2.0)[0] is None):
                count += 1
                break
    return count


def settle_prop_shells(obj, token, report, max_push=0.080, step=0.0005):
    """Seat prop shells that float proud of the surface they belong in.

    field-scout-male's eyeballs are modelled 6 cm in front of his face. Head on
    this is invisible, because they line up over the sockets and the texture
    does the rest; from three-quarters the far eye clears the bridge of his
    nose and hangs in open air beside his cheek. Nothing else in the compiler
    can see it -- both surfaces are individually valid, correctly wound,
    correctly wrapped and correctly textured, and the defect is only where they
    sit relative to each other, which no UV, bake or deviation metric measures.

    Scope is deliberately narrow. Only shells whose faces all use materials
    matching `token` are considered, because "a small shell sitting outside the
    body" also describes ninja-man's shoulder plates and fox-mascot's eye
    decals, and those belong exactly where they are. With no token this does
    nothing at all.

    The distance is measured rather than configured: the smallest setback at
    which no vertex of the assembly is outside its host's silhouette any more.
    """
    outcome = {"token": token, "clusters": []}
    if not token:
        return outcome

    working = bmesh.new()
    working.from_mesh(obj.data)
    bmesh.ops.remove_doubles(working, verts=working.verts[:], dist=1e-5)
    working.verts.index_update()
    groups = _shells(working)
    total = len(working.verts)

    materials = obj.data.materials
    prop_slots = set(
        index for index, material in enumerate(materials)
        if material and token in material.name.lower())
    if not prop_slots:
        working.free()
        return outcome

    def is_prop(group):
        slots = set(f.material_index for v in group for f in v.link_faces)
        return bool(slots) and slots <= prop_slots

    # The host of an eye is the shell it sits in, and that is not simply the
    # biggest one: field-scout-male's head is a separate 3.5k-vertex shell from
    # his 29k-vertex torso, and measured against the torso every ray escapes --
    # because it does. The torso is 3 cm below his eyes.
    hosts = []
    for group in groups:
        if len(group) < total * 0.01 or is_prop(group):
            continue
        index = set(v.index for v in group)
        host_bm = working.copy()
        host_bm.verts.index_update()
        bmesh.ops.delete(
            host_bm, geom=[v for v in host_bm.verts if v.index not in index],
            context="VERTS")
        # Cap the neck. A host with a hole in it fails the both-sides test
        # everywhere, because some axis runs out through the lid aperture one
        # way and out through the neck the other.
        boundary = [e for e in host_bm.edges if len(e.link_faces) == 1]
        if boundary:
            bmesh.ops.holes_fill(host_bm, edges=boundary, sides=0)
            boundary = [e for e in host_bm.edges if len(e.link_faces) == 1]
            if boundary:
                bmesh.ops.triangle_fill(host_bm, edges=boundary, use_beauty=True)
        hosts.append({
            "verts": len(group),
            "centre": sum((v.co for v in group), Vector()) / len(group),
            "tree": BVHTree.FromBMesh(host_bm),
            "bm": host_bm,
        })
    if not hosts:
        working.free()
        return outcome

    # An eye is four shells -- sclera, iris, pupil, highlight -- stacked a few
    # millimetres apart. Move one without the others and the eye comes apart.
    props = [g for g in groups if is_prop(g)]
    centres = [sum((v.co for v in g), Vector()) / len(g) for g in props]
    clusters = []
    for index, centre in enumerate(centres):
        for cluster in clusters:
            if (centre - cluster["centre"]).length < 0.030:
                cluster["shells"].append(index)
                cluster["centre"] = (cluster["centre"] + centre) / 2.0
                break
        else:
            clusters.append({"centre": centre.copy(), "shells": [index]})

    axes = _probe_axes()

    # Measure every cluster before moving any of them. A left eye that needs
    # 46.5mm and a right that needs 39.5mm are not two independent answers --
    # the difference is asymmetry in the head, and applying it would leave the
    # face lopsided. Take the largest, which seats them all, and let the
    # mirrored forward directions keep the pair symmetric.
    plan = []
    for cluster in clusters:
        verts = [v for i in cluster["shells"] for v in props[i]]
        host = min(hosts, key=lambda h: (h["centre"] - cluster["centre"]).length)
        forward = cluster["centre"] - host["centre"]
        forward.z = 0.0
        if forward.length < 1e-6:
            continue
        forward.normalize()

        before = _outside_silhouette(verts, host["tree"], axes)
        entry = {
            "centre_m": [round(c, 4) for c in cluster["centre"]],
            "shells": len(cluster["shells"]), "verts": len(verts),
            "outside_before": before, "push_mm": None,
        }
        outcome["clusters"].append(entry)
        if not before:
            continue

        best, distance = None, step
        while distance <= max_push + 1e-9:
            if not _outside_silhouette(verts, host["tree"], axes,
                                       offset=-forward * distance):
                best = distance
                break
            distance += step
        if best is None:
            print("[RETOPO] prop at {0} still breaks the silhouette at {1:.0f}mm"
                  "; left alone".format(entry["centre_m"], max_push * 1000))
            continue
        plan.append({"verts": verts, "forward": forward, "entry": entry,
                     "measured": best, "before": before})

    moved = 0
    if plan:
        agreed = max(item["measured"] for item in plan)
        outcome["setback_mm"] = round(agreed * 1000, 2)
        for item in plan:
            item["entry"]["measured_mm"] = round(item["measured"] * 1000, 2)
            item["entry"]["push_mm"] = round(agreed * 1000, 2)
            shift = -item["forward"] * agreed
            targets = set((round(v.co.x, 6), round(v.co.y, 6), round(v.co.z, 6))
                          for v in item["verts"])
            indices = [vert.index for vert in obj.data.vertices
                       if (round(vert.co.x, 6), round(vert.co.y, 6),
                           round(vert.co.z, 6)) in targets]
            for index in indices:
                obj.data.vertices[index].co += shift
            moved += len(indices)

            # Move the shape keys too, or nothing moves at all.
            #
            # field-scout-male carries a Basis plus four corrective elbow
            # blendshapes. With shape keys present the mesh vertex array is
            # not what the object shows: the moment anything enters edit mode
            # -- and the heal that follows immediately does, to weld the
            # export's split vertices -- Basis is written back over it and the
            # setback is silently undone. The build reported settling both
            # eyes 46.5mm and shipped them exactly where they started.
            #
            # Every block gets the same rigid shift, so the correctives keep
            # the deltas they were authored with.
            keys = obj.data.shape_keys
            if keys:
                for block in keys.key_blocks:
                    for index in indices:
                        block.data[index].co += shift
            print("[RETOPO] settled prop at {0}: {1} of {2} vertices were "
                  "outside the silhouette, needed {3:.1f}mm, set back {4:.1f}mm"
                  .format(item["entry"]["centre_m"], item["before"],
                          len(item["verts"]), item["measured"] * 1000,
                          agreed * 1000))

    obj.data.update()
    for host in hosts:
        host["bm"].free()
    working.free()
    outcome["vertices_moved"] = moved
    report["prop_settle"] = outcome
    return outcome


def rejoin_prop_shells(obj, props):
    """Put the preserved props back, before UVs and weights are built."""
    if props is None:
        return obj
    bpy.ops.object.select_all(action="DESELECT")
    props.select_set(True)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


def split_off_prop_shells(obj, token, report):
    """Lift prop geometry out of the mesh so the remesh cannot touch it.

    fox-mascot's eyes are four flat plates stacked five millimetres apart in
    front of his face -- outline, iris, pupil, highlight. QuadriFlow run over
    the whole character absorbs them into the head, and the bake that follows
    has to choose, for every texel near an eye, between plates that are now
    only a fraction of a millimetre apart with orange fur immediately behind
    them. It chooses wrongly in patches, which is why brown wedges appear to
    have been bitten out of his eyes.

    Remeshing them was never the point. They are 248 triangles of flat colour
    carrying a cartoon eye, they cost nothing to keep, and keeping them means
    the bake ray leaves the plate and arrives back on the same plate. They are
    still re-unwrapped with everything else after they are joined back, which
    is what repairs their UVs -- in the source all four pile 1.67x the sheet
    on top of each other.
    """
    materials = obj.data.materials
    slots = set(index for index, material in enumerate(materials)
                if material and token in material.name.lower())
    if not slots:
        return None
    faces = [poly for poly in obj.data.polygons if poly.material_index in slots]
    if not faces or len(faces) == len(obj.data.polygons):
        return None

    existing = set(bpy.data.objects)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    # Select inside edit mode, not before entering it. Face flags written in
    # object mode are discarded when the mesh is handed to the edit-mode
    # bmesh, which restores whatever was selected last -- everything, on a
    # freshly duplicated object. The separate then took the WHOLE character
    # out of the remesh and left QuadriFlow an empty mesh to work on.
    edit_bm = bmesh.from_edit_mesh(obj.data)
    edit_bm.faces.ensure_lookup_table()
    for face in edit_bm.faces:
        face.select_set(face.material_index in slots)
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.mesh.separate(type="SELECTED")
    bpy.ops.object.mode_set(mode="OBJECT")

    split = [o for o in bpy.data.objects if o not in existing]
    if len(split) != 1:
        print("[RETOPO] prop split produced {0} objects; not preserving".format(
            len(split)))
        return None
    props = split[0]
    # If this ever separates the character and keeps the eyes, the remesh gets
    # nothing to work on and the build fails several stages later with an
    # unrelated-looking message. Check it here instead.
    if tri_count(props.data) >= tri_count(obj.data):
        print("[RETOPO] prop split kept {0} triangles against {1} left behind; "
              "putting it back".format(tri_count(props.data), tri_count(obj.data)))
        rejoin_prop_shells(obj, props)
        return None
    report["props_preserved"] = {
        "token": token,
        "materials": sorted(materials[i].name for i in slots),
        "tris": tri_count(props.data),
    }
    print("[RETOPO] holding {0} prop triangles out of the remesh ({1})".format(
        tri_count(props.data), ", ".join(sorted(materials[i].name for i in slots))))
    return props


def region_of(bone_name):
    if not bone_name:
        return "other"
    lowered = bone_name.lower()
    for token, region in REGION_TOKENS:
        if token in lowered:
            side = ("_l" if lowered.endswith("_l")
                    else ("_r" if lowered.endswith("_r") else ""))
            return region + side if region in ("arm", "hand", "leg", "foot") else region
    return "other"


def is_facial(name, token="face"):
    """Does this material name mean facial skin?

    "EyeSurface" contains "face" through sur-FACE, which read ninja-man's eye
    material as skin. Strip the word that hides the token, and never treat an
    eye material as skin.
    """
    cleaned = name.lower().replace("surface", "")
    return token in cleaned and "eye" not in cleaned


def face_regions_by_bone(obj, armature):
    """Body region per face, from the weights the object already carries."""
    bone_names = {b.name for b in armature.data.bones}
    group_name = {g.index: g.name for g in obj.vertex_groups}
    vert_region = []
    for vert in obj.data.vertices:
        best_weight, best = 0.0, None
        for entry in vert.groups:
            name = group_name.get(entry.group)
            if name in bone_names and entry.weight > best_weight:
                best_weight, best = entry.weight, name
        vert_region.append(region_of(best))
    out = []
    for poly in obj.data.polygons:
        tally = Counter(vert_region[i] for i in poly.vertices)
        out.append(tally.most_common(1)[0][0])
    return out


def source_density_by_material(high, sources, original_uv):
    """Texels per square centimetre the source art actually holds, per material.

    This is the ceiling on what any layout can show. Give a region more texels
    than its source has and the result is not more detail, it is the source's
    own pixels magnified -- which reads exactly as "this has been upscaled".
    """
    if not original_uv:
        return {}, {}
    uv_layer = high.data.uv_layers.get(original_uv)
    if uv_layer is None:
        return {}, {}
    sizes = {}
    for index, slot in enumerate(high.material_slots):
        if slot.material is None:
            continue
        path = sources.get(slot.material.name)
        if not path or not Path(path).exists():
            continue
        image = bpy.data.images.load(path, check_existing=True)
        if image.size[0]:
            sizes[index] = (slot.material.name, float(image.size[0]))

    surface, uv_area = {}, {}
    for poly in high.data.polygons:
        if poly.material_index not in sizes:
            continue
        name = sizes[poly.material_index][0]
        # Blender areas are in square metres; one of those is 10,000 cm2.
        surface[name] = surface.get(name, 0.0) + poly.area * 10000.0
        points = [uv_layer.data[i].uv for i in poly.loop_indices]
        total = 0.0
        for i in range(1, len(points) - 1):
            a, b, c = points[0], points[i], points[i + 1]
            total += abs((b[0] - a[0]) * (c[1] - a[1])
                         - (c[0] - a[0]) * (b[1] - a[1])) * 0.5
        uv_area[name] = uv_area.get(name, 0.0) + total

    density = {}
    for _, (name, size) in sizes.items():
        if surface.get(name, 0.0) > 1e-9:
            density[name] = size * size * uv_area.get(name, 0.0) / surface[name]
    return density, surface


def uv_area_by_material(obj, uv_name):
    """UV area each material covers, as a multiple of the unit square.

    A material whose faces span more UV area than the whole sheet is not
    laid out, it is piled up. fox-mascot's four eye materials each measure
    1.67 from 144 faces, every one spanning the full 0-1 range, which is
    what makes his eyeballs sample body fur in the engine.
    """
    layer = obj.data.uv_layers.get(uv_name) if uv_name else None
    if layer is None:
        return {}
    names = [s.material.name if s.material else "<none>"
             for s in obj.material_slots]
    area = {}
    for poly in obj.data.polygons:
        if poly.material_index >= len(names):
            continue
        points = [layer.data[i].uv for i in poly.loop_indices]
        total = 0.0
        for i in range(1, len(points) - 1):
            a, b, c = points[0], points[i], points[i + 1]
            total += abs((b[0] - a[0]) * (c[1] - a[1])
                         - (c[0] - a[0]) * (b[1] - a[1])) * 0.5
        name = names[poly.material_index]
        area[name] = area.get(name, 0.0) + total
    return area


def uv_layout_metrics(obj):
    """Measure atlas area and reject layouts collapsed onto a near-1D diagonal."""
    layer = obj.data.uv_layers.active
    if layer is None:
        return {"triangle_area": 0.0, "nondegenerate_fraction": 0.0,
                "minor_major_variance_ratio": 0.0}
    points = []
    total_area = 0.0
    nondegenerate = 0
    triangles = 0
    for poly in obj.data.polygons:
        polygon_uv = [layer.data[index].uv.copy() for index in poly.loop_indices]
        for index in range(1, len(polygon_uv) - 1):
            a, b, c = polygon_uv[0], polygon_uv[index], polygon_uv[index + 1]
            area = abs((b.x - a.x) * (c.y - a.y) -
                       (c.x - a.x) * (b.y - a.y)) * 0.5
            total_area += area
            nondegenerate += int(area > 1e-10)
            triangles += 1
        points.extend(polygon_uv)
    if not points:
        return {"triangle_area": 0.0, "nondegenerate_fraction": 0.0,
                "minor_major_variance_ratio": 0.0}
    mean_u = sum(point.x for point in points) / len(points)
    mean_v = sum(point.y for point in points) / len(points)
    variance_u = sum((point.x - mean_u) ** 2 for point in points) / len(points)
    variance_v = sum((point.y - mean_v) ** 2 for point in points) / len(points)
    covariance = sum((point.x - mean_u) * (point.y - mean_v)
                     for point in points) / len(points)
    trace = variance_u + variance_v
    discriminant = math.sqrt(max((variance_u - variance_v) ** 2 +
                                 4.0 * covariance ** 2, 0.0))
    major = (trace + discriminant) * 0.5
    minor = (trace - discriminant) * 0.5
    return {
        "triangle_area": round(total_area, 6),
        "nondegenerate_fraction": round(nondegenerate / max(triangles, 1), 6),
        "minor_major_variance_ratio": round(minor / max(major, 1e-12), 6),
    }


def original_uv_name(obj):
    return obj.data.uv_layers.active.name if obj.data.uv_layers else None


def skin_faces_in_head(high, sources, original_uv, region_of_vert):
    """Find facial skin by colour, for characters that do not author it.

    field-scout-female has a dedicated face material and needs none of this.
    ninja-man has one body atlas and a hood, so his bone-derived `head` region
    is 30% of the mesh -- almost all of it cloth -- and his actual face ends up
    as a patch of roughly 180x360 texels in a 4096 sheet. Weighting `head`
    there spends the entire budget on the hood.

    His face is also the only skin-coloured thing on him, so it can be found by
    sampling the accepted albedo at each head triangle and testing for skin.
    Colour alone is not trustworthy -- fox-mascot is orange from nose to tail
    and would report a face the size of its whole head -- so the result is only
    used when it selects a MINORITY of the head. That is the difference between
    "there is a face in here" and "this whole animal is the colour of a face".
    """
    if not original_uv or not sources:
        return set()
    uv_layer = high.data.uv_layers.get(original_uv)
    if uv_layer is None:
        return set()

    images = {}
    for index, slot in enumerate(high.material_slots):
        if slot.material is None:
            continue
        path = sources.get(slot.material.name)
        if not path or not Path(path).exists():
            continue
        image = bpy.data.images.load(path, check_existing=True)
        width, height = image.size
        if not width or not height:
            continue
        pixels = np.array(image.pixels[:], dtype=np.float32).reshape(height, width, 4)
        images[index] = (pixels, width, height)
    if not images:
        return set()

    head_polys, skin_polys = [], []
    for poly in high.data.polygons:
        if region_of_vert(poly) != "head":
            continue
        head_polys.append(poly)
        entry = images.get(poly.material_index)
        if entry is None:
            continue
        pixels, width, height = entry
        us = vs = 0.0
        for loop_index in poly.loop_indices:
            uv = uv_layer.data[loop_index].uv
            us += uv[0]
            vs += uv[1]
        count = len(poly.loop_indices)
        x = int(min(max(us / count, 0.0), 0.9999) * (width - 1))
        y = int((1.0 - min(max(vs / count, 0.0), 0.9999)) * (height - 1))
        r, g, b = (float(c) for c in pixels[y, x, :3])
        high_c, low_c = max(r, g, b), min(r, g, b)
        if high_c < 0.18 or high_c > 0.99:
            continue
        chroma = high_c - low_c
        # Skin: red is the strongest channel, blue the weakest, and the whole
        # thing is desaturated. Cloth in this cohort is blue, grey or olive.
        if r == high_c and b == low_c and 0.04 < chroma < 0.42 and g > b:
            skin_polys.append(poly)

    if not head_polys:
        return set()
    fraction = len(skin_polys) / float(len(head_polys))
    print("[RETOPO] skin-in-head test: {0} of {1} head triangles ({2:.0%})".format(
        len(skin_polys), len(head_polys), fraction))
    if fraction >= 0.4 or fraction < 0.01:
        print("[RETOPO] skin test not used: {0}".format(
            "the whole head is skin-coloured" if fraction >= 0.4
            else "found almost none"))
        return set()
    verts = set()
    for poly in skin_polys:
        verts.update(poly.vertices)
    return verts


def face_regions(low, armature, high, face_material="face", sources=None):
    """Body region per retopo face, read from the skinned original.

    The remeshed copy carries no weights yet, so the region is taken from the
    nearest vertex of the original -- which is skinned, and therefore knows
    which body part each point belongs to.

    The facial skin is separated out as its own region, because the bones
    cannot see it: the skull, the hair and the neck all weight to `head`, so
    weighting `head` for texel density spends most of the budget on hair. On
    field-scout-female the head region is 37.6% of the sheet while the face
    material is 5.9% -- the same density boost costs six times less when it is
    aimed at the part that is actually read as a likeness. That distinction is
    already authored, as a separate face material, so it is taken from there
    rather than guessed from geometry.
    """
    bone_names = {b.name for b in armature.data.bones}
    group_name = {g.index: g.name for g in high.vertex_groups}
    high_regions = []
    for vert in high.data.vertices:
        best_weight, best = 0.0, None
        for group in vert.groups:
            name = group_name.get(group.group)
            if name in bone_names and group.weight > best_weight:
                best_weight, best = group.weight, name
        high_regions.append(region_of(best))

    # Vertices touched by a face-material triangle. Taken per vertex so it can
    # ride the same nearest-vertex lookup as the bone regions.
    facial = set()
    slot_names = [s.material.name.lower() if s.material else ""
                  for s in high.material_slots]
    token = face_material.lower()
    for poly in high.data.polygons:
        if poly.material_index < len(slot_names) and is_facial(slot_names[poly.material_index], token):
            facial.update(poly.vertices)
    if not facial:
        # Nothing authored a face material; find it by colour instead.
        def poly_region(poly):
            tally = Counter(high_regions[i] for i in poly.vertices)
            return tally.most_common(1)[0][0]

        facial = skin_faces_in_head(high, sources or {}, original_uv_name(high),
                                    poly_region)
    for index in facial:
        high_regions[index] = "face"

    tree = KDTree(len(high.data.vertices))
    for index, vert in enumerate(high.data.vertices):
        tree.insert(high.matrix_world @ vert.co, index)
    tree.balance()

    out = []
    for poly in low.data.polygons:
        centre = low.matrix_world @ poly.center
        _, nearest, _ = tree.find(centre)
        # find() returns None when the query point is not a finite location.
        out.append("other" if nearest is None else high_regions[nearest])
    return out


def silhouette_grid(obj, lo, extent, bins=64):
    mw = obj.matrix_world
    pts = np.array([(mw @ v.co)[:] for v in obj.data.vertices], dtype=np.float64)
    idx = np.clip(np.floor((pts - lo) / extent * (bins - 1)).astype(int), 0, bins - 1)
    grid = np.zeros((bins, bins, bins), dtype=bool)
    grid[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return grid


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    # Absolute, because Image.save() resolves a relative filepath_raw against
    # Blender's own notion of the current directory rather than the shell's,
    # and silently writes nothing when that misses.
    src = Path(argv[0]).resolve()
    out_dir, report_path = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    budget = arg(argv, "--budget", 12000, int)
    resolution = arg(argv, "--resolution", 2048, int)
    samples = arg(argv, "--samples", 24, int)
    # Rays must reach. Where the remesh pulls furthest from the original --
    # a heavily reduced head, a thin collar -- a short ray finds nothing, and
    # a texel that is never hit keeps the pass fill. For BaseColor that fill
    # is black, so ninja-man's head baked almost entirely black and read as a
    # texture that had been destroyed.
    #
    # A short ray was tried as a fix for fox-mascot's eyes baking as fur and
    # made no difference at all, because that was never a ray problem: its
    # eye materials are flat-coloured and had been handed the body atlas.
    # Short rays, now that a miss is repaired rather than left black.
    #
    # 2cm of extrusion is long enough to leave a neck and hit the scarf in
    # front of it, which is where field-scout-female picked up brown speckles
    # along her jaw and collar. Short rays were tried before and made things
    # worse -- ninja-man's head baked black -- but only because a ray that
    # reached nothing left the clear value behind. fill_unbaked now grows the
    # nearest baked colour into those texels, so the safe direction is short.
    cage = arg(argv, "--cage", 0.003, float)
    ray_distance = arg(argv, "--ray-distance", 0.010, float)
    weld = arg(argv, "--weld", 0.0001, float)
    min_shell_frac = arg(argv, "--min-shell-frac", 0.001, float)
    base_color_path = arg(argv, "--basecolor", None)
    texmap_path = arg(argv, "--texmap", None)
    # Texel budget per body region, as a UV scale factor. Density goes as the
    # square, so 1.45 on the head is roughly twice the texels per cm2.
    region_weights = json.loads(arg(argv, "--region-weight", DEFAULT_REGION_WEIGHT))
    face_material = arg(argv, "--face-material", "face")
    max_influences = arg(argv, "--max-influences", 4, int)
    min_remesh_faces = arg(argv, "--min-remesh-faces", 2000, int)
    sharp_angle = arg(argv, "--sharp", 72.0, float)
    strategy = arg(argv, "--strategy", "auto")
    normal_min_mm = arg(argv, "--normal-min-mm", NORMAL_MAP_MIN_DETAIL_MM, float)
    settle_props = arg(argv, "--settle-props", None)
    preserve_props = arg(argv, "--preserve-props", None)
    close_holes = arg(argv, "--close-holes", "", str)
    # A static prop is the same job with the skeleton removed. Nothing about
    # healing, unwrapping, baking or packaging changes; what does not apply is
    # every stage that reads bones -- weight transfer, the influence cap, the
    # armature modifier, and semantic UV charts cut at body-region boundaries.
    # See tests/test_planner.py::test_static_prop_never_enters_rigging.
    kind = arg(argv, "--kind", "humanoid", str)
    # The texture gate's own floor, passed in rather than duplicated, so the
    # atlas cannot be stepped down to a size that gate will then reject.
    min_density = arg(argv, "--min-density", 0.0, float)
    prebuilt_low_path = arg(argv, "--prebuilt-low", None)
    allow_missing_basecolor = arg(
        argv, "--allow-missing-basecolor", "", str
    ).strip().lower() in {"1", "true", "yes"}
    rigged = kind != "static_prop"
    if prebuilt_low_path and rigged:
        print("[RETOPO] FAILED: --prebuilt-low is currently gated to static props")
        return 1
    if allow_missing_basecolor and (rigged or not prebuilt_low_path):
        print("[RETOPO] FAILED: --allow-missing-basecolor requires a prebuilt static prop")
        return 1

    sources = {}
    if texmap_path and Path(texmap_path).exists():
        sources = json.loads(Path(texmap_path).read_text(encoding="utf-8-sig"))

    source_suffix = src.suffix.lower()
    if source_suffix == ".blend":
        # Semantic cleanup's native BLEND is the topology authority.  Read it
        # directly so the bake donor is the exact approved cleanup derivative
        # instead of a face-corner-splitting transport re-export.
        bpy.ops.wm.open_mainfile(filepath=str(src))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    if source_suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(src))
    elif source_suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(src))
    elif source_suffix != ".blend":
        print("[RETOPO] FAILED: source must be BLEND, FBX, GLB, or GLTF")
        return 1

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not meshes:
        print("[RETOPO] FAILED: need a mesh")
        return 1
    if rigged and not armatures:
        print("[RETOPO] FAILED: need a mesh and an armature")
        return 1
    if not rigged and armatures:
        print("[RETOPO] FAILED: --kind static_prop, but this file has an "
              "armature; it is a character, not a prop")
        return 1
    high = max(meshes, key=lambda o: len(o.data.polygons))
    armature = armatures[0] if armatures else None
    report_kind = kind
    original_uv = high.data.uv_layers.active.name if high.data.uv_layers else None
    source_densities, source_surface = source_density_by_material(
        high, sources, original_uv)
    uv_areas = uv_area_by_material(high, original_uv)
    # A layout nobody can preserve. Keeping the original UVs only makes sense
    # if they ARE a layout; where a material piles its faces on top of the
    # whole sheet, a passthrough bake paints that material's colour over
    # everything else -- fox-mascot came out 3.35x too bright with 62% of the
    # atlas flooded by his eye highlight. Such an asset has to be remeshed and
    # re-unwrapped, which is the one thing that gives those faces a sane chart.
    overlapping = sorted(n for n, a in uv_areas.items() if a > UV_AREA_LIMIT)

    report = {
        "source": str(src),
        "asset_kind": report_kind,
        "blender_version": bpy.app.version_string,
        "high_tris": tri_count(high.data),
        "budget": budget,
        "resolution": resolution,
    }

    # Seat any floating prop shells before anything is derived from this
    # mesh. Doing it here rather than on the retopo keeps the bake source and
    # the bake target agreeing about where the eyes are; move only one of
    # them and every ray from the moved eye lands on the socket behind it.
    if settle_props:
        settle_prop_shells(high, settle_props, report)

    report["source_density_by_material"] = {
        k: round(v, 1) for k, v in source_densities.items()}

    lo_pt = np.array([(high.matrix_world @ v.co)[:] for v in high.data.vertices])
    lo_b, hi_b = lo_pt.min(axis=0), lo_pt.max(axis=0)
    extent = np.maximum(hi_b - lo_b, 1e-6)
    high_grid = silhouette_grid(high, lo_b, extent)

    if prebuilt_low_path:
        prebuilt_path = Path(prebuilt_low_path).resolve()
        if not prebuilt_path.is_file():
            print("[RETOPO] FAILED: prebuilt low mesh missing at {0}".format(prebuilt_path))
            return 1
        before_import = set(bpy.data.objects)
        if prebuilt_path.suffix.lower() == ".fbx":
            bpy.ops.import_scene.fbx(filepath=str(prebuilt_path))
        elif prebuilt_path.suffix.lower() in {".glb", ".gltf"}:
            bpy.ops.import_scene.gltf(filepath=str(prebuilt_path))
        else:
            print("[RETOPO] FAILED: prebuilt low must be FBX, GLB, or GLTF")
            return 1
        imported = [
            obj for obj in bpy.data.objects
            if obj not in before_import and obj.type == "MESH"
        ]
        if not imported:
            print("[RETOPO] FAILED: prebuilt low contains no mesh")
            return 1
        bpy.ops.object.select_all(action="DESELECT")
        for obj in imported:
            obj.select_set(True)
        low = max(imported, key=lambda obj: len(obj.data.polygons))
        bpy.context.view_layer.objects.active = low
        if len(imported) > 1:
            bpy.ops.object.join()
        low.name = high.name + "_retopo"
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        for modifier in list(low.modifiers):
            low.modifiers.remove(modifier)
        before_remesh = low.data
        report["remesh_mode"] = "prebuilt_voxel_qem"
        report["prebuilt_low"] = str(prebuilt_path)
        report["shells"] = []
        report["shells_refused"] = 0
        report["shells_preserved"] = 0
        report["faces_preserved"] = 0
        report["heal"] = {"skipped": "prebuilt low is already a closed reviewed candidate"}
        print("[RETOPO] prebuilt low: {0} triangles".format(tri_count(low.data)))
    else:
        # Duplicate and heal the copy; the original stays as the bake source.
        bpy.ops.object.select_all(action="DESELECT")
        high.select_set(True)
        bpy.context.view_layer.objects.active = high
        bpy.ops.object.duplicate()
        low = bpy.context.view_layer.objects.active
        low.name = high.name + "_retopo"
        for modifier in list(low.modifiers):
            low.modifiers.remove(modifier)

        bpy.ops.object.select_all(action="DESELECT")
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        healed = heal(low, weld, min_shell_frac, report)
        print("[RETOPO] healed: {0} -> {1} components, {2} non-manifold edges".format(
            report["heal"]["imported"]["components"], healed["components"],
            healed["non_manifold_edges"]))

        # Keep the healed mesh, in case the remesh turns out not to be worth it.
        before_remesh = low.data.copy()
        props = split_off_prop_shells(low, preserve_props, report) if preserve_props else None
        low = remesh(low, budget, report, min_remesh_faces, armature, strategy)
        low = rejoin_prop_shells(low, props)

    # Close what is still open, AFTER the remesh rather than before it.
    #
    # fox-mascot's head has 181 boundary edges that survive the heal --
    # fill_holes only closes what it can fan-triangulate and gives up on the
    # rest -- and they sit in a crescent around each eye socket. You see
    # straight into his head through them, which is what "missing holes around
    # his eyes" means, and the remesh makes them larger and tidier rather than
    # smaller.
    #
    # The order is not a preference. Running make_manifold BEFORE QuadriFlow
    # was tried and it made QuadriFlow refuse his body outright; that is
    # recorded in make_manifold's own docstring. Afterwards it is safe, and the
    # caps are created before the unwrap, so they get UVs and bake like any
    # other face.
    #
    # Opt-in per asset, because capping every boundary loop is not universally
    # right: field-scout-male's eyelid aperture IS a boundary loop, and closing
    # it would seal his eyes inside his head.
    if close_holes:
        report["closed_holes"] = make_manifold(low)
        print("[RETOPO] closed holes: {0} boundary edges left, {1} over two "
              "faces, {2} bowties".format(
                  report["closed_holes"]["boundary_edges"],
                  report["closed_holes"]["edges_over_two_faces"],
                  report["closed_holes"]["bowtie_verts"]))

    # The cage is built by pushing vertices along their own normals, so a
    # shell whose winding points inward pushes its cage INWARD and every ray
    # from it fires away from the surface. field-scout-male baked 54% of its
    # sheet and the rest stayed at the clear value -- a black character with
    # correct geometry. Joining shells does not harmonise winding, so do it
    # here, once, on the finished mesh.
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    edit_op(lambda: bpy.ops.mesh.normals_make_consistent(inside=False))
    report["low_tris"] = tri_count(low.data)
    report["low_quads"] = sum(1 for p in low.data.polygons if len(p.vertices) == 4)
    report["quadriflow"] = "PREBUILT_NOT_RUN" if prebuilt_low_path else "PER_SHELL"

    # QuadriFlow reports refusal as a warning plus CANCELLED, never an
    # exception, so the only reliable check is whether topology changed. What
    # to DO about that depends on whether there is a recorded reason.
    #
    # A silent no-op is a bug and stays a hard failure. A recorded refusal is
    # an honest outcome: field-scout-male's body is rejected by QuadriFlow for
    # reasons nothing measurable explains, and preserving it beats shipping a
    # decimated likeness. The rest of the stage -- normal map, AO, semantic
    # UVs, four influences -- is worth having on its own.
    # Not every character can be reduced, and that is not a failure.
    #
    # QuadriFlow refuses field-scout-male's body outright, for reasons nothing
    # measurable explains. Cutting him into body regions and remeshing the
    # pieces does work -- but preserve_boundary keeps the SHAPE of a cut, not
    # its vertices, so the pieces no longer share points and he ships torn
    # along every seam. Snapping and boundary-welding both failed to close it.
    #
    # So when the geometry cannot be reduced, keep it exactly and do the rest
    # of the job anyway: semantic UVs weighted at the face, the art
    # transferred into that layout, ambient occlusion, four influences. What
    # is NOT possible is a normal map -- there is no denser surface to capture
    # -- and selected-to-active baking, which against a coincident copy of the
    # same mesh bakes fully-occluded AO and a black albedo. Both are handled
    # by baking the mesh against itself instead.
    # A barely-remeshed mesh must not be re-unwrapped.
    #
    # The semantic layout is built for a clean quad field. Where most of the
    # geometry is still the original -- field-scout-male keeps 90% of his faces,
    # because QuadriFlow accepts only his hair -- re-unwrapping throws away a
    # good layout that still fits and replaces it with a shattered one: 499
    # islands against field-scout-female's 7, and hard-edged rectangles across
    # his nose and mouth where the charts meet. A 7.5% triangle saving is not
    # worth a face.
    remeshed_faces = sum(
        s.get("faces_in", 0) for s in report.get("shells", []) if not s.get("kept"))
    if prebuilt_low_path or report.get("remesh_mode") == "whole":
        remeshed_faces = report["high_tris"]
    report["faces_remeshed_fraction"] = round(
        remeshed_faces / float(max(report["high_tris"], 1)), 3)
    report["uv_area_by_material"] = {k: round(v, 3) for k, v in uv_areas.items()}
    report["materials_with_piled_uvs"] = overlapping
    passthrough = (not prebuilt_low_path and (report["low_quads"] == 0
                   or report["low_tris"] >= report["high_tris"] * 0.95
                   or report["faces_remeshed_fraction"] < REMESH_COVERAGE_MIN))
    if passthrough and overlapping and rigged:
        # Refuse, rather than quietly taking a worse road. Keeping these UVs
        # floods the atlas with one material's colour; re-unwrapping the
        # original triangle soup instead is the ninja-man trap -- it took
        # fox-mascot to 1,456 islands at 51% coverage and a third of his
        # source density. The only good answer is to remesh him, which the
        # caller has to choose.
        report["ok"] = False
        report["failure"] = (
            "passthrough is unsafe: {0} pile their UVs over the whole sheet "
            "({1}), so a passthrough bake paints one material over the rest. "
            "Build this asset with --strategy auto so it is remeshed and "
            "re-unwrapped.".format(", ".join(overlapping),
                                   ", ".join("{0}={1:.2f}".format(
                                       n, uv_areas[n]) for n in overlapping)))
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("[RETOPO] FAILED: {0}".format(report["failure"]))
        return 1
    report["reduced"] = not passthrough
    if passthrough and low.data is not before_remesh:
        # Put the original geometry back. A partial remesh leaves the shells it
        # touched with no UVs at all -- QuadriFlow discards them -- so keeping
        # "the original layout" on a partly-remeshed mesh means baking garbage
        # onto whatever was rebuilt. Either the remesh is worth a new layout or
        # the mesh reverts; there is no useful middle.
        stale = low.data
        low.data = before_remesh
        bpy.data.meshes.remove(stale)
        report["low_tris"] = tri_count(low.data)
        report["low_quads"] = sum(
            1 for p in low.data.polygons if len(p.vertices) == 4)
        report["reverted_to_healed_geometry"] = True
        print("[RETOPO] reverted to the healed original: {0} tris".format(
            report["low_tris"]))
    elif low.data is before_remesh:
        pass
    if passthrough:
        refusals = sorted({s.get("reason") for s in report.get("shells", [])
                           if s.get("kept") and s.get("reason")})
        report["no_reduction_reason"] = "; ".join(refusals) or "QuadriFlow refused"
        print("[RETOPO] no reduction possible ({0}); keeping the geometry and "
              "rebuilding UVs, AO and weights on it".format(
                  report["no_reduction_reason"]))

    iou = float(np.logical_and(high_grid, silhouette_grid(low, lo_b, extent)).sum())
    iou /= float(max(np.logical_or(
        high_grid, silhouette_grid(low, lo_b, extent)).sum(), 1))
    report["silhouette_iou"] = round(iou, 4)

    # Only re-unwrap a mesh that was actually remeshed.
    #
    # The semantic layout is built for a clean quad field. Run on the original
    # triangle soup it is much worse than the xatlas layout it replaces:
    # ninja-man went from 942 islands at 71.3% coverage and 146 texels/cm2 to
    # 1,630 islands at 44.1% coverage and 76-108 texels/cm2, and the character
    # lost the blue in his clothes. Where the geometry is kept, the UVs it
    # shipped with are kept too, and the stage adds what it can instead:
    # ambient occlusion and a four-influence weight clamp.
    # A kept-geometry prop re-unwraps only when its incoming layout cannot be
    # kept, which is not the same as always.
    #
    # The first prop through here made it look unconditional. office-chair's six
    # materials each tile their own 256px texture across the surface, covering
    # 0.55 to 14.6 times the UV square: there is no layout there to preserve,
    # and collapsing them into one atlas is the whole point of compiling it.
    #
    # A generated mesh is the opposite case and re-unwrapping it is the same
    # trap this stage already refuses for characters. A raw Pixal3D chair
    # arrives as one material on a sane 0.58-of-the-square layout, and 971,442
    # triangles that QuadriFlow will not touch. Re-unwrapping that soup gave 17
    # texels/cm2 against a source holding 324, and the texture gate rejected it
    # -- correctly, and for a layout this stage had just thrown away.
    #
    # So: keep a layout that is a layout. Replace one that piles materials on
    # top of each other, which is the case where a single shared atlas has no
    # choice but to be rebuilt.
    contested = bool(overlapping) or len([
        name for name in (sources or {}) if bpy.data.materials.get(name)]) > 1
    unwrap = report.get("reduced", True) or (not rigged and contested)
    report["unwrap_reason"] = (
        "remeshed" if report.get("reduced", True)
        else ("prop, incoming layout unusable" if (not rigged and contested)
              else "kept: the incoming layout is usable"))
    semantic_regions = []
    if unwrap:
        # --- unwrap into semantic charts ----------------------------------------
        # Seams where the body region changes, not wherever the surface creases.
        # smart_project measured worse than the xatlas layout it was replacing
        # (954 islands vs 395); region seams measured 31.
        # Charts cut at body-region boundaries need bones to define the
        # regions. A prop has none, so its seams come from surface creases
        # alone, which is what the sharp-angle pass below does anyway.
        semantic_regions = (face_regions(low, armature, high, face_material, sources)
                            if rigged else [0] * len(low.data.polygons))
        bm = bmesh.new()
        bm.from_mesh(low.data)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        seams = 0
        # 50 degrees cuts a seam at every ordinary fold. On field-scout-female that
        # still gave 28 islands, but ninja-man -- a join of 24 shells of ragged,
        # layered cloth -- came out with 5,664 seams and 265 islands, 166 of them
        # under 64 pixels. His head became a mosaic of tiny islands, each bleeding
        # at its edges, which reads as a face made of flat grey tiles. A seam is
        # meant to mark a genuine crease, not a gentle bend.
        sharp = math.radians(sharp_angle)
        for edge in bm.edges:
            linked = edge.link_faces
            if len(linked) != 2:
                edge.seam = True
                seams += 1
                continue
            a, b = linked
            if semantic_regions[a.index] != semantic_regions[b.index]:
                edge.seam = True
                seams += 1
            elif edge.calc_face_angle(0.0) > sharp:
                edge.seam = True
                seams += 1
        bm.to_mesh(low.data)
        bm.free()
        report["seam_edges"] = seams
        report["region_face_counts"] = dict(Counter(semantic_regions))

        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        if not rigged and prebuilt_low_path:
            # Angle-based unwrap can converge to a formally finite but nearly
            # one-dimensional diagonal on dense closed static props. That
            # poisoned the chair atlas while the old gate admired its 0-1
            # bounds. Smart Project produces ordinary 2D charts for this case;
            # articulated assets retain their deliberately authored seams.
            bpy.ops.uv.smart_project(
                angle_limit=math.radians(66.0),
                island_margin=0.006,
                area_weight=0.0,
                correct_aspect=True,
                scale_to_bounds=False,
            )
            report["unwrap_operator"] = "SMART_PROJECT_STATIC_PREBUILT"
        else:
            bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=0.006)
            report["unwrap_operator"] = "ANGLE_BASED"
        bpy.ops.object.mode_set(mode="OBJECT")

        # Weight the charts before packing, so the face is not rationed like a boot.
        #
        # pack_islands rescales every island by ONE common factor to fit the sheet,
        # which means relative island sizes set before packing survive it. Scaling
        # a region's UVs by s multiplies its texel density by s^2; the cost is
        # spread over every other region through that common factor, and is small
        # here because the head is a small share of the sheet.
        #
        # Region seams guarantee no island spans two regions, so scaling per face
        # scales whole islands and cannot tear one apart. The scale is about the
        # UV origin -- islands fly off the sheet, and packing puts them back.
        # `face` and `head` are alternatives, not a stack. Where the art has a
        # separate face material the facial skin is its own region and gets the
        # weight; the surrounding skull, hair and neck do not need it and are
        # expensive -- on field-scout-female `head` is 37.6% of the sheet against
        # the face material's 5.9%. Assets with a single body atlas have no `face`
        # region to aim at, so they fall back to weighting `head` more gently,
        # because there the same factor costs six times as much.
        region_weights = dict(region_weights)
        if any(r == "face" for r in semantic_regions):
            region_weights.pop("head", None)
            # Size the face weight from what it costs, not from a fixed number.
            #
            # Scaling a region by w multiplies its density by w^2 and grows the
            # sheet by share*(w^2-1), which every other region pays for through the
            # common pack factor. Fixing w instead of the cost gets it backwards:
            # field-scout-female's face is 10% of her triangles and ninja-man's is
            # 3% of his, so the same 1.55 costs her three times more and buys him
            # far too little -- his face lands as a patch of about 180x360 texels
            # in a 4096 sheet.
            #
            # Fixing the COST inverts that: w = sqrt(1 + budget/share), capped so a
            # sliver of a face cannot demand the whole atlas.
            share = sum(1 for r in semantic_regions if r == "face") / float(
                max(len(semantic_regions), 1))
            affordable = min(math.sqrt(1.0 + FACE_AREA_BUDGET / max(share, 1e-4)), 3.0)

            # Never magnify past what the source holds.
            #
            # A boost is only worth spending where the art has more detail on the
            # face than on the body. field-scout-female's face comes from a
            # dedicated 1024 projection at 721 texels/cm2 against a 306 body, so
            # 2.4x more really is there to recover. field-scout-male's face and
            # body share ONE uniform 4096 atlas at 303, and the same boost put his
            # head at 456 -- half again more texels than the source has, which is
            # just his own pixels enlarged -- while paying for it by dropping his
            # torso to 198. That trade buys nothing and looks oversharpened.
            densities = source_densities
            facial = [d for n, d in densities.items() if is_facial(n)]
            others = [d for n, d in densities.items() if not is_facial(n)]
            if facial and others:
                headroom = max((sum(facial) / len(facial))
                               / max(sum(others) / len(others), 1e-6), 1.0)
            elif densities:
                # One atlas for everything: the face is no better served than the
                # sleeve, so there is nothing to recover by magnifying it.
                headroom = 1.0
            else:
                headroom = affordable ** 2
            weight = round(min(affordable, math.sqrt(headroom)), 3)
            region_weights["face"] = weight
            report["face_share"] = round(share, 4)
            report["source_density_by_material"] = {
                k: round(v, 1) for k, v in densities.items()}
            report["face_detail_headroom"] = round(headroom, 2)
            print("[RETOPO] face is {0:.1%} of the mesh; affordable x{1:.2f}, source "
                  "holds x{2:.2f} -> weight {3:.2f} (density x{4:.1f})".format(
                      share, affordable, math.sqrt(headroom), weight, weight ** 2))
        else:
            region_weights.pop("face", None)

        layer = low.data.uv_layers.active
        scaled = Counter()
        for poly in low.data.polygons:
            region = semantic_regions[poly.index]
            weight = region_weights.get(region, 1.0)
            if weight == 1.0:
                continue
            for loop_index in poly.loop_indices:
                uv = layer.data[loop_index].uv
                uv[0] *= weight
                uv[1] *= weight
            scaled[region] += 1
        report["region_uv_scale"] = {r: region_weights[r] for r in scaled}
        print("[RETOPO] chart weights: {0}".format(report["region_uv_scale"]))

        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(rotate=True, margin=0.006)
        bpy.ops.object.mode_set(mode="OBJECT")

        layout_metrics = uv_layout_metrics(low)
        report["uv_layout_metrics"] = layout_metrics
        if (layout_metrics["triangle_area"] < 0.20 or
                layout_metrics["nondegenerate_fraction"] < 0.99 or
                layout_metrics["minor_major_variance_ratio"] < 0.02):
            print("[RETOPO] FAILED: unusable UV layout metrics {0}".format(
                layout_metrics))
            return 1

    # --- atlas size -----------------------------------------------------------
    # Do not output more texels than the source art holds.
    #
    # A 4096 sheet is not free: it is 4x the memory of 2048 and, if the source
    # cannot fill it, 4x the memory for the same picture enlarged. fox-mascot's
    # albedo is a 2048 map spread over a big furry surface -- 43 texels/cm2 --
    # and baking him at 4096 gave about 200, magnifying his art fourfold.
    # field-scout-male's source is 313 and lands at 270, so he keeps 4096.
    #
    # A little headroom is allowed, because the new layout packs tighter than
    # the old one and losing that would waste the gain.
    chosen = resolution
    if not report.get("reduced", True) and rigged:
        # Passthrough keeps the original UV layout, so the right atlas size is
        # simply the one the art already uses. Estimating density from that
        # layout is not safe -- it overlaps and mirrors charts, which inflates
        # the summed UV area and made ninja-man look like he was being given
        # 482 texels/cm2 when the gate measured 146. Stepping him down on that
        # reading cost him three quarters of his resolution.
        sizes = []
        for path in set((sources or {}).values()):
            if Path(path).exists():
                image = bpy.data.images.load(path, check_existing=True)
                if image.size[0]:
                    sizes.append(int(image.size[0]))
        if sizes:
            chosen = min(max(sizes), resolution)
        report["atlas"] = {"requested": resolution, "chosen": chosen,
                           "rule": "passthrough: match the source texture"}
        if chosen != resolution:
            print("[RETOPO] atlas {0} -> {1}: matching the source texture".format(
                resolution, chosen))
    elif source_densities:
        surface_cm2 = sum(poly.area for poly in low.data.polygons) * 10000.0
        uv_layer = low.data.uv_layers.active
        uv_total = 0.0
        if uv_layer is not None:
            for poly in low.data.polygons:
                points = [uv_layer.data[i].uv for i in poly.loop_indices]
                for i in range(1, len(points) - 1):
                    a, b, c = points[0], points[i], points[i + 1]
                    uv_total += abs((b[0] - a[0]) * (c[1] - a[1])
                                    - (c[0] - a[0]) * (b[1] - a[1])) * 0.5
        # Which source density is the ceiling depends on what the materials
        # ARE. A character carries a body atlas and maybe a face projection,
        # and the face legitimately sets the bar for the whole sheet -- that is
        # the region anyone looks at. A prop carries one small tiling texture
        # per surface type, and taking the maximum lets the smallest of them
        # decide: the chair's rust patch reads 11,518 texels/cm2 because a
        # 256px tile repeats 2.7 times across a few square centimetres, which
        # says nothing about what the chair as a whole holds. Weighted by the
        # area each material actually covers, the chair holds 73.
        if rigged or not source_surface:
            reference = max(source_densities.values())
            basis = "max"
        else:
            weighted = sum(source_densities[name] * source_surface.get(name, 0.0)
                           for name in source_densities)
            total_area = sum(source_surface.get(name, 0.0)
                             for name in source_densities)
            reference = weighted / total_area if total_area > 1e-9 else 0.0
            basis = "area-weighted mean"
        ceiling = reference * ATLAS_HEADROOM
        if surface_cm2 > 1e-9 and uv_total > 1e-9:
            candidate = resolution
            while candidate > 1024:
                density = candidate * candidate * uv_total / surface_cm2
                if density <= ceiling:
                    break
                # Do not magnify past the source -- but do not starve the sheet
                # either. Below the density the texture gate requires, a step
                # down stops being thrift and becomes a soft asset that fails
                # for the opposite reason. The chair's source holds 73
                # texels/cm2 and its own floor is 120, so there is no size that
                # satisfies both; 2048 misses the ceiling by 2x, and 1024
                # misses the floor by 3x. Miss the ceiling.
                if (candidate // 2) ** 2 * uv_total / surface_cm2 < min_density:
                    break
                candidate //= 2
            chosen = candidate
        report["atlas"] = {
            "requested": resolution, "chosen": chosen,
            "source_density_basis": basis,
            "source_density_reference": round(reference, 1),
            "source_density_max": round(max(source_densities.values()), 1),
            "min_density_floor": min_density,
            "density_at_chosen": round(
                chosen * chosen * uv_total / max(surface_cm2, 1e-9), 1),
        }
        if chosen != resolution:
            print("[RETOPO] atlas {0} -> {1}: the source holds {2:.0f} "
                  "texels/cm2 ({3}) and {0} would deliver {4:.0f}".format(
                      resolution, chosen, reference, basis,
                      resolution * resolution * uv_total / max(surface_cm2, 1e-9)))
    resolution = chosen

    # Everything from here to the bake is skinning, and a prop has none of it:
    # no groups to transfer, no influence cap to enforce, no armature to parent
    # to. Skipping it is the contract, not an optimisation -- a static prop
    # that acquires a skeleton on the way through has stopped being a prop.
    report["influences"] = None
    if rigged:
        # --- weights ------------------------------------------------------------
        for group in high.vertex_groups:
            if group.name not in low.vertex_groups:
                low.vertex_groups.new(name=group.name)
        bpy.ops.object.select_all(action="DESELECT")
        low.select_set(True)
        high.select_set(True)
        bpy.context.view_layer.objects.active = low
        transfer = low.modifiers.new("WeightTransfer", "DATA_TRANSFER")
        transfer.object = high
        transfer.use_vert_data = True
        transfer.data_types_verts = {"VGROUP_WEIGHTS"}
        transfer.vert_mapping = "POLYINTERP_NEAREST"
        bpy.ops.object.datalayout_transfer(modifier=transfer.name)
        bpy.ops.object.modifier_apply(modifier=transfer.name)

        # The modifier is the good transfer -- it interpolates across the source
        # polygon rather than snapping -- but it does not always land. On
        # fox-mascot it left the entire remeshed body unweighted while the shells
        # that were kept verbatim held the weights they were duplicated with. An
        # unweighted vertex is not a cosmetic problem: it stays behind at the
        # origin the moment the rig moves.
        #
        # So fill the gaps from the nearest original vertex. It is cruder than
        # interpolation and only ever applied where interpolation produced
        # nothing, and the count is reported rather than swallowed.
        gaps = [v for v in low.data.vertices
                if not any(g.weight > 0.0 for g in v.groups)]
        report["weights_filled_from_nearest"] = len(gaps)
        if gaps:
            source_tree = KDTree(len(high.data.vertices))
            for index, vert in enumerate(high.data.vertices):
                source_tree.insert(high.matrix_world @ vert.co, index)
            source_tree.balance()
            high_group_name = {g.index: g.name for g in high.vertex_groups}
            low_group = {g.name: g for g in low.vertex_groups}
            for vert in gaps:
                _, nearest, _ = source_tree.find(low.matrix_world @ vert.co)
                if nearest is None:
                    continue
                for entry in high.data.vertices[nearest].groups:
                    name = high_group_name.get(entry.group)
                    group = low_group.get(name)
                    if group is not None and entry.weight > 0.0:
                        group.add([vert.index], entry.weight, "REPLACE")
            remaining = sum(1 for v in low.data.vertices
                            if not any(g.weight > 0.0 for g in v.groups))
            print("[RETOPO] filled {0} unweighted vertices from the nearest "
                  "original vertex; {1} still unweighted".format(
                      len(gaps), remaining))

        # Interpolating weights from the original blends the influences of every
        # source vertex it samples, so a retopo vertex near a joint can end up
        # touched by seven bones where the original never exceeded four. UE5
        # imports at most `max_influences` and renormalises the rest away
        # silently -- which changes the deformation after it was tested. Cutting
        # to the cap here means what is tested is what ships.
        bpy.ops.object.select_all(action="DESELECT")
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        before = max((sum(1 for g in v.groups if g.weight > 0.0)
                      for v in low.data.vertices), default=0)
        bpy.ops.object.vertex_group_limit_total(limit=max_influences)
        bpy.ops.object.vertex_group_normalize_all(lock_active=False)
        after = max((sum(1 for g in v.groups if g.weight > 0.0)
                     for v in low.data.vertices), default=0)
        unweighted = sum(
            1 for v in low.data.vertices
            if not any(g.weight > 0.0 for g in v.groups))
        report["influences"] = {"before": before, "after": after,
                                "cap": max_influences, "unweighted_verts": unweighted}
        print("[RETOPO] influences: {0} -> {1} (cap {2}), {3} unweighted".format(
            before, after, max_influences, unweighted))
        if unweighted:
            report["ok"] = False
            report["failure"] = "{0} vertices carry no bone weight".format(unweighted)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print("[RETOPO] FAILED: {0}".format(report["failure"]))
            return 1

        armature_mod = low.modifiers.new("Armature", "ARMATURE")
        armature_mod.object = armature
        low.parent = armature

    # --- bake ---------------------------------------------------------------
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.bake.use_selected_to_active = True
    # How far the retopo actually sits from the accepted surface. Reported
    # because it is the number that says whether the likeness survived, and
    # measured as point-to-SURFACE distance: nearest-vertex distance mostly
    # reports how densely the original happens to be sampled, and produced
    # 18mm readings on meshes that had barely moved.
    step = max(1, len(low.data.vertices) // 4000)
    inverse = high.matrix_world.inverted()
    deviations = []
    for index in range(0, len(low.data.vertices), step):
        point = inverse @ (low.matrix_world @ low.data.vertices[index].co)
        found, location, _, _ = high.closest_point_on_mesh(point)
        if found:
            deviations.append((location - point).length)
    deviations = np.array(deviations or [0.0], dtype=np.float64)
    report["deviation"] = {
        "samples": int(len(deviations)),
        "p99_m": round(float(np.percentile(deviations, 99)), 5),
        "max_m": round(float(deviations.max()), 5),
    }
    print("[RETOPO] deviation from the original: p99 {0:.4f}m, max {1:.4f}m".format(
        float(np.percentile(deviations, 99)), float(deviations.max())))

    # Extrusion, not a cage object.
    #
    # A cage -- the low-poly pushed out along its own normals -- is the
    # textbook answer, and it was tried. It bakes field-scout-male entirely
    # black: fully-occluded AO and a black albedo, at every offset from 2mm to
    # 27mm, while the same mesh bakes correctly with a plain extrusion. Rather
    # than ship a black character for a technique that measured worse, the
    # extrusion stays and the cage is recorded as tried and rejected.
    scene.render.bake.use_cage = False
    scene.render.bake.cage_extrusion = cage
    scene.render.bake.max_ray_distance = ray_distance
    # Fill the gutter from the faces next door, not by smearing edge pixels
    # outward. EXTEND draws long radial streaks away from every island, which
    # on a normal map reads as fans of bogus surface detail -- clearly visible
    # as lines across the characters once they were lit in the engine.
    if hasattr(scene.render.bake, "margin_type"):
        scene.render.bake.margin_type = "ADJACENT_FACES"
    scene.render.bake.margin = 24

    # The source must emit its own albedo for a colour transfer; a Principled
    # BSDF would bake shading into it.
    #
    # Each material gets ITS OWN texture. A character can carry more than one
    # -- field-scout-female has a body atlas plus a separate face projection --
    # and feeding every slot the body atlas bakes the body's pixels onto the
    # face at the face's UVs, which comes out as noise where the head should be.
    # `sources` was loaded before the unwrap, because the region pass needs it
    # to find facial skin by colour on characters that do not author a face
    # material.
    if not sources and base_color_path and Path(base_color_path).exists():
        sources = {slot.material.name: base_color_path
                   for slot in high.material_slots if slot.material}
    report["bake_sources"] = sources

    # Not every material is textured. fox-mascot builds its eyes out of four
    # flat-coloured materials -- EyeOutline, EyeIris, EyePupil, EyeHighlight --
    # and so do the other characters; that is why the originals have crisp
    # cartoon eyes and no eye texture on disk. Handing those materials the body
    # atlas bakes fur onto the eyeballs, and leaving them alone bakes black,
    # because an EMIT pass through a Principled BSDF emits nothing.
    #
    # So each material is baked from whatever it actually uses: the mapped
    # texture, else its own image node, else its flat base colour.
    resolved = {}
    surface_channels = {}
    if original_uv:
        for slot in high.material_slots:
            mat = slot.material
            if mat is None:
                continue
            own, flat = None, (0.5, 0.5, 0.5, 1.0)
            roughness, metallic = 0.5, 0.0
            if mat.use_nodes:
                for node in mat.node_tree.nodes:
                    if node.type == "TEX_IMAGE" and node.image and node.image.filepath:
                        candidate = bpy.path.abspath(node.image.filepath)
                        if Path(candidate).exists():
                            own = candidate
                    elif node.type == "BSDF_PRINCIPLED":
                        flat = tuple(node.inputs["Base Color"].default_value)
                        if node.inputs.get("Roughness"):
                            roughness = float(node.inputs["Roughness"].default_value)
                        if node.inputs.get("Metallic"):
                            metallic = float(node.inputs["Metallic"].default_value)

            texture_path = sources.get(mat.name)
            if not texture_path or not Path(texture_path).exists():
                texture_path = own
            surface_channels[mat.name] = {
                "basecolor_texture": texture_path,
                "basecolor": flat,
                "roughness": max(0.0, min(1.0, roughness)),
                "metallic": max(0.0, min(1.0, metallic)),
            }
            if texture_path:
                resolved[mat.name] = "texture: " + Path(texture_path).name
            else:
                resolved[mat.name] = "flat colour: {0}".format(
                    tuple(round(c, 4) for c in flat[:3]))

    def configure_source_emission(channel):
        """Expose one authored channel as emission for selected-to-active bake."""
        key = channel.lower()
        for slot in high.material_slots:
            mat = slot.material
            if mat is None or mat.name not in surface_channels:
                continue
            spec = surface_channels[mat.name]
            mat.use_nodes = True
            tree = mat.node_tree
            tree.nodes.clear()
            out_node = tree.nodes.new("ShaderNodeOutputMaterial")
            emit = tree.nodes.new("ShaderNodeEmission")
            if channel == "BaseColor" and spec["basecolor_texture"]:
                tex = tree.nodes.new("ShaderNodeTexImage")
                tex.image = bpy.data.images.load(
                    spec["basecolor_texture"], check_existing=True)
                tex.image.colorspace_settings.name = "sRGB"
                uvmap = tree.nodes.new("ShaderNodeUVMap")
                uvmap.uv_map = original_uv
                tree.links.new(uvmap.outputs["UV"], tex.inputs["Vector"])
                tree.links.new(tex.outputs["Color"], emit.inputs["Color"])
            elif channel == "BaseColor":
                emit.inputs["Color"].default_value = spec["basecolor"]
            else:
                value = spec[key]
                emit.inputs["Color"].default_value = (value, value, value, 1.0)
            tree.links.new(emit.outputs["Emission"], out_node.inputs["Surface"])

    if resolved:
        configure_source_emission("BaseColor")
    report["bake_sources_resolved"] = resolved
    report["surface_constants"] = {
        name: {"roughness": round(spec["roughness"], 4),
               "metallic": round(spec["metallic"], 4)}
        for name, spec in sorted(surface_channels.items())
    }
    report["materials_without_source"] = []
    for name, how in sorted(resolved.items()):
        print("[RETOPO] bake source {0} <- {1}".format(name, how))

    # With a reduction there are two surfaces, so the dense one is baked onto
    # the light one and every material can carry its own bake target. Without
    # one there is a single surface, which bakes against itself: the emit
    # graphs already built are read through the OLD UVs and written through
    # the new ones, so the transfer still happens, just in place.
    if report.get("reduced", True):
        bake_material = bpy.data.materials.new("M_Retopo")
        bake_material.use_nodes = True
        low.data.materials.clear()
        low.data.materials.append(bake_material)
        bake_trees = [bake_material.node_tree]
    else:
        bake_trees = [slot.material.node_tree for slot in low.material_slots
                      if slot.material is not None]

    out_dir.mkdir(parents=True, exist_ok=True)
    baked, coverage, unbaked = {}, {}, {}
    passes = [("AO", "AO", (1.0, 1.0, 1.0, 1.0), True)]
    # A normal map is only worth baking where the two surfaces genuinely
    # differ. field-scout-male's retopo sits 0.7mm from his original at the
    # 99th percentile, so his map holds no recoverable detail -- just bake
    # noise and seam artifacts, which is exactly what showed up as lines
    # drawn across him in the engine.
    detail_mm = (report.get("deviation", {}).get("p99_m") or 0.0) * 1000.0
    worth_a_normal_map = detail_mm >= normal_min_mm
    report["normal_map_worth_baking"] = {
        "deviation_p99_mm": round(detail_mm, 2),
        "threshold_mm": normal_min_mm,
        "baked": bool(worth_a_normal_map and report.get("reduced", True)),
    }
    if report.get("reduced", True) and worth_a_normal_map:
        # A normal map needs a denser surface to capture. Without a reduction
        # there is none, and baking one produces a flat sheet that only costs
        # memory.
        passes.insert(0, ("Normal", "NORMAL", (0.5, 0.5, 1.0, 1.0), True))
    if kind == "static_prop" and surface_channels:
        # Props often mix metal, vinyl, rust and paper in one atlas. Preserve
        # the authored material constants per texel instead of inventing both
        # channels from albedo brightness at promotion time.
        passes.insert(0, ("Metallic", "EMIT", (0.0, 0.0, 0.0, 1.0), True))
        passes.insert(0, ("Roughness", "EMIT", (1.0, 1.0, 1.0, 1.0), True))
    if resolved:
        passes.insert(0, ("BaseColor", "EMIT", (0.0, 0.0, 0.0, 1.0), False))

    for name, bake_type, fill, non_color in passes:
        if name in {"BaseColor", "Roughness", "Metallic"}:
            configure_source_emission(name)
        image = bpy.data.images.new(
            "BK_" + name, resolution, resolution, alpha=True)
        image.generated_color = fill
        if non_color:
            image.colorspace_settings.name = "Non-Color"
        nodes = []
        for tree in bake_trees:
            node = tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            # Cycles bakes into the SELECTED, ACTIVE image node -- and in the
            # passthrough path a material has two image nodes, the source
            # texture and this target. Leaving the source selected lets the
            # bake write into the source instead, so the target keeps nothing
            # where that material's faces are and the margin floods the gap
            # with whatever neighbouring material did bake. On fox-mascot that
            # was his EyeHighlight yellow across most of the sheet, and the
            # albedo came out 3.35x too bright with a fifth of it clipped.
            for other in tree.nodes:
                other.select = False
            node.select = True
            tree.nodes.active = node
            nodes.append((tree, node))

        bpy.ops.object.select_all(action="DESELECT")
        scene.render.bake.use_selected_to_active = report.get("reduced", True)
        if report.get("reduced", True):
            high.select_set(True)
        low.select_set(True)
        bpy.context.view_layer.objects.active = low
        try:
            bpy.ops.object.bake(type=bake_type, use_clear=True, margin=24)
        except RuntimeError as error:
            print("[RETOPO] bake {0} failed: {1}".format(name, error))
            for tree, node in nodes:
                tree.nodes.remove(node)
            continue

        # A texel the rays never reached keeps the fill, and for BaseColor
        # the fill is black. Alpha says which texels were actually written,
        # so a bake that quietly missed is visible in the report instead of
        # shipping as a black head.
        pixels = np.array(image.pixels[:], dtype=np.float32).reshape(
            resolution, resolution, 4)
        hit = float((pixels[..., 3] > 0.5).mean())
        coverage[name] = round(100.0 * hit, 2)
        unbaked[name] = fill_unbaked(pixels)
        if name == "Normal":
            report["normal_texels_repaired"] = sanitise_normal_map(pixels)
            print("[RETOPO] normal map: {0} implausible texels flattened".format(
                report["normal_texels_repaired"]))
        image.pixels[:] = pixels.reshape(-1)

        path = out_dir / "T_{0}_{1}.png".format(src.stem.replace("-", ""), name)
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
        baked[name] = path.name
        for tree, node in nodes:
            tree.nodes.remove(node)
        print("[RETOPO] baked {0} -> {1}".format(name, path.name))

    report["baked"] = baked
    report["bake_coverage_pct"] = coverage
    report["texels_filled"] = unbaked
    print("[RETOPO] bake coverage: {0}".format(coverage))
    print("[RETOPO] unreached texels filled from neighbours: {0}".format(unbaked))
    has_basecolor = "BaseColor" in baked
    report["basecolor_status"] = (
        "baked_from_source"
        if has_basecolor
        else "pending_image_conditioned_texture_stage"
        if allow_missing_basecolor
        else "missing"
    )
    report["ok"] = "AO" in baked and (has_basecolor or allow_missing_basecolor)

    # --- export -------------------------------------------------------------
    bpy.data.objects.remove(high, do_unlink=True)
    bpy.ops.object.select_all(action="DESELECT")
    low.select_set(True)
    if armature is not None:
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature
    out_fbx = out_dir / (src.stem + "_retopo.fbx")
    bpy.ops.export_scene.fbx(
        filepath=str(out_fbx), use_selection=True, path_mode="RELATIVE",
        embed_textures=False, apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Y", axis_up="Z", apply_unit_scale=True,
        bake_anim=False, add_leaf_bones=False,
        object_types={"ARMATURE", "MESH"} if rigged else {"MESH"},
        mesh_smooth_type="FACE")
    report["output_fbx"] = out_fbx.name
    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / "retopo.blend"))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[RETOPO] {0}: {1} -> {2} tris ({3} quads), silhouette IoU {4:.3f}".format(
        src.stem, report["high_tris"], report["low_tris"], report["low_quads"], iou))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
