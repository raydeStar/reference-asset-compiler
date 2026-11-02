"""Speaking demo: drive the face shapes from Windows speech-synthesis visemes (SAPI's 22 mouth shapes with their
timings), add two blinks and a little head movement, and render the frames for a video with the voice track.

  $B -b <rigged.blend> --python speak_demo.py -- <visemes.json> <frames_dir> [fps]
The mouth shapes on the face, teeth and tongue are the MakeHuman expression shapes of the same names.
"""
import bpy, sys, os, json, math
from mathutils import Vector, Euler
a = sys.argv[sys.argv.index("--") + 1:]; vis_p, out = a[0], a[1]; FPS = int(a[2]) if len(a) > 2 else 24
os.makedirs(out, exist_ok=True)
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
data = json.load(open(vis_p, encoding="utf-8-sig")); V = data["visemes"]
end_t = max(v["t"] + v["d"] for v in V) + 0.4
# SAPI viseme -> mouth shape mix (MakeHuman expression units)
O, R, P, PR, FD, FE, C = "mouth-open", "mouth-retraction", "mouth-pursing", "mouth-protusion", "mouth-depression-retraction", "mouth-elevation", "mouth-compression"
MAP = {0: {}, 1: {O: .55}, 2: {O: .75}, 3: {O: .5, P: .3}, 4: {O: .4, R: .3}, 5: {O: .3, P: .3}, 6: {R: .8, O: .15}, 7: {P: .9, PR: .5},
       8: {O: .45, P: .5}, 9: {O: .6, P: .3}, 10: {O: .45, P: .4}, 11: {O: .65, R: .2}, 12: {O: .3}, 13: {P: .4, O: .2}, 14: {O: .35},
       15: {R: .6, O: .1}, 16: {P: .5, PR: .4, O: .15}, 17: {O: .25}, 18: {FD: .6, FE: .5}, 19: {O: .25, R: .2}, 20: {O: .35}, 21: {C: 1.0}}
SHAPES = sorted({k for m in MAP.values() for k in m})
targets = [o for o in sc.objects if o.type == 'MESH' and o.data.shape_keys and any(s in o.data.shape_keys.key_blocks for s in SHAPES)]
sc.render.fps = FPS; sc.frame_start = 1; sc.frame_end = int(end_t * FPS) + 1
for o in targets:
    kb = o.data.shape_keys.key_blocks
    for k in kb[1:]: k.value = 0.0
    for s in SHAPES + ["eye-left-closure", "eye-right-closure"]:
        if s not in kb: continue
        k = kb[s]; k.value = 0; k.keyframe_insert("value", frame=1)
    for v in V:
        f = 1 + v["t"] * FPS; ws = MAP.get(v["v"], {})
        for s in SHAPES:
            if s in kb: kb[s].value = ws.get(s, 0.0) * 0.9; kb[s].keyframe_insert("value", frame=f)
    for s in SHAPES:
        if s in kb: kb[s].value = 0; kb[s].keyframe_insert("value", frame=sc.frame_end)
    for bt in (0.15, 2.35):   # two blinks
        for s in ("eye-left-closure", "eye-right-closure"):
            if s not in kb: continue
            for df, val in ((0, 0), (2, 1), (4, 1), (7, 0)):
                kb[s].value = val; kb[s].keyframe_insert("value", frame=1 + bt * FPS + df)
# a little head movement: a nod on the first phrase, a slight turn later
pb = arm.pose.bones
for b in ("neck_01", "head"): pb[b].rotation_mode = 'XYZ'
for f, rot in ((1, (0, 0, 0)), (0.5 * FPS, (4, 0, 0)), (1.2 * FPS, (-2, 0, 1)), (2.2 * FPS, (1, 0, -3)), (end_t * FPS, (0, 0, 0))):
    pb["head"].rotation_euler = tuple(math.radians(x) for x in rot); pb["head"].keyframe_insert("rotation_euler", frame=max(1, f))
# render setup: head and shoulders, three-quarter
sc.render.engine = 'BLENDER_EEVEE'; sc.view_settings.view_transform = 'Standard'
w = sc.world or bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.33, 0.36, 1)
for nm, en, rot in (("key", 2.6, (55, 0, -35)), ("fill", 0.7, (65, 0, 60)), ("rim", 1.5, (110, 0, 170))):
    l = bpy.data.objects.new(nm, bpy.data.lights.new(nm, 'SUN')); l.data.energy = en; sc.collection.objects.link(l); l.rotation_euler = tuple(math.radians(x) for x in rot)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam; cam.data.lens = 85
head = arm.matrix_world @ arm.data.bones["head"].head_local + Vector((0, 0, 0.05))
d = Vector((0, -1, 0)); d.rotate(Euler((0, 0, math.radians(18)))); cam.location = head + d * 1.75 + Vector((0, 0, 0.03))
cam.rotation_euler = (head - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.render.resolution_x, sc.render.resolution_y = 960, 960
sc.render.image_settings.file_format = 'PNG'; sc.render.filepath = os.path.join(out, "f_")
bpy.ops.render.render(animation=True)
json.dump({"fps": FPS, "frames": sc.frame_end, "duration_s": end_t, "visemes": len(V), "shapes": SHAPES, "driven_meshes": [o.name for o in targets]},
          open(os.path.join(out, "speak.json"), "w"), indent=2)
print("SPEAK_OK", sc.frame_end, "frames", [o.name for o in targets])
