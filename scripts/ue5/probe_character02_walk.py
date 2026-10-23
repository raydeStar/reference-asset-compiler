# SPDX-License-Identifier: MIT
"""CPU/null-RHI walk pose capture in an owned game process; saves no assets."""
import json
import os
from pathlib import Path
import time
import traceback

import unreal

assert '-game' in unreal.SystemLibrary.get_command_line().lower()
assert '-nullrhi' in unreal.SystemLibrary.get_command_line().lower()
OUT = Path(os.environ['RAC_WALK_PROOF'])
OUT.mkdir(parents=True, exist_ok=False)
STATE = {'pawn': None, 'time': 0., 'sample': 0., 'started': time.monotonic()}
REPORT = {'scope': 'CPU null-RHI owned game input and evaluated poses; not rendered gameplay or human acceptance.',
          'frames': [], 'error': None, 'engine': unreal.SystemLibrary.get_engine_version()}


def pack(t):
    p, q = t.translation, t.rotation
    return [p.x, p.y, p.z, q.x, q.y, q.z, q.w]


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(STATE['handle'])
    REPORT['error'] = error
    (OUT/'proof.json').write_text(json.dumps(REPORT, indent=2))
    unreal.log_warning('WALK_POSE_CAPTURE -- the knees were questioned without borrowing the GPU. ' + str(error or OUT))
    if STATE['pawn']:
        unreal.SystemLibrary.quit_game(STATE['pawn'], STATE['pawn'].get_controller(), unreal.QuitPreference.QUIT, False)


def tick(delta):
    try:
        if time.monotonic() - STATE['started'] > 60:
            raise TimeoutError('Owned CPU probe did not complete')
        if STATE['pawn'] is None:
            for pawn in unreal.ObjectIterator(unreal.TheAetherWarsCharacter):
                if pawn.is_player_controlled():
                    STATE['pawn'] = pawn
                    mesh = pawn.get_component_by_class(unreal.SkeletalMeshComponent)
                    mesh.set_editor_property('visibility_based_anim_tick_option', unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
                    mesh.set_editor_property('enable_update_rate_optimizations', False)
                    STATE['bones'] = [str(mesh.get_bone_name(i)) for i in range(mesh.get_num_bones())]
                    REPORT['mesh'] = mesh.get_skeletal_mesh_asset().get_path_name()
                    REPORT['anim_class'] = mesh.get_anim_instance().get_class().get_path_name()
                    break
            return
        pawn = STATE['pawn']
        STATE['time'] += float(delta)
        STATE['sample'] += float(delta)
        t = STATE['time']
        phase = 'settle' if t < 1.5 else 'walk' if t < 5.5 else 'stop'
        if phase == 'walk':
            pawn.add_movement_input(pawn.get_actor_forward_vector(), 89.18050216261764/500, True)
        if STATE['sample'] >= .025:
            STATE['sample'] = 0
            mesh = pawn.get_component_by_class(unreal.SkeletalMeshComponent)
            movement = pawn.get_component_by_class(unreal.CharacterMovementComponent)
            REPORT['frames'].append({'case': phase, 'time': t, 'speed_cm_s': pawn.get_velocity().length(),
                'falling': movement.is_falling(), 'mesh_world': pack(mesh.get_world_transform()),
                'bones': {n: pack(mesh.get_socket_transform(n, unreal.RelativeTransformSpace.RTS_COMPONENT)) for n in STATE['bones']}})
        if t > 7:
            if not any(f['case']=='walk' and f['speed_cm_s'] > 80 for f in REPORT['frames']):
                raise RuntimeError('Did not reach the requested walk speed')
            finish()
    except Exception:
        finish(traceback.format_exc())


STATE['handle'] = unreal.register_slate_post_tick_callback(tick)
