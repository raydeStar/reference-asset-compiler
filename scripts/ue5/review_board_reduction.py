"""Actual engine comparison: original board left, native reduced candidate right."""
import hashlib
import json
import os
from pathlib import Path
import time

import unreal


root = Path(os.environ["RAC_ROOT"])
out = root / "work/sunset-workshop/evidence/board-reduction-review-v001"
target = "/Game/SunsetWorkshop/L_BoardReview_v001"
if out.exists() or unreal.EditorAssetLibrary.does_asset_exist(target):
    raise RuntimeError("Keep previous review evidence")
out.mkdir(parents=True)
level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if not level.new_level_from_template(target,"/Game/SunsetWorkshop/L_WorkshopPreview_v003"):
    raise RuntimeError("Unable to create separate review map")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
paths = ["/Game/Compiled/SunsetCircuitBoardProduction/sunset-circuit-board-production",
         "/Game/SunsetWorkshop/Optimized/SM_BoardReduced_v001"]
records = []
for name,x,path in zip(("Original_Left","Reduced_Right"),(35,112),paths):
    mesh = unreal.load_asset(path)
    if mesh is None:
        raise RuntimeError("Missing board " + path)
    actor = actors.spawn_actor_from_object(mesh,unreal.Vector(x,-225,92.3),unreal.Rotator())
    actor.set_actor_label(name)
    actor.static_mesh_component.set_collision_profile_name("NoCollision")
    records.append({"label":name,"mesh":path,"lod0_vertices":unreal.EditorStaticMeshLibrary.get_number_verts(mesh,0)})
level.save_current_level()
editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
level.editor_set_game_view(True)
unreal.EditorPythonScripting.set_keep_python_script_alive(True)
views = [("comparison",(74,-330,185),(-39,90)),("grazing",(74,-350,120),(-12,90))]
state = {"index":0,"phase":"startup","time":time.monotonic(),"frames":[]}


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(handle)
    (out / "review.json").write_text(json.dumps({"level":target,"assets":records,
        "frames":state["frames"],"error":error,"production_ready":False},indent=2)+"\n")
    unreal.SystemLibrary.quit_editor()


def tick(delta):
    try:
        now = time.monotonic()
        name,xyz,rotation = views[state["index"]]
        frame = out / (name+".png")
        if state["phase"] == "startup" and now-state["time"] > 5:
            editor.set_level_viewport_camera_info(unreal.Vector(*xyz),unreal.Rotator(pitch=rotation[0],yaw=rotation[1],roll=0))
            state.update(phase="warm",time=now)
        elif state["phase"] == "warm" and now-state["time"] > 15:
            unreal.AutomationLibrary.take_high_res_screenshot(1600,900,str(frame))
            state.update(phase="capture",time=now)
        elif state["phase"] == "capture" and frame.is_file() and now-state["time"] > 3:
            state["frames"].append({"path":str(frame),"sha256":hashlib.sha256(frame.read_bytes()).hexdigest()})
            state["index"] += 1
            if state["index"] == len(views):
                finish()
            else:
                state.update(phase="startup",time=now-6)
        elif now-state["time"] > 90:
            finish("Timed out capturing board review")
    except Exception as error:
        finish(str(error))


handle = unreal.register_slate_post_tick_callback(tick)
