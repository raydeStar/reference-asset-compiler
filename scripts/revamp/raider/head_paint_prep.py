"""Reduce the accepted head candidate to a paintable mesh (QEM collapse), unwrap it into coherent islands and
export a glTF the Hunyuan3D-Paint 2.1 runner can lock to. The dense candidate is never modified."""
import bpy, sys, json, numpy as np
a = sys.argv[sys.argv.index("--") + 1:]; src, out, target = a[0], a[1], int(a[2])
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.gltf(filepath=src)
ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
bpy.context.view_layer.objects.active = ob; ob.select_set(True)
n0 = len(ob.data.polygons)
mod = ob.modifiers.new("reduce", 'DECIMATE'); mod.ratio = target / n0; mod.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier=mod.name)
ob.data.materials.clear()
for uvl in list(ob.data.uv_layers): ob.data.uv_layers.remove(uvl)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004, area_weight=0.0, scale_to_bounds=False)
bpy.ops.uv.pack_islands(margin=0.004, rotate=True)
bpy.ops.object.mode_set(mode='OBJECT')
for p in ob.data.polygons: p.use_smooth = True
# the painter reads UVs through a textured material; without one the loader drops them
m = bpy.data.materials.new("paint"); m.use_nodes = True; ob.data.materials.append(m)
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB', use_selection=True, export_materials='EXPORT',
                          export_normals=True, export_texcoords=True, export_yup=True)
rep = {"source": src, "source_faces": n0, "faces": len(ob.data.polygons), "verts": len(ob.data.vertices)}
json.dump(rep, open(out + ".json", "w"), indent=2); print("PREP", json.dumps(rep))
