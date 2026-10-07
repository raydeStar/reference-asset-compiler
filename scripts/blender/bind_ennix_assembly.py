"""Transfer the tested proxy rig onto the editable assembly without losing faces.

Body weights transfer by nearest unchanged source vertex. Head/neck weights
blend over the existing neck, with eyes, teeth, scalp and groom following head.
Facial shape keys and original rest transforms are preserved.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
from mathutils.kdtree import KDTree


def main():
    p = argparse.ArgumentParser()
    p.add_argument("assembly")
    p.add_argument("proxy_rig")
    p.add_argument("out")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1:])
    out = Path(a.out).resolve()
    if out.exists():
        raise ValueError("Choose a new candidate directory; the previous fitting is evidence.")
    out.mkdir(parents=True)
    bpy.ops.wm.open_mainfile(filepath=str(Path(a.assembly).resolve()))
    with bpy.data.libraries.load(str(Path(a.proxy_rig).resolve()), link=False) as (src, dst):
        dst.objects = [name for name in src.objects if name in ("root", "Ennix_Skinning_Proxy")]
    for ob in dst.objects:
        bpy.context.scene.collection.objects.link(ob)
    rig = next(ob for ob in dst.objects if ob.type == "ARMATURE")
    proxy = next(ob for ob in dst.objects if ob.type == "MESH")
    bpy.context.view_layer.update()
    tree = KDTree(len(proxy.data.vertices))
    for v in proxy.data.vertices:
        tree.insert(proxy.matrix_world @ v.co, v.index)
    tree.balance()
    body = bpy.data.objects["Ennix_Outfit_And_Hands"]
    meshes = [ob for ob in bpy.context.scene.objects if ob.type == "MESH" and ob != proxy]
    diagnostics = {}
    for ob in meshes:
        world = ob.matrix_world.copy()
        if not ob.data.uv_layers:
            # The constant-colour scalp still gets a valid UV channel so the
            # export contract does not depend on a particular hair shader.
            uv = ob.data.uv_layers.new(name="UVMap")
            xs = [v.co.x for v in ob.data.vertices]
            ys = [v.co.y for v in ob.data.vertices]
            for loop in ob.data.loops:
                co = ob.data.vertices[loop.vertex_index].co
                uv.data[loop.index].uv = ((co.x - min(xs)) / max(max(xs) - min(xs), 1e-6),
                                        (co.y - min(ys)) / max(max(ys) - min(ys), 1e-6))
        ob.vertex_groups.clear()
        distances = []
        for bone in rig.data.bones:
            if bone.use_deform:
                ob.vertex_groups.new(name=bone.name)
        for v in ob.data.vertices:
            pos = world @ v.co
            if ob == body:
                _, index, distance = tree.find(pos)
                distances.append(distance)
                if distance > 1e-4 and not (pos.z > 1.46 and abs(pos.x) < 0.20 and distance < 0.02):
                    raise ValueError("Body differs from the proxy outside the recorded collar repair.")
                weights = {proxy.vertex_groups[g.group].name: g.weight
                           for g in proxy.data.vertices[index].groups if g.weight > 1e-5}
            elif ob.name == "Ennix_head":
                head = min(1.0, max(0.0, (pos.z - 1.515) / 0.080))
                head = head * head * (3 - 2 * head)
                weights = {"head": head, "neck_02": 1 - head}
            else:
                weights = {"head": 1.0}
            total = sum(weights.values())
            if total < 1e-8:
                raise ValueError(f"Unweighted vertex {ob.name}:{v.index}")
            for name, weight in weights.items():
                if weight > 1e-5:
                    ob.vertex_groups[name].add([v.index], weight / total, "REPLACE")
        mod = ob.modifiers.new("Ennix_Deformation", "ARMATURE")
        mod.object = rig
        # Skinning before subdivision keeps the same editable facial controls.
        bpy.context.view_layer.objects.active = ob
        while list(ob.modifiers).index(mod) > 0:
            bpy.ops.object.modifier_move_up(modifier=mod.name)
        ob.parent = rig
        ob.matrix_world = world
        diagnostics[ob.name] = {"vertices": len(ob.data.vertices),
                                "max_transfer_distance_m": max(distances, default=0),
                                "facial_controls": len(ob.data.shape_keys.key_blocks) - 1 if ob.data.shape_keys else 0}
    groom = bpy.data.objects.get("Ennix_groom")
    if groom:
        world = groom.matrix_world.copy()
        groom.parent = rig
        groom.parent_type = "BONE"
        groom.parent_bone = "head"
        bpy.context.view_layer.update()
        groom.matrix_world = world
    bpy.data.objects.remove(proxy, do_unlink=True)
    bpy.ops.file.pack_all()
    native = out / "Ennix_Rigged.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(native))
    bpy.ops.object.select_all(action="DESELECT")
    rig.select_set(True)
    for ob in meshes:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.export_scene.fbx(filepath=str(out / "Ennix_Body_Face.fbx"), use_selection=True,
                             object_types={"ARMATURE", "MESH"}, add_leaf_bones=False,
                             bake_anim=False, use_mesh_modifiers=False, path_mode="COPY", embed_textures=True)
    receipt = {"inputs": {name: {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
                          for name, path in (("assembly", a.assembly), ("proxy_rig", a.proxy_rig))},
               "meshes": diagnostics, "groom_parent": "head", "production_ready": False,
               "export_note": "FBX includes body, face morphs, eyes and oral meshes. Native strand groom is separate and is not in FBX."}
    (out / "bind-receipt.json").write_text(json.dumps(receipt, indent=2))
    print("The suit and its skeleton now travel together, sir; the hair has its own carriage.")


if __name__ == "__main__":
    main()
