"""A CPU build stays off the GPU: the stages that render with EEVEE switch to Cycles on the CPU (RAC_BLENDER)."""
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get("RAC_BLENDER")
pytestmark = pytest.mark.skipif(not BLENDER, reason="Set RAC_BLENDER for real Blender checks")

MAKE = r'''
import sys, bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.5))
bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 1])
'''


def ortho(tmp_path, device):
    make = tmp_path / "make.py"
    make.write_text(MAKE)
    blend = tmp_path / "cube.blend"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(make), "--", str(blend)], check=True,
                   capture_output=True, timeout=300)
    env = dict(os.environ)
    env.pop("RAC_RENDER_DEVICE", None)
    if device:
        env["RAC_RENDER_DEVICE"] = device
    out = tmp_path / f"ortho-{device or 'default'}"
    result = subprocess.run([BLENDER, "-b", "--factory-startup", str(blend), "--python-exit-code", "1", "--python",
                             str(ROOT / "scripts/blender/render_ortho_views.py"), "--", str(out), "64"],
                            capture_output=True, text=True, timeout=600, env=env)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout, out


def test_a_cpu_build_renders_the_ortho_views_with_cycles_on_the_cpu(tmp_path):
    log, out = ortho(tmp_path, "CPU")
    assert "RENDER ENGINE CYCLES CPU" in log
    assert all((out / f"{view}.png").is_file() for view in ("front", "left", "back", "top"))


RIG = r'''
import sys, bpy
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.5))
cube = bpy.context.object
arm = bpy.data.objects.new("root", bpy.data.armatures.new("root"))
bpy.context.scene.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
bone = arm.data.edit_bones.new("pelvis"); bone.head = (0, 0, 0); bone.tail = (0, 0, 1)
bpy.ops.object.mode_set(mode="OBJECT")
cube.parent = arm
cube.vertex_groups.new(name="pelvis").add(list(range(8)), 1.0, "REPLACE")
cube.modifiers.new("Armature", "ARMATURE").object = arm
bpy.ops.export_scene.fbx(filepath=sys.argv[sys.argv.index("--") + 1], add_leaf_bones=False)
'''


def test_a_cpu_build_runs_the_deform_test_with_cycles_on_the_cpu(tmp_path):
    # Cycles is an add-on engine, missing from Blender's static engine list: the stage must still find it.
    make = tmp_path / "rig.py"
    make.write_text(RIG)
    fbx = tmp_path / "rig.fbx"
    subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(make), "--", str(fbx)], check=True,
                   capture_output=True, timeout=300)
    env = dict(os.environ, RAC_RENDER_DEVICE="CPU")
    result = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(ROOT / "scripts/blender/deform_test.py"),
                             "--", str(fbx), str(tmp_path / "deform"), str(tmp_path / "deform.json"), "32"],
                            capture_output=True, text=True, timeout=600, env=env)
    assert "RENDER ENGINE CYCLES CPU" in result.stdout, result.stdout[-3000:] + result.stderr[-2000:]


def test_the_rebuild_hands_its_device_to_every_stage():
    source = (ROOT / "scripts/rebuild_character.py").read_text(encoding="utf-8")
    assert 'os.environ["RAC_RENDER_DEVICE"] = a.device' in source
    for script in ("render_ortho_views.py", "pose_ue5_anim_test.py", "deform_test.py"):
        assert "RAC_RENDER_DEVICE" in (ROOT / "scripts/blender" / script).read_text(encoding="utf-8"), script
