# SPDX-License-Identifier: MIT
"""Actual combo and sole/collision evidence in an owned Unreal -game process.

RAC_CONTACT_OUTPUT and RAC_BOOT_PROBE are required. Never run in a user's PIE.
"""
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

import unreal

assert '-game' in unreal.SystemLibrary.get_command_line().lower()
OUT = Path(os.environ['RAC_CONTACT_OUTPUT'])
OUT.mkdir(parents=True, exist_ok=False)
BOOT_PATH = Path(os.environ['RAC_BOOT_PROBE'])
BOOT = json.loads(BOOT_PATH.read_text())
STATE = {'pawn': None, 'time': 0., 'sample': 0., 'attack': False, 'last_input': -1.,
         'started': time.monotonic(), 'seen_sections': set()}
PROOF = {'schema': 'rac.character02-runtime-contact.v1', 'frames': [], 'error': None,
         'boot_source_sha256': BOOT['source_sha256'],
         'probe_sha256': hashlib.sha256(BOOT_PATH.read_bytes()).hexdigest(),
         'engine': unreal.SystemLibrary.get_engine_version(),
         'scope': 'Owned editor -game, actual combat input, evaluated skinned sole samples and map collision; no cooked-build or human acceptance claim.'}
if os.environ.get('RAC_REFERENCE_POSES'):
    PROOF['reference_component'] = json.loads(Path(os.environ['RAC_REFERENCE_POSES']).read_text())['reference_component']
PROOF['fps'] = 30


def pack(t):
    p, q = t.translation, t.rotation
    return [p.x, p.y, p.z, q.x, q.y, q.z, q.w]


def trace(pawn, point):
    hit = unreal.SystemLibrary.line_trace_single(pawn, point + unreal.Vector(0, 0, 45),
        point - unreal.Vector(0, 0, 180), unreal.TraceTypeQuery.TRACE_TYPE_QUERY1,
        True, [pawn], unreal.DrawDebugTrace.NONE, True)
    if not hit or not hit.to_dict().get('blocking_hit'):
        return None
    d = hit.to_dict()
    p, n = d['impact_point'], d['impact_normal']
    component = d.get('hit_component') or d.get('component')
    return {'point': [p.x, p.y, p.z], 'normal': [n.x, n.y, n.z],
            'component': component.get_path_name() if component else None,
            'visible': component.is_visible() if component else None}


def soles(pawn, mesh, bones):
    result = {}
    for side, vertices in BOOT['sides'].items():
        points = []
        for vertex in vertices:
            point = unreal.Vector()
            for influence in vertex['influences']:
                point += bones[influence['bone']].transform_location(unreal.Vector(*influence['point_cm'])) * influence['weight']
            point = mesh.get_world_transform().transform_location(point)
            points.append((point.z, vertex['vertex'], point))
        _, index, point = min(points, key=lambda p: p[0])
        ground = trace(pawn, point)
        result[side] = {'vertex': index, 'sampled_vertices': len(points),
            'world_cm': [point.x, point.y, point.z], 'ground': ground,
            'gap_cm': point.z - ground['point'][2] if ground else None}
    return result


def finish(error=None):
    unreal.unregister_slate_post_tick_callback(STATE['handle'])
    PROOF['error'] = error
    PROOF['seen_sections'] = sorted(STATE['seen_sections'])
    (OUT / 'proof.json').write_text(json.dumps(PROOF, indent=2))
    unreal.log_warning('CONTACT_PROBE_DONE -- gravity has been summoned as a witness. ' + str(error or OUT))
    if STATE['pawn']:
        unreal.SystemLibrary.quit_game(STATE['pawn'], STATE['pawn'].get_controller(), unreal.QuitPreference.QUIT, False)


def tick(delta):
    try:
        if time.monotonic() - STATE['started'] > 70:
            raise TimeoutError('Owned combat probe exceeded its time budget')
        if STATE['pawn'] is None:
            for pawn in unreal.ObjectIterator(unreal.TheAetherWarsCharacter):
                if pawn.is_player_controlled():
                    STATE['pawn'] = pawn
                    mesh = pawn.get_component_by_class(unreal.SkeletalMeshComponent)
                    STATE['bones'] = [str(mesh.get_bone_name(i)) for i in range(mesh.get_num_bones())]
                    PROOF['mesh_asset'] = mesh.get_editor_property('skeletal_mesh_asset').get_path_name()
                    PROOF['sections'] = [str(n) for n in pawn.get_editor_property('combo_section_names')]
                    PROOF['montage'] = pawn.get_editor_property('combo_attack_montage').get_path_name()
                    pawn.get_controller().set_control_rotation(unreal.Rotator(pitch=-12, yaw=pawn.get_actor_rotation().yaw+155, roll=0))
                    break
            return
        pawn = STATE['pawn']
        STATE['time'] += float(delta)
        STATE['sample'] += float(delta)
        mesh = pawn.get_component_by_class(unreal.SkeletalMeshComponent)
        anim = mesh.get_anim_instance()
        montage = pawn.get_editor_property('combo_attack_montage')
        section = str(anim.montage_get_current_section(montage)) if anim.montage_is_playing(montage) else ''
        if section:
            STATE['seen_sections'].add(section)
        if STATE['time'] >= 2 and not STATE['attack']:
            pawn.do_combo_attack()
            STATE['attack'] = True
            STATE['last_input'] = STATE['time']
        elif STATE['attack'] and section in PROOF['sections'][:2] and STATE['time'] - STATE['last_input'] > .10:
            pawn.do_combo_attack()
            STATE['last_input'] = STATE['time']
        if STATE['sample'] >= 1/30:
            STATE['sample'] = 0
            bones = {n: mesh.get_socket_transform(n, unreal.RelativeTransformSpace.RTS_COMPONENT) for n in STATE['bones']}
            PROOF['frames'].append({'case': section or 'idle', 'frame': len(PROOF['frames']), 'time': STATE['time'],
                'delta_s': float(delta), 'montage_position': anim.montage_get_position(montage),
                'pawn': pack(pawn.get_actor_transform()), 'mesh_world': pack(mesh.get_world_transform()),
                'bones': {n: pack(t) for n, t in bones.items()}, 'soles': soles(pawn, mesh, bones)})
        if os.environ.get('RAC_CONTACT_CAPTURE') == '1':
            for at in [1.5, 2.3, 2.7, 3.1, 3.5, 3.9]:
                if STATE['time'] >= at and at not in STATE.setdefault('captures', []):
                    STATE['captures'].append(at)
                    unreal.SystemLibrary.execute_console_command(pawn, f'HighResShot 1024x768 filename="{(OUT / (str(at)+".png")).as_posix()}"')
        if os.environ.get('RAC_CONTACT_MOVIE') == '1' and STATE['time'] - STATE.get('last_capture', -1) >= 1/24:
            STATE['last_capture'] = STATE['time']
            captures = PROOF.setdefault('movie_frames', [])
            path = OUT / f'movie-{len(captures):05d}.png'
            captures.append({'time_s': STATE['time'], 'path': str(path), 'section': section})
            unreal.SystemLibrary.execute_console_command(pawn, f'HighResShot 640x480 filename="{path.as_posix()}"')
        if STATE['time'] > 7:
            if len(STATE['seen_sections']) < 3:
                raise RuntimeError('The actual input did not reach all three combo sections')
            finish()
    except Exception:
        finish(traceback.format_exc())


STATE['handle'] = unreal.register_slate_post_tick_callback(tick)
