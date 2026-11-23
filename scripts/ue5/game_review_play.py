"""Game review steps 7-8: put the review character on the player pawn for this session only, to play or to shoot.

Launched by run_game_review.ps1:
  set RAC_GAME_REVIEW_JOB=<attempt>\\job.json   RAC_GAME_REVIEW_MODE=play|closeups
  UnrealEditor.exe <project> <level> -game -windowed ... -ExecCmds="py <this file>"
The saved Blueprint, level and default character are never modified.

play      Swap and stay (RAC_GAME_REVIEW_LOOK picks a look's materials): WASD, mouse camera, hold the walk key (Left Alt) to walk, Shift to sprint. Writes
          06-unreal/ready.json (or runtime-error.json) and two shots (standing, face). She says the game's lip-sync
          demo line at the face close-up, and again whenever L is pressed.
closeups  Swap, freeze Manny's idle at 1 s, and shoot in the level's own light: the face (front, three-quarter,
          low) once per look, then the body from the front, three-quarter, side and back. Writes
          07-closeups/<look>_face_<view>.png, body_<view>.png and done.json, then quits. -Face adds the face pass:
          the game's own face component held in each expression and each lip-sync mouth shape (face_<key>_<view>.png).

Both modes put the recipe's lip-sync gains (face.mouth_morph_gain) on the player's face component, and its reach
numbers (unreal.climb_reach) on the player's climbing component, so her hands meet walls and ledges.

RAC_GAME_REVIEW_BASELINE=1 (closeups, -Baseline): no swap. The game's own hero is shot through the same animations
(the sources of the mapping) at the same frames into 07-closeups/baseline/, for a side-by-side with the character.

The character's own tick rewrites the camera boom and FOV every frame (TheAetherWarsCharacter.cpp), so closeups pause
the actor tick and drive the boom themselves. Python here cannot spawn actors or add components.
"""
import datetime
import json
import os
import time
import traceback
from pathlib import Path

import unreal

JOB = json.loads(Path(os.environ['RAC_GAME_REVIEW_JOB']).read_text(encoding='utf-8'))
MODE = os.environ.get('RAC_GAME_REVIEW_MODE', 'play')
UE = JOB['unreal']
OUT = Path(JOB['paths']['unreal'])
BASELINE = os.environ.get('RAC_GAME_REVIEW_BASELINE') == '1'
SHOTS = Path(JOB['paths']['closeups']) / ('baseline' if BASELINE else '')
IMPORT = json.loads((OUT / 'import.json').read_text(encoding='utf-8'))
MESH = UE['mesh']
ABP = IMPORT['anim_blueprints'][0]
ABP_CLASS = f"{ABP}.{ABP.rsplit('/', 1)[-1]}_C"
IDLE = IMPORT['idle_clip']
PAWN_CLASS = getattr(unreal, UE['pawn_class'])
LOOKS = ['default'] + list(JOB['looks'])
STATE = {'started': time.monotonic(), 'pawn': None, 'ready': False, 'walking': None}
WALK_KEY = unreal.Key()
assert WALK_KEY.import_text(UE['walk_key'])
STEP_S = 2.0
# -Poses: frozen Manny clips for judging the body rig, (label, clip or None for the bind pose, seconds)
POSES = [('bind', None, 0), ('idle', 'MM_Idle', 1.0), ('walk', 'MF_Unarmed_Walk_Fwd', 0.3),
         ('jog', 'MF_Unarmed_Jog_Fwd', 0.25), ('attack', 'MM_Attack_01', 0.35), ('jump', 'MM_Jump', 0.3)] \
    if os.environ.get('RAC_GAME_REVIEW_POSES') == '1' else []
# -Motion: every animation the player uses, each sampled through its length from two sides
MOTION = os.environ.get('RAC_GAME_REVIEW_MOTION') == '1' or BASELINE
MOTION_FRACTIONS = (0.15, 0.4, 0.65, 0.9)
MOTION_VIEWS = (('three_quarter', 45), ('side', 90))
MOTION_STEP_S = 1.2
# -Face: the game's face component held in each expression, then in each mouth shape, from the front and three-quarter
FACE_PASS = os.environ.get('RAC_GAME_REVIEW_FACE') == '1'
FACE_PASS_VIEWS = [v for v in JOB['face_views'] if v[0] in ('front', 'three_quarter')]
EXPRESSIONS = {'idle': 'idle_expression', 'combat': 'combat_expression', 'hurt': 'hurt_expression',
               'climb': 'climb_expression', 'hang': 'hang_expression', 'glide': 'glide_expression'}
SPEAK_KEY = unreal.Key()
assert SPEAK_KEY.import_text('L')
SPEAK_LINE = 'VL_LipSyncDemo'


def motion_clips():
    """(label, sequence path, length s, owner slots) for each player animation; montages split into their segments.
    A montage with an empty segment is listed as 'EMPTY' (the copied montage would play nothing)."""
    by_path, empty = {}, []
    slots = {source: f'{c or "character"}.{p}' for c, p, source in IMPORT['player_anim_slots']}
    for source, copy in sorted(IMPORT['mapping'].items()):
        if BASELINE:      # the game hero's own clips
            copy = source
        asset = unreal.load_asset(copy)
        if asset is None:
            empty.append(f'{slots.get(source, source)}: missing {copy}')
            continue
        sequences = [asset]
        if isinstance(asset, unreal.AnimMontage):
            sequences = []
            for track in asset.get_editor_property('slot_anim_tracks'):
                for segment in track.get_editor_property('anim_track').get_editor_property('anim_segments'):
                    ref = segment.get_editor_property('anim_reference')
                    if ref:
                        sequences.append(ref)
                    else:
                        empty.append(f'{slots.get(source, source)}: {copy} has an EMPTY segment')
        for seq in sequences:
            entry = by_path.setdefault(seq.get_path_name(), [seq.get_name(), seq.get_path_name(),
                                                             float(seq.get_play_length()), []])
            entry[3].append(slots.get(source, source))
    return list(by_path.values()), empty


def _weights(table):
    return {str(k): round(float(v), 4) for k, v in table.items()}


def _name_map(weights):
    out = unreal.Map(unreal.Name, float)
    for k, v in weights.items():
        out[unreal.Name(k)] = float(v)
    return out


def _letter(shape):
    return str(getattr(shape, 'name', shape)).split('.')[-1].strip('<>: 0123456789')


def configure_face(pawn, quiet):
    """The recipe's lip-sync gains on the player's face component, and a report of what it will drive.

    The component drives morphs by name and skips any the mesh lacks, so every name it (or the recipe) uses is checked
    against the mesh. quiet (closeups): no random blinks or eye flutter, so a shot never catches a lid half shut."""
    face = pawn.get_component_by_class(unreal.AetherFaceComponent) if hasattr(unreal, 'AetherFaceComponent') else None
    if face is None:
        return {'face_component': False}
    face.set_editor_property('mouth_morph_gain', _name_map(JOB['face']['mouth_morph_gain']))
    morphs = {str(m.get_name()) for m in unreal.load_asset(MESH).get_editor_property('morph_targets')}
    tables = {state: _weights(face.get_editor_property(prop)) for state, prop in EXPRESSIONS.items()}
    visemes = {_letter(shape): _weights(mouth.get_editor_property('morphs'))
               for shape, mouth in face.get_editor_property('viseme_morphs').items()}
    blink = [str(face.get_editor_property('blink_left_morph')), str(face.get_editor_property('blink_right_morph'))]
    named = set(JOB['face']['mouth_morph_gain']) | set(blink)
    for table in list(tables.values()) + list(visemes.values()):
        named |= set(table)
    STATE['face'] = {'component': face, 'tables': tables, 'visemes': visemes, 'blink': blink,
                     'gain': dict(JOB['face']['mouth_morph_gain']),
                     'intensity': float(face.get_editor_property('lip_sync_intensity')),
                     'blink_weight': float(face.get_editor_property('blink_weight')),
                     'hold': float(face.get_editor_property('blink_hold_time'))}
    if quiet:
        for prop, value in (('blink_interval_min', 1000.0), ('blink_interval_max', 1000.0),
                            ('double_blink_chance', 0.0), ('eye_micro_movement_intensity', 0.0)):
            face.set_editor_property(prop, value)
        face.blink()      # a blink now, so the next is scheduled 1000 s out
    return {'face_component': True, 'mouth_morph_gain': STATE['face']['gain'],
            'unknown_morphs': sorted(n for n in named if n not in morphs), 'morphs_on_mesh': len(morphs)}


def face_targets(part, state):
    """The morph weights the face component settles on for a face-pass state (its own tables and gains)."""
    f = STATE['face']
    idle = f['tables']['idle']
    if part == 'expr' and state == 'rest':
        return {}
    if part == 'expr' and state in f['tables']:
        return f['tables'][state]
    if part == 'expr' and state == 'blink':
        return {**idle, **{m: min(1.0, idle.get(m, 0.0) + f['blink_weight']) for m in f['blink']}}
    mouth = {m: 0.0 for table in f['visemes'].values() for m in table}
    for m, w in f['visemes'].get(state, {}).items():
        mouth[m] += w * f['gain'].get(m, 1.0) * f['intensity']
    return {**idle, **{m: round(w, 4) for m, w in mouth.items()}}


def hold_face(part, state):
    """Hold the face component in a state: an expression through its idle slot (the slot it plays at rest), the lids
    shut by a blink held open-endedly, or a mouth shape by a one-cue line that lasts a minute (over the idle face)."""
    f = STATE['face']
    face = f['component']
    if face.is_speaking():
        face.stop_speaking()
    face.set_editor_property('blink_hold_time', f['hold'])      # ends a held blink
    if part == 'expr' and state == 'rest':
        table = {}
    elif part == 'expr' and state in f['tables']:
        table = f['tables'][state]
    else:
        table = f['tables']['idle']
    face.set_editor_property('idle_expression', _name_map(table))
    if part == 'expr' and state == 'blink':
        face.set_editor_property('blink_hold_time', 60.0)
        face.blink()
    if part == 'viseme':
        key = unreal.AetherVisemeKey()
        key.set_editor_property('time', 0.0)
        key.set_editor_property('shape', getattr(unreal.AetherViseme, state))
        track = unreal.AetherVisemeTrack()
        track.set_editor_property('keys', [key])
        track.set_editor_property('duration', 60.0)
        face.speak(None, track)


def console(pawn, command):
    unreal.SystemLibrary.execute_console_command(pawn.get_world(), command)


def swap(pawn):
    body = pawn.get_editor_property('mesh')
    mesh = unreal.load_asset(MESH)
    assert mesh, MESH
    abp = unreal.load_class(None, ABP_CLASS)
    assert abp, ABP_CLASS
    hidden = []
    for child in body.get_children_components(True):
        if isinstance(child, unreal.PrimitiveComponent) and child.is_visible():
            child.set_visibility(False, True)
            hidden.append(f'{child.get_name()} ({child.get_class().get_name()})')
    body.set_skeletal_mesh_asset(mesh)
    for i, slot in enumerate(mesh.materials):
        body.set_material(i, slot.material_interface)
    body.set_anim_instance_class(abp)
    look = os.environ.get('RAC_GAME_REVIEW_LOOK', 'default') if MODE == 'play' else 'default'
    chosen = IMPORT.get('material_sets', {}).get(look, {})
    slots = [str(s.material_slot_name) for s in mesh.materials]
    for i, name in enumerate(slots):      # play with a named look: its materials on the slots it changes
        if name in chosen:
            body.set_material(i, unreal.load_asset(chosen[name]))
    swapped, missing = {}, {}
    for cls_name, prop, source in IMPORT['player_anim_slots']:
        owner = pawn if cls_name is None else pawn.get_component_by_class(getattr(unreal, cls_name))
        target = IMPORT['mapping'].get(source)
        anim = unreal.load_asset(target) if target else None
        if owner and anim:
            owner.set_editor_property(prop, anim)
            swapped[f'{cls_name or "character"}.{prop}'] = target
        else:
            missing[f'{cls_name or "character"}.{prop}'] = source
    glider = fit_glider(pawn)
    return {'hidden_attachments': hidden, 'animations_swapped': swapped, 'animations_missing': missing, 'look': look,
            'glider': glider, 'climb_reach': fit_climb_reach(pawn),
            'face': configure_face(pawn, quiet=MODE == 'closeups')}


def fit_glider(pawn):
    """The import's glider grip moved the Sailwing for this character's hands (unreal.glider_grip): hang it there for
    this session only. Without it the glider stays where the hero's hands are."""
    offset = (IMPORT.get('glider_grip') or {}).get('flight_offset')
    cls = getattr(unreal, 'AetherGliderComponent', None)
    glider = pawn.get_component_by_class(cls) if cls and offset else None
    if not glider:
        return None
    glider.set_editor_property('flight_offset', unreal.Transform(
        unreal.Vector(*offset[:3]), unreal.Quat(*offset[3:]).rotator(), unreal.Vector(1, 1, 1)))
    glider.build_visuals()
    return {'flight_offset': offset}


def fit_climb_reach(pawn):
    """The recipe's reach numbers (unreal.climb_reach) on the player's climbing component, for this session only.

    The component holds the body where the hero's hands meet a wall or a ledge's lip; a character with shorter arms and
    torso plays the same clips with her fists on the bare wall under the lip. Each setting is read back from the
    component, so ready.json shows the hero's number and the one in force. Without the key nothing is touched."""
    reach = UE.get('climb_reach')
    if not reach:
        return None
    cls = getattr(unreal, 'ClimbingComponent', None)
    climb = pawn.get_component_by_class(cls) if cls else None
    if not climb:
        return {'applied': False, 'why': 'the player has no ClimbingComponent', 'asked': reach}
    settings = {}
    for prop, value in reach.items():
        hero = float(climb.get_editor_property(prop))
        climb.set_editor_property(prop, float(value))
        settings[prop] = {'hero': round(hero, 2), 'now': round(float(climb.get_editor_property(prop)), 2)}
    return {'applied': True, 'settings': settings}


def freeze_idle(body):
    body.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    body.set_animation(unreal.load_asset(IDLE))
    body.play(False)
    body.set_position(1.0, False)
    body.set_play_rate(0.0)


def apply_look(body, look):
    chosen = IMPORT.get('material_sets', {}).get(look, {}) if look != 'default' else {}
    for k, name in enumerate(STATE['slot_names']):
        body.set_material(k, unreal.load_asset(chosen[name]) if name in chosen else STATE['default_mats'][k])


def closeup_steps():
    if BASELINE:
        return [('motion', 'default', (clip, fraction, view)) for clip in STATE['motion_clips']
                for view in MOTION_VIEWS for fraction in MOTION_FRACTIONS]
    steps = [('face', look, view) for look in LOOKS for view in JOB['face_views']]
    steps += [('body', 'default', view) for view in JOB['body_views']]
    if FACE_PASS and 'face' in STATE:
        steps += [('expr', 'default', (state, view)) for state in JOB['face_states'] for view in FACE_PASS_VIEWS]
        steps += [('viseme', 'default', (shape, view)) for shape in JOB['visemes'] for view in FACE_PASS_VIEWS]
    if POSES:
        steps += [('pose', 'default', (pose, view)) for pose in POSES for view in JOB['body_views']]
        # the hands up close, relaxed and in the attack's fist: finger joints are judged here, not in the body shots
        steps += [('hand', 'default', (pose, side)) for pose in POSES if pose[0] in ('idle', 'attack')
                  for side in ('l', 'r')]
    if MOTION:
        steps += [('motion', 'default', (clip, fraction, view)) for clip in STATE['motion_clips']
                  for view in MOTION_VIEWS for fraction in MOTION_FRACTIONS]
    return steps


def step_at(steps, t):
    """The step index at time t (motion shots are shorter than the rest), and the time into that step."""
    start = 0.0
    for i, step in enumerate(steps):
        length = MOTION_STEP_S if step[0] == 'motion' else STEP_S
        if t < start + length:
            return i, t - start, length
        start += length
    return len(steps), 0.0, STEP_S


def hold_pose(body, pose):
    """A Manny clip frozen at a time, or the bind pose (no animation)."""
    label, clip, when = pose
    body.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    anim = unreal.load_asset(IMPORT['idle_clip'].rsplit('_MM_Idle', 1)[0] + '_' + clip) if clip else None
    body.set_animation(anim)
    if anim:
        body.play(False)
        body.set_position(when, False)
        body.set_play_rate(0.0)


def shot_label(part, look, view):
    if part == 'face':
        return f'{look}_face_{view[0]}'
    if part == 'pose':
        return f'pose_{view[0][0]}_{view[1][0]}'
    if part == 'hand':
        return f'hand_{view[0][0]}_{view[1]}'
    if part == 'motion':
        clip, fraction, side = view
        return f'motion_{clip[0]}_{side[0]}_{int(round(fraction * 100)):02d}'
    if part in ('expr', 'viseme'):
        return f'face_{"" if part == "expr" else "viseme_"}{view[0]}_{view[1][0]}'
    return f'body_{view[0]}'


def closeups(pawn, t):
    body = pawn.get_editor_property('mesh')
    boom = pawn.get_component_by_class(unreal.SpringArmComponent)
    cam = pawn.get_component_by_class(unreal.CameraComponent)
    if 'setup' not in STATE:
        STATE['setup'] = True
        STATE['yaw'] = pawn.get_actor_rotation().yaw
        STATE['default_mats'] = list(body.get_materials())
        mesh = body.get_editor_property('skeletal_mesh_asset') if BASELINE else unreal.load_asset(MESH)
        STATE['slot_names'] = [str(s.material_slot_name) for s in mesh.materials]
        STATE['blinks'] = [str(m.get_name()) for m in mesh.get_editor_property('morph_targets')
                           if 'closure' in str(m.get_name()).lower() or 'blink' in str(m.get_name()).lower()]
        pawn.get_movement_component().disable_movement()
        pawn.set_actor_tick_enabled(False)
        if not BASELINE:      # the baseline's motion steps set the hero's own clips
            freeze_idle(body)
        SHOTS.mkdir(parents=True, exist_ok=True)
        for old in SHOTS.glob('*.png'):
            old.unlink()
        STATE['motion_clips'], STATE['motion_empty'] = motion_clips() if MOTION else ([], [])
    if 'face' not in STATE:      # no face component to quiet: hold the lids open from here
        for morph in STATE['blinks']:
            body.set_morph_target(morph, 0.0, False)
    boom.set_editor_property('socket_offset', unreal.Vector(0, 0, 0))
    boom.set_editor_property('do_collision_test', False)
    boom.set_editor_property('enable_camera_lag', False)
    boom.set_editor_property('enable_camera_rotation_lag', False)
    steps = closeup_steps()
    i, into, length = step_at(steps, t)
    if i >= len(steps):
        if 'done' not in STATE:
            STATE['done'] = True
            shots = [shot_label(part, look, v) for part, look, v in steps]
            motion = [{'clip': c[0], 'path': c[1], 'length_s': round(c[2], 3), 'used_by': c[3]}
                      for c in STATE['motion_clips']]
            face = None
            if FACE_PASS and 'face' in STATE:
                face = {'states': JOB['face_states'], 'visemes': JOB['visemes'], 'views': [v[0] for v in FACE_PASS_VIEWS],
                        'targets': {('' if part == 'expr' else 'viseme_') + state: face_targets(part, state)
                                    for part, states in (('expr', JOB['face_states']), ('viseme', JOB['visemes']))
                                    for state in states},
                        **STATE['swap']['face']}
            (SHOTS / 'done.json').write_text(json.dumps({'shots': shots, 'looks': LOOKS, 'poses': [p[0] for p in POSES],
                                                         'motion': motion, 'motion_problems': STATE['motion_empty'],
                                                         'motion_fractions': list(MOTION_FRACTIONS),
                                                         'motion_views': [v[0] for v in MOTION_VIEWS],
                                                         'face_pass': face}, indent=1))
            console(pawn, 'quit')
        return
    part, look, view = steps[i]
    if STATE.get('look') != look and not BASELINE:
        STATE['look'] = look
        apply_look(body, look)
    label = shot_label(part, look, view)
    if part in ('pose', 'hand'):
        pose, view = view
        if STATE.get('pose') != pose[0]:
            STATE['pose'] = pose[0]
            hold_pose(body, pose)
    if part in ('expr', 'viseme'):
        state, view = view
        if STATE.get('face_state') != (part, state):
            STATE['face_state'] = (part, state)
            hold_face(part, state)
    if part == 'motion':
        clip, fraction, view = view
        key = (clip[1], fraction)
        if STATE.get('motion_pose') != key:
            STATE['motion_pose'] = key
            body.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            body.set_animation(unreal.load_asset(clip[1]))
            body.play(False)
            body.set_position(fraction * clip[2], False)
            body.set_play_rate(0.0)
    if part == 'hand':
        turn, orbit, pitch = 0, 0, -6
        boom.set_editor_property('target_arm_length', 300.0)
        cam.set_field_of_view(6.0)
        aim = body.get_socket_location('hand_' + view) + unreal.Vector(0, 0, -6)
    elif part in ('face', 'expr', 'viseme'):
        name, yaw, pitch = view
        turn, orbit = 0, yaw
        boom.set_editor_property('target_arm_length', 300.0)
        cam.set_field_of_view(9.0)
        aim = body.get_socket_location('head') + unreal.Vector(0, 0, 3)
    else:
        # the body turns, the camera stays where the front view is clear: walls behind a character in the
        # level hid the back view when the camera orbited instead
        name, yaw = view
        pitch, turn, orbit = -3, -yaw, 0
        boom.set_editor_property('target_arm_length', 430.0)
        cam.set_field_of_view(36.0)
        if 'body_aim' not in STATE:      # one aim for every body and pose view: halfway up the bind height
            head, foot = body.get_socket_location('head'), body.get_socket_location('foot_l')
            at = pawn.get_actor_location()      # the turn axis, so a turned body stays centred
            STATE['body_aim'] = unreal.Vector(at.x, at.y, (head.z + foot.z) / 2 + 4)
        aim = STATE['body_aim']
        if part == 'motion':      # clips carry her off her mark (climb, hang, a fall): follow the hips instead
            pelvis = body.get_socket_location('pelvis')
            aim = unreal.Vector(pelvis.x, pelvis.y, pelvis.z + 8)
            cam.set_field_of_view(40.0)
    pawn.set_actor_rotation(unreal.Rotator(0, 0, STATE['yaw'] + turn), False)
    boom.set_editor_property('target_offset', aim - boom.get_world_location())
    # the boom looks along the control rotation from behind: to see the front, look back at the character
    pawn.get_controller().set_control_rotation(unreal.Rotator(0, pitch, STATE['yaw'] + orbit + 180))
    if into > length - 0.5 and STATE.get('shot') != i:
        STATE['shot'] = i
        console(pawn, f"HighResShot 1 filename={(SHOTS / f'{label}.png').as_posix()}")


HAIR_SHAPES = {'left': 'rac_hair_sway_left', 'right': 'rac_hair_sway_right', 'forward': 'rac_hair_sway_forward',
               'back': 'rac_hair_sway_back', 'lift': 'rac_hair_lift'}
# A damped spring per axis (component space, cm): the hair's tip lags the head's acceleration and settles.
# ~1.3 Hz, a little bouncy; 15 m/s^2 (a sprint start) swings the tips the shapes' full 3.5 cm.
HAIR_OMEGA, HAIR_DAMPING, HAIR_LAG = 8.0, 0.35, 3.5 / 1500.0
HAIR_FULL_CM = {'side': 3.5, 'fwd': 3.5, 'up': 2.5}


def hair_motion(pawn, delta):
    """Secondary motion for the loose hair by its sway morphs (game_review_finish.py), from the head's acceleration.

    Runtime Python cannot add a physics node to the animation blueprint, so the review drives morphs instead: the head
    bone's world acceleration, turned into the mesh component's axes (+X the character's left, +Y forward, +Z up, as
    the shapes were authored), pulls each axis of a damped spring the other way, as inertia pulls hair.
    """
    body = pawn.get_editor_property('mesh')
    if 'hair' not in STATE:
        mesh = unreal.load_asset(MESH)
        names = {str(m.get_name()) for m in mesh.get_editor_property('morph_targets')}
        STATE['hair'] = {'on': all(n in names for n in HAIR_SHAPES.values()), 'x': [0.0] * 3, 'v': [0.0] * 3,
                         'p': None, 'vel': None, 'acc': [0.0] * 3, 'peak': {k: 0.0 for k in HAIR_SHAPES}}
    h = STATE['hair']
    if not h['on'] or delta <= 0:
        return
    dt = min(delta, 0.05)
    head = body.get_socket_location('head')
    p = [head.x, head.y, head.z]
    if h['p'] is not None:
        vel = [(a - b) / dt for a, b in zip(p, h['p'])]
        if h['vel'] is not None:
            raw = [(a - b) / dt for a, b in zip(vel, h['vel'])]
            h['acc'] = [0.6 * a + 0.4 * r for a, r in zip(h['acc'], raw)]      # finite differences are noisy
        h['vel'] = vel
    h['p'] = p
    local = unreal.MathLibrary.inverse_transform_direction(body.get_world_transform(), unreal.Vector(*h['acc']))
    target = [-HAIR_LAG * local.x, -HAIR_LAG * local.y, -HAIR_LAG * local.z]
    steps = max(1, int(dt / (1 / 120)))
    for _ in range(steps):      # semi-implicit Euler, sub-stepped for stability at low frame rates
        for i in range(3):
            accel = HAIR_OMEGA ** 2 * (target[i] - h['x'][i]) - 2 * HAIR_DAMPING * HAIR_OMEGA * h['v'][i]
            h['v'][i] += accel * dt / steps
            h['x'][i] += h['v'][i] * dt / steps
    side, fwd, up = h['x']
    weights = {'left': max(0.0, side) / HAIR_FULL_CM['side'], 'right': max(0.0, -side) / HAIR_FULL_CM['side'],
               'forward': max(0.0, fwd) / HAIR_FULL_CM['fwd'], 'back': max(0.0, -fwd) / HAIR_FULL_CM['fwd'],
               'lift': max(0.0, up) / HAIR_FULL_CM['up']}
    for key, weight in weights.items():
        weight = min(1.0, weight)
        body.set_morph_target(HAIR_SHAPES[key], weight, False)
        h['peak'][key] = max(h['peak'][key], weight)


def play(pawn, age):
    walking = pawn.get_controller().is_input_key_down(WALK_KEY)
    if walking != STATE['walking']:
        pawn.set_editor_property('walk_speed', UE['walk_speed'] if walking else STATE['normal_speed'])
        STATE['walking'] = walking
    for when in (4, 9):        # a standing shot, then the face close, from the front
        if age >= when and when not in STATE.setdefault('shots', set()):
            STATE['shots'].add(when)
            pawn.get_controller().set_control_rotation(unreal.Rotator(0, -10, pawn.get_actor_rotation().yaw + 180))
            boom = pawn.get_component_by_class(unreal.SpringArmComponent)
            if when == 9:
                STATE['boom'] = (boom.get_editor_property('target_arm_length'), boom.get_editor_property('target_offset'))
                boom.set_editor_property('target_arm_length', 90.0)
                boom.set_editor_property('target_offset', unreal.Vector(0, 0, 62))
                console(pawn, f'AetherSpeak {SPEAK_LINE}')      # the mouth up close, with the line's sound
        if age >= when + 1.5 and f'{when}s' not in STATE['shots']:
            STATE['shots'].add(f'{when}s')
            console(pawn, f"HighResShot 1 filename={(OUT / f'play-{when}s.png').as_posix()}")
    speak = pawn.get_controller().is_input_key_down(SPEAK_KEY)
    if speak and not STATE.get('speak_down'):
        console(pawn, f'AetherSpeak {SPEAK_LINE}')
    STATE['speak_down'] = speak
    if 'boom' in STATE and age >= 16:      # back to the normal play camera once the line is over
        boom = pawn.get_component_by_class(unreal.SpringArmComponent)
        boom.set_editor_property('target_arm_length', STATE['boom'][0])
        boom.set_editor_property('target_offset', STATE['boom'][1])
        del STATE['boom']


def tick(delta):
    try:
        pawn = STATE['pawn']
        if pawn is None or pawn.get_controller() is None:
            STATE['pawn'] = None
            for candidate in unreal.ObjectIterator(PAWN_CLASS):
                if candidate.is_player_controlled() and candidate.get_controller() is not None:
                    STATE['pawn'] = candidate
                    STATE['walking'] = None
                    break
            pawn = STATE['pawn']
            if pawn is None:
                if not STATE['ready'] and time.monotonic() - STATE['started'] > 90:
                    raise RuntimeError('No controlled player pawn within 90 seconds')
                return
            STATE['swap'] = ({'baseline': True, 'face': configure_face(pawn, quiet=True)} if BASELINE
                             else swap(pawn))
            STATE['normal_speed'] = float(pawn.get_editor_property('walk_speed'))
            STATE['configured_at'] = time.monotonic()
        age = time.monotonic() - STATE['configured_at']
        if not STATE['ready'] and age >= 2:
            body = pawn.get_editor_property('mesh')
            result = {'ready': True, 'mode': MODE, 'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'pawn': pawn.get_path_name(), 'mesh': MESH, 'anim_class': ABP_CLASS, **STATE['swap'],
                      'controls': 'WASD move; hold Left Alt to walk; Shift sprint; mouse camera; L says a line',
                      'saved_assets_modified': False,
                      'bones': {b: str(body.get_socket_location(b)) for b in ('root', 'pelvis', 'head', 'foot_l')}}
            (OUT / 'ready.json').write_text(json.dumps(result, indent=2))
            STATE['ready'] = True
            unreal.log_warning('RAC_GAME_REVIEW_READY')
        if MODE == 'closeups':
            if age >= 3:
                closeups(pawn, age - 3)
        else:
            play(pawn, age)
            try:
                hair_motion(pawn, delta)
            except Exception:      # a hair fault turns the hair off, never the review
                STATE.setdefault('hair', {})['on'] = False
                (OUT / 'hair-motion-error.json').write_text(json.dumps({'error': traceback.format_exc()}, indent=2))
            if age >= 30 and 'hair_written' not in STATE and 'hair' in STATE:      # evidence the hair is moving
                STATE['hair_written'] = True
                (OUT / 'hair-motion.json').write_text(json.dumps(
                    {'shapes_found': STATE['hair']['on'], 'peak_weights': STATE['hair']['peak']}, indent=1))
    except Exception:
        (OUT / 'runtime-error.json').write_text(json.dumps({'error': traceback.format_exc()}, indent=2))
        unreal.unregister_slate_post_tick_callback(STATE['handle'])
        unreal.log_error('RAC_GAME_REVIEW_ERROR')
        if MODE == 'closeups' and STATE.get('pawn'):
            console(STATE['pawn'], 'quit')


STATE['handle'] = unreal.register_slate_post_tick_callback(tick)
