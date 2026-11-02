"""Pack the painter's OBJ and maps into one GLB (base colour, metallic-roughness, normal) for fixed-view renders."""
import bpy
import sys
import os
import glob
a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=src)
ob = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
d = os.path.dirname(src)
stem = os.path.splitext(os.path.basename(src))[0]
files = sorted(glob.glob(os.path.join(d, stem + "*.png")) + glob.glob(os.path.join(d, stem + "*.jpg")))
print("MAPS", [os.path.basename(f) for f in files])
m = bpy.data.materials.new("painted")
m.use_nodes = True
nt = m.node_tree
b = nt.nodes["Principled BSDF"]
def tex(path, non_color=False):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path)
    if non_color:
        t.image.colorspace_settings.name = 'Non-Color'
    return t
for f in files:
    n = os.path.basename(f).lower()
    if "metallic" in n or "rough" in n:
        t = tex(f, True)
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(t.outputs[0], sep.inputs[0])
        nt.links.new(sep.outputs[2], b.inputs["Metallic"])
        nt.links.new(sep.outputs[1], b.inputs["Roughness"])
    elif "normal" in n:
        t = tex(f, True)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(t.outputs[0], nm.inputs["Color"])
        nt.links.new(nm.outputs[0], b.inputs["Normal"])
    elif n.endswith((".png", ".jpg")) and n.startswith(stem.lower()):
        nt.links.new(tex(f).outputs[0], b.inputs["Base Color"])
ob.data.materials.clear()
ob.data.materials.append(m)
for p in ob.data.polygons:
    p.use_smooth = True
bpy.ops.export_scene.gltf(filepath=out, export_format='GLB')
print("GLB_OK")
