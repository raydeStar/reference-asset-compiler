"""Keep only the faces something outside the model could actually see.

A generated mesh carries geometry nobody will ever look at: interior shells
left where a decoder could not resolve two nearby surfaces, the inward faces of
a hollow body, fragments sealed inside. Measured on this library, that is
**47% of a raw decoded lantern** -- 280,000 of its 592,000 faces are invisible
from every direction. Every one of them costs triangles and texture space, and
competes for the budget a reduction is trying to spend on the silhouette.

Visibility asks a different question from every distance-based repair. Stand
outside, look from every direction, keep what you saw. That is:

- **topology-preserving** -- faces are deleted, never moved, so every crease
  stays exactly as sharp as it was and no UV shifts;
- **scale-free** -- no threshold, no voxel size, nothing to tune wrong;
- **incapable of fusing anything** -- it never asks whether two surfaces are
  near each other, so two coils that nearly touch cannot blend into one. That
  is the failure mode of merge-by-distance and of voxel remeshing, and this is
  immune to it by construction.

Seen is decided by whether a ray can escape. A ray leaves from just off the
surface, and if it travels four model widths without striking the mesh again,
that point was visible from somewhere. A face's centre is tried first; its
corners are tried only if the centre is hidden, because a face whose middle is
behind a strut but whose edge is not is still a face somebody can see, and
deleting it is the one mistake available here that cannot be undone.

Everything in the file occludes everything else, so a character's separate hair
and eyes shadow its body honestly rather than each being judged in isolation.

**Two honest limits.** An outward-facing flap floating just above the true
surface *is* seen, so it survives: this removes interior shells, enclosed
fragments and back-facing debris, a large share and not all of it. And a ray
cannot tell glass from brass, so on a model with anything transparent this
would delete exactly what you can see through the panes -- which is why such a
model is refused rather than quietly hollowed.

Usage:
  blender -b --factory-startup --python scripts/blender/cull_unseen_faces.py
      -- <mesh.glb> <culled.glb> <report.json>
      [--directions 64] [--most 0.6] [--largest-part 0.1] [--ignore-transparency]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

from visibility import (  # noqa: E402
    cull_verdict, directions_over_sphere, viewing_order, whole_part_verdict,
    whole_parts_removed)


# Where Blender's glTF importer parks what it made rather than what it read.
SCAFFOLDING = "glTF_not_exported"


def read_option(argv, name, default):
    if name not in argv:
        return default
    at = argv.index(name) + 1
    return argv[at] if at < len(argv) else default


def positional_arguments(argv):
    """Everything that is not an option and not an option's value."""
    taken, out = set(), []
    for index, item in enumerate(argv):
        if item.startswith("--"):
            taken.add(index + 1)
        elif index not in taken:
            out.append(item)
    return out


def see_through_materials(objects):
    """The materials a viewer can see past, which this cannot reason about.

    A ray stops at the first surface it meets whatever that surface is made of.
    On a glass lantern that makes the entire inside invisible, and culling it
    would empty the lantern through the very panes that make it worth looking
    at. Naming the materials is the whole remedy: it turns a silently gutted
    asset into a refusal somebody can read.
    """
    found = set()
    for item in objects:
        for slot in item.data.materials:
            if slot is None:
                continue
            for node in getattr(slot.node_tree, "nodes", ()) or ():
                if node.type != "BSDF_PRINCIPLED":
                    continue
                for label in ("Transmission Weight", "Transmission"):
                    socket = node.inputs.get(label)
                    if socket is not None and (socket.is_linked or socket.default_value > 0.0):
                        found.add(slot.name)
                alpha = node.inputs.get("Alpha")
                if alpha is not None and (alpha.is_linked or alpha.default_value < 1.0):
                    found.add(slot.name)
    return sorted(found)


def glb_document(path: Path):
    """The JSON a GLB carries, or None if this is not one."""
    data = path.read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        return None
    length = int.from_bytes(data[12:16], "little")
    return json.loads(data[20:20 + length].decode("utf-8"))


def bones_in_glb(path: Path) -> int:
    """How many joints the written file actually carries.

    Read back from the delivered bytes rather than from the scene, because the
    scene is not what anybody loads. A cull that quietly unrigs a character has
    done far more damage than the triangles it saved are worth.
    """
    document = glb_document(path)
    if document is None:
        return 0
    return sum(len(skin.get("joints", ())) for skin in document.get("skins", ()))


def vertex_attributes(path: Path) -> set[str]:
    """Which per-vertex attributes the source actually carries.

    Worth asking because the exporter will happily add ones it did not. A raw
    decoded lantern arrives with POSITION and nothing else, 295,768 vertices
    shared across 592,000 faces. Export it with normals and every vertex splits
    three ways -- 929,393 of them -- and a file that lost 47% of its faces
    comes back two and a half times larger. Deleting faces should not invent
    data, so whatever came in is what goes out.
    """
    document = glb_document(path)
    if document is None:
        return set()
    return {name
            for mesh in document.get("meshes", ())
            for primitive in mesh.get("primitives", ())
            for name in primitive.get("attributes", ())}


def weld(mesh) -> None:
    """Rejoin the vertices glTF split apart at every UV seam.

    Not cosmetic here. A mesh torn along every seam has cracks a ray can slip
    through, and a face beside one would report itself visible through a gap
    that is not in the model. Blender keeps a UV per face corner, so this costs
    nothing: the exporter splits them again on the way out.
    """
    work = bmesh.new()
    try:
        work.from_mesh(mesh)
        bmesh.ops.remove_doubles(work, verts=work.verts, dist=1e-6)
        work.normal_update()
        work.to_mesh(mesh)
    finally:
        work.free()
    mesh.update(calc_edges=True)


def face_neighbours(mesh):
    """For each face, the faces sharing an edge with it."""
    neighbours = [[] for _ in mesh.polygons]
    work = bmesh.new()
    try:
        work.from_mesh(mesh)
        work.faces.ensure_lookup_table()
        for face in work.faces:
            touching = neighbours[face.index]
            for edge in face.edges:
                for other in edge.link_faces:
                    if other.index != face.index:
                        touching.append(other.index)
    finally:
        work.free()
    return neighbours


def visible_faces(mesh, matrix, tree, rays, lift, reach, only=None):
    """Which of this mesh's faces a ray could reach from outside, and what it cost.

    `only` narrows the sweep to a set of faces worth asking about again, which
    is how the same function answers the second question: run it against a tree
    holding this mesh alone, and whatever escapes now was being hidden by
    something else in the file rather than by the model itself.
    """
    rotation = matrix.to_3x3()
    seen, casts = set(), 0
    for polygon in mesh.polygons:
        if only is not None and polygon.index not in only:
            continue
        normal = rotation @ polygon.normal
        if normal.length == 0.0:
            continue  # A degenerate face has no outside. It is not something to keep.
        normal = normal.normalized()
        ordered = [(Vector(ray), side) for ray, side in viewing_order(rays, tuple(normal))]
        centre = polygon.center
        # Corners are pulled a little toward the centre so a ray leaves from
        # this face rather than from the crease it shares with its neighbour.
        samples = [matrix @ centre] + [
            matrix @ mesh.vertices[index].co.lerp(centre, 0.08) for index in polygon.vertices]
        for point in samples:
            escaped = False
            for ray, side in ordered:
                casts += 1
                # Lifted off the face on the side this ray is leaving by, so it
                # never strikes the face it started from whichever way it goes.
                if tree.ray_cast(point + normal * (lift * side), ray, reach)[0] is None:
                    escaped = True
                    break
            if escaped:
                seen.add(polygon.index)
                break
    return seen, casts


def tree_over(objects):
    """One BVH across every object given, in world space."""
    points, triangles, offset = [], [], 0
    for item in objects:
        matrix = item.matrix_world
        points += [tuple(matrix @ vertex.co) for vertex in item.data.vertices]
        triangles += [tuple(index + offset for index in polygon.vertices)
                      for polygon in item.data.polygons]
        offset += len(item.data.vertices)
    return BVHTree.FromPolygons(points, triangles, all_triangles=False, epsilon=0.0), points


def trim(mesh, keep) -> None:
    """Delete every face nothing saw, leaving the rest exactly where it was."""
    work = bmesh.new()
    try:
        work.from_mesh(mesh)
        work.faces.ensure_lookup_table()
        bmesh.ops.delete(
            work, geom=[face for face in work.faces if face.index not in keep], context="FACES")
        work.to_mesh(mesh)
    finally:
        work.free()
    mesh.update(calc_edges=True)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    positional = positional_arguments(argv)
    if len(positional) < 3:
        print("[CULL] FAILED: expected <source> <output.glb> <report.json>")
        return 2
    source, output, report_path = (Path(positional[0]), Path(positional[1]), Path(positional[2]))
    ignore_transparency = "--ignore-transparency" in argv

    try:
        count = int(read_option(argv, "--directions", "64"))
        most = float(read_option(argv, "--most", "0.6"))
        largest = float(read_option(argv, "--largest-part", "0.1"))
        foreign = float(read_option(argv, "--shadowed-by-others", "0.1"))
    except ValueError:
        print("[CULL] FAILED: --directions takes a whole number; --most, --largest-part "
              "and --shadowed-by-others take fractions")
        return 1
    if not 8 <= count <= 512:
        print("[CULL] FAILED: directions runs from 8 to 512. Got {0}".format(count))
        return 1
    for value, flag in ((most, "--most"), (largest, "--largest-part"),
                        (foreign, "--shadowed-by-others")):
        if not 0.0 < value <= 1.0:
            print("[CULL] FAILED: {0} runs above 0 up to 1. Got {1}".format(flag, value))
            return 1
    if not source.is_file():
        print("[CULL] FAILED: source does not exist: {0}".format(source))
        return 1
    if output.exists():
        print("[CULL] FAILED: refusing to overwrite {0}".format(output))
        return 1

    suffix = source.suffix.lower()
    if suffix == ".blend":
        bpy.ops.wm.open_mainfile(filepath=str(source))
    elif suffix in (".glb", ".gltf"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(source))
    else:
        print("[CULL] FAILED: unsupported source format: {0}".format(suffix))
        return 1

    # The glTF importer builds its own scaffolding -- bone display shapes and
    # the like -- and parks it in a collection it will not export. It is not
    # part of the model, but it is geometry a ray stops at, and an 80-face
    # probe sphere left in the tree took a ninja's legs off while every number
    # in the report stayed correct. It is not the model, so it does not occlude.
    objects = [item for item in bpy.context.scene.objects
               if item.type == "MESH"
               and not any(group.name == SCAFFOLDING for group in item.users_collection)]
    if not objects:
        print("[CULL] FAILED: this file has no mesh to look at")
        return 1

    source_bones = bones_in_glb(source) if suffix in (".glb", ".gltf") else 0
    carried = vertex_attributes(source) if suffix in (".glb", ".gltf") else {"NORMAL"}
    see_through = see_through_materials(objects)
    if see_through and not ignore_transparency:
        print("[CULL] FAILED: this model has materials somebody can see past ({0}), and a ray "
              "cannot tell glass from brass. Culling it would delete the inside you look at "
              "through the panes. Pass --ignore-transparency only if nothing behind those "
              "surfaces is meant to be seen.".format(", ".join(see_through)))
        return 1

    transport_vertices = sum(len(item.data.vertices) for item in objects)
    for item in objects:
        weld(item.data)
    welded_vertices = sum(len(item.data.vertices) for item in objects)
    if not any(item.data.polygons for item in objects):
        print("[CULL] FAILED: this mesh has no faces to look at")
        return 1

    # One tree over everything in the file, so each piece occludes the others.
    # Judging a character's body without its hair in the way would keep every
    # face under it, which is the opposite of the point.
    tree, points = tree_over(objects)

    extent = max(max(p[axis] for p in points) - min(p[axis] for p in points) for axis in range(3))
    if extent <= 0.0:
        print("[CULL] FAILED: this mesh has no size")
        return 1
    # Far enough off the surface that a ray does not strike the face it left,
    # small enough that it cannot step past a neighbour standing right there.
    lift = extent * 1e-5
    reach = extent * 4.0
    rays = directions_over_sphere(count)

    total = casts = 0
    kept_faces = []
    sealed_parts = []
    blame = {}
    for item in objects:
        mesh = item.data
        seen, cost = visible_faces(mesh, item.matrix_world, tree, rays, lift, reach)
        casts += cost
        removed_here = {polygon.index for polygon in mesh.polygons} - seen
        if removed_here and len(objects) > 1:
            # Ask the same question again with the rest of the file taken away.
            # Anything that escapes now was never hidden by this model at all.
            alone, cost = visible_faces(
                mesh, item.matrix_world, tree_over([item])[0], rays, lift, reach,
                only=removed_here)
            casts += cost
            if alone:
                blame[item.name] = len(alone)
            removed_here -= alone
            seen |= alone
        if removed_here:
            sealed_parts += whole_parts_removed(face_neighbours(mesh), removed_here)
        kept_faces.append(seen)
        total += len(mesh.polygons)

    # A probe sphere, a sky dome, a placeholder nobody removed: 80 faces that
    # never render and that a ray stops at all the same. One of them sitting
    # around this ninja took his legs off, and every number in the report was
    # correct while it happened. So the blame gets named instead of absorbed.
    shadowed = sum(blame.values())
    if shadowed and shadowed / total > foreign:
        print("[CULL] FAILED: {0:,} faces ({1:.1%}) are hidden by other objects in this file "
              "rather than by the model itself: {2}. Something here is wrapped around or "
              "standing in front of the geometry being judged -- a probe sphere, a sky dome, "
              "a placeholder nobody removed. Take it out and run this again.".format(
                  shadowed, shadowed / total,
                  "; ".join("{0} loses {1:,} of them".format(name, count)
                            for name, count in sorted(blame.items(), key=lambda p: -p[1]))
                  + ". The file also holds: "
                  + ", ".join(item.name for item in objects if item.name not in blame)))
        return 1

    kept = sum(len(seen) for seen in kept_faces)
    sealed_parts.sort(reverse=True)
    refusal = (cull_verdict(total, kept, most)
               or whole_part_verdict(sealed_parts, total, largest))
    if refusal:
        print("[CULL] FAILED: " + refusal)
        return 1

    for item, seen in zip(objects, kept_faces):
        trim(item.data, seen)

    output.parent.mkdir(parents=True, exist_ok=True)
    # The whole scene, not a selection. Selecting the meshes alone leaves the
    # armature behind, and a character arrives with every bone gone -- which is
    # not a thing a stage that only deletes faces should be able to do.
    armatures = [item for item in bpy.context.scene.objects if item.type == "ARMATURE"]
    bpy.ops.export_scene.gltf(
        filepath=str(output), export_format="GLB", export_yup=True, export_apply=True,
        export_skins=bool(armatures),
        # Only what came in. A source carrying bare positions gets bare
        # positions back; adding normals to one splits every shared vertex and
        # undoes more than the cull saved.
        export_normals="NORMAL" in carried,
        export_tangents="TANGENT" in carried,
        export_animations=False, export_cameras=False, export_lights=False)
    if not output.is_file():
        print("[CULL] FAILED: the exporter wrote no file")
        return 1
    delivered_bones = bones_in_glb(output)
    if source_bones and delivered_bones != source_bones:
        print("[CULL] FAILED: this model arrived with {0} joints and would leave with {1}. "
              "Deleting faces must not touch the rig.".format(source_bones, delivered_bones))
        output.unlink()
        return 1

    removed = total - kept
    report = {
        "schema": "reference-asset-compiler.culled-faces.v1",
        "blender_version": bpy.app.version_string,
        "source": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "meshes": len(objects),
        # All three counts, because each answers a different question: how torn
        # the transport file was, how much of that was seams, and what the trim
        # left standing once the faces holding a vertex up were gone.
        "vertices": {"transport": transport_vertices, "welded": welded_vertices,
                     "after_cull": sum(len(item.data.vertices) for item in objects)},
        "faces": {"before": total, "kept": kept, "removed": removed,
                  "removed_share": round(removed / total, 5)},
        # Written down because fewer faces does not always mean fewer bytes,
        # and somebody should be able to see that rather than discover it.
        "bytes": {"before": source.stat().st_size, "after": output.stat().st_size},
        "vertex_attributes": sorted(carried),
        # Parts that went whole rather than being trimmed. Debris is meant to
        # look like this; so is an eyeball sealed inside a head, which is why
        # the sizes are written down instead of being taken on trust.
        "sealed_parts_removed": {
            "count": len(sealed_parts), "faces": sealed_parts[:20],
            "largest_share": round(sealed_parts[0] / total, 5) if sealed_parts else 0.0},
        "see_through_materials": see_through,
        # Faces that only looked hidden because something else in the file was
        # in the way. They are kept, and the count is written down, because a
        # stray helper object is a thing about the file rather than the model.
        "spared_shadowed_by_other_objects": blame,
        "joints": {"before": source_bones, "after": delivered_bones},
        "directions": count,
        "rays_cast": casts,
        "method": "a face is kept when a ray leaving just off it travels four model widths "
                  "without striking anything in the file again; its centre is tried first "
                  "and its corners only if the centre is hidden",
        "limit": "an outward-facing flap floating just above the true surface is seen, so it "
                 "survives, and a ray cannot see through glass. This removes interior shells, "
                 "enclosed fragments and back-facing debris: a large share, not all of it. It "
                 "is the first step of a cleanup.",
        "vertices_moved": 0,
        "requires_fixed_view_review": True,
        "production_grade": False,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("[CULL] {0:,} of {1:,} faces were never seen from outside and are gone ({2:.1%}); "
          "{3} sealed parts; {4:,} rays cast".format(
              removed, total, removed / total, len(sealed_parts), casts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
