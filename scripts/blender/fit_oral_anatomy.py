"""Replace oral fitting cages with CC0 teeth/tongue and close the neck overlap.

MHCLO barycentric correspondence is applied to the already conformed hm08
surface and every expression. The native groom and facial identity are retained.

--name prefixes the new materials. Where the mouth interior and the neck are
(--mouth-box, --neck) is the character's: rebuild_character.py passes them from
profiles/characters/<name>.json. Metres, conformed-head space.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Vector
from mathutils.kdtree import KDTree


def fitted_asset(path, head):
    metadata, matches, reading = {}, [], False
    for raw in path.read_text().splitlines():
        words = raw.split()
        if not words or words[0].startswith("#"):
            continue
        if words[0] == "verts":
            reading = True
            continue
        if reading and words[0].isdigit():
            if len(words) == 1:
                matches.append(([int(words[0])] * 3, [1, 0, 0], [0, 0, 0]))
            else:
                matches.append((list(map(int, words[:3])), list(map(float, words[3:6])), list(map(float, words[6:9]))))
        else:
            reading = False
            metadata[words[0]] = words[1:]
    v = head["verts"]
    scales = {}
    for axis, component in (("x", 0), ("y", 2), ("z", 1)):
        i, j, base = metadata[axis + "_scale"]
        scales[axis] = abs(v[int(i), component] - v[int(j), component]) / float(base)
    indices = np.array([m[0] for m in matches])
    weights = np.array([m[1] for m in matches])
    offsets = np.array([m[2] for m in matches])
    offset = np.c_[offsets[:, 0] * scales["x"], -offsets[:, 2] * scales["z"], offsets[:, 1] * scales["y"]]
    positions = np.einsum("nk,nkj->nj", weights, v[indices]) + offset
    faces, face_uv, uvs = [], [], []
    obj = path.parent / metadata["obj_file"][0]
    for line in obj.read_text().splitlines():
        words = line.split()
        if not words:
            continue
        if words[0] == "vt":
            uvs.append(list(map(float, words[1:3])))
        elif words[0] == "f":
            fields = [item.split("/") for item in words[1:]]
            faces.append([int(f[0]) - 1 for f in fields])
            face_uv.extend([uvs[int(f[1]) - 1] for f in fields])
    return positions, faces, np.array(face_uv), indices, weights, metadata


def extend_neck(ob, below_z, end_z):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.edges.index_update()
    edges = [e for e in bm.edges if e.is_boundary and all(v.co.z < below_z for v in e.verts)]
    # Only the lowest connected boundary is the neck. Mouth/eye boundaries
    # must never acquire a collar of their own, however fashionable that seems.
    todo, components = set(edges), []
    while todo:
        first = min(todo, key=lambda e: e.index)
        todo.remove(first)
        pending = [first]
        component = []
        while pending:
            edge = pending.pop()
            component.append(edge)
            for v in edge.verts:
                for neighbour in v.link_edges:
                    if neighbour in todo:
                        todo.remove(neighbour)
                        pending.append(neighbour)
        components.append(component)
    if not components:
        raise ValueError("Expected the open neck boundary")
    ring = sorted(min(components, key=lambda es: min(v.co.z for e in es for v in e.verts)), key=lambda e: e.index)
    old_verts = {v for e in ring for v in e.verts}
    if len(old_verts) < 10:
        raise ValueError("The detected neck boundary is too small")
    shapes = list(bm.verts.layers.shape.values())
    result = bmesh.ops.extrude_edge_only(bm, edges=ring)
    created = [x for x in result["geom"] if isinstance(x, bmesh.types.BMVert) and x not in old_verts]
    for v in created:
        end = Vector((v.co.x * 1.05, v.co.y, end_z))
        v.co = end
        for layer in shapes:
            v[layer] = end
    for f in bm.faces:
        f.smooth = True
    bm.normal_update()
    bm.to_mesh(ob.data)
    bm.free()
    return len(created)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("head_npz")
    p.add_argument("assets")
    p.add_argument("out")
    p.add_argument("--template", required=True, help="original template exposure identifies occluded mouth surfaces")
    p.add_argument("--name", default="Character", help="prefix for the new materials")
    p.add_argument("--mouth-box", type=float, nargs=4, required=True, metavar=("ABS_X", "MIN_Y", "MIN_Z", "MAX_Z"),
                   help="where occluded head faces become the mouth interior")
    p.add_argument("--neck", type=float, nargs=2, required=True, metavar=("BOUNDARY_BELOW_Z", "END_Z"),
                   help="the open neck boundary lies below BOUNDARY_BELOW_Z; extend it down to END_Z")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.source).resolve()))
    head = dict(np.load(a.head_npz))
    exposure = np.load(a.template)["exposure"]
    skin = bpy.data.objects["head"]
    tree = KDTree(len(head["verts"]))
    for i, co in enumerate(head["verts"]):
        tree.insert(Vector(co), i)
    tree.balance()
    ids = [tree.find(v.co)[1] for v in skin.data.vertices]
    cavity = bpy.data.materials.new(a.name + "_Mouth_Interior")
    cavity.use_nodes = True
    cavity.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.025, 0.004, 0.005, 1)
    cavity.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.75
    skin.data.materials.append(cavity)
    inside_faces = 0
    mouth_x, mouth_y, mouth_z0, mouth_z1 = a.mouth_box
    for poly in skin.data.polygons:
        centre = poly.center
        if abs(centre.x) < mouth_x and centre.y > mouth_y and mouth_z0 < centre.z < mouth_z1:
            if np.mean([exposure[ids[i]] for i in poly.vertices]) < 0.28:
                poly.material_index = len(skin.data.materials) - 1
                inside_faces += 1
    extension = extend_neck(bpy.data.objects["head"], *a.neck)
    for name in ("helper-upper-teeth", "helper-lower-teeth", "helper-tongue"):
        ob = bpy.data.objects.get(name)
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)
    assets = Path(a.assets).resolve()
    receipts = {}
    for name, folder, filename, texture in (("teeth", "teeth/teeth_base", "teeth_base", "teeth.png"),
                                            ("tongue", "tongue/tongue01", "tongue01", "tongue01_diffuse.png")):
        path = assets / folder / (filename + ".mhclo")
        verts, faces, uv, ids, weights, metadata = fitted_asset(path, head)
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts.tolist(), [], faces)
        mesh.update()
        mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", uv.ravel())
        for poly in mesh.polygons:
            poly.use_smooth = True
        ob = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(ob)
        ob.shape_key_add(name="Basis")
        for key, delta in head.items():
            if key.startswith("ex__"):
                sk = ob.shape_key_add(name=key[4:])
                sk.data.foreach_set("co", (verts + np.einsum("nk,nkj->nj", weights, delta[ids])).astype(np.float32).ravel())
        mat = bpy.data.materials.new(a.name + "_" + name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        image = mat.node_tree.nodes.new("ShaderNodeTexImage")
        image.image = bpy.data.images.load(str(assets / folder / texture))
        mat.node_tree.links.new(image.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.38
        mesh.materials.append(mat)
        sub = ob.modifiers.new("oral-smooth", "SUBSURF")
        sub.levels = sub.render_levels = 1
        receipts[name] = {"mhclo_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "vertices": len(verts), "faces": len(faces)}
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    out.with_suffix(".anatomy.json").write_text(json.dumps({"source_sha256": hashlib.sha256(Path(a.source).read_bytes()).hexdigest(),
        "neck_extension_vertices": extension, "mouth_interior_faces": inside_faces, "oral_assets": receipts,
        "license_source": "https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html",
        "asset_license": "CC0", "review_pending": True}, indent=2))
    print(f"The fitting cages are retired, sir; {a.name} has actual teeth now.")


if __name__ == "__main__":
    main()
