"""Game review step 6: import the exported character into The Aether Wars as a review player (nothing existing changes).

Headless, editor and game closed:
  set RAC_GAME_REVIEW_JOB=<attempt>\\job.json
  UnrealEditor-Cmd.exe <project> -run=pythonscript -script=<this file> -unattended -nop4 -nosplash
Writes <attempt>\\06-unreal\\import.json.

1. FBX -> <content_root>/<Name>/<Version>/SK_<Name>_<Version>, on its own skeleton, with morphs, vertex colours
   (the scatter mask) and a physics asset. The folder is the review's alone and is started fresh.
2. One material per slot from textures.json: normal maps flipped to Unreal's convention (glTF is OpenGL +Y), hair
   with the job's hair look, skin with a Burley subsurface profile whose opacity is scatter x vertex colour G.
   Each named look in the job becomes a further material set the closeups swap to.
3. Animations, by the job's unreal.animation_source:
   "player": what the player plays now, from the mesh the player Blueprint uses (The Aether Wars: Character02's
   AnimBP, with its library locomotion, idles, turns, starts and stops, and every montage and traversal clip in the
   player's slots), through one retargeter built the installer's way. The character moves as the game's hero does.
   "manny": Epic's Manny combat AnimBP and montages through the installer's prepare_animations, plus the
   Manny-authored traversal clips; a slot with no Manny source comes from its owner (secondary_source_mesh).
4. The mapping (player's animation -> this character's copy) the play script swaps on the live pawn.

Adapted from the Remora game86 import (2026-11-07), itself from the Raider v5 import.
"""
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path

import unreal

PROJECT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
sys.path.insert(0, str(PROJECT / 'Tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import CharacterInstall as ci  # noqa: E402  (The Aether Wars' own installer)
import retarget_calibration as rc  # noqa: E402  (the character's own retarget pose and gait style)

JOB = json.loads(Path(os.environ['RAC_GAME_REVIEW_JOB']).read_text(encoding='utf-8'))
UE = JOB['unreal']
TAG = JOB['tag']
DEST = UE['dest']
ANIM_DIR = DEST + '/Anims'
PREFIX = TAG + '_'
MESH = UE['mesh']
FBX = JOB['paths']['fbx']
TEX = Path(JOB['paths']['textures'])
OUT = Path(JOB['paths']['unreal'])
SPEC = json.loads((TEX / 'textures.json').read_text(encoding='utf-8'))
TRAVERSAL = {p.lower(): f'/Game/AetherWars/Animations/Traversal/AW_{p}' for p in (
    'Climb_Idle', 'Climb_Up', 'Climb_Down', 'Climb_Left', 'Climb_Right', 'Climb_Leap', 'Hang_Idle', 'Hang_Left',
    'Hang_Right', 'Mantle', 'Glide')}
CASTS = {
    'push_montage': '/Game/AetherWars/Animations/Casts/AM_AetherPush',
    'left_push_montage': '/Game/AetherWars/Animations/Casts/AM_AetherPushLeft',
    'pull_montage': '/Game/AetherWars/Animations/Casts/AM_AetherRecall',
}
ANIM_SLOTS = [      # (component class or None for the character, properties that hold animation assets)
    (None, ['dodge_montage', 'backstep_montage', 'combo_attack_montage', 'charged_attack_montage', 'death_animation']),
    ('AetherPowersComponent', ['surge_montage', 'push_montage', 'left_push_montage', 'pull_montage', 'pulse_montage',
                               'bomb_throw_montage']),
    ('AetherTraversalAnimComponent', ['climb_idle', 'climb_up', 'climb_down', 'climb_left', 'climb_right', 'climb_leap',
                                      'hang_idle', 'hang_left', 'hang_right', 'mantle', 'glide']),
    ('AetherGliderComponent', ['deployment_animation']),
]
REPORT = {'job': os.environ['RAC_GAME_REVIEW_JOB']}
TEXTURES = {}


def save(asset):
    unreal.EditorAssetLibrary.save_loaded_asset(asset, False)


def legacy_fbx(task):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    unreal.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 0')
    try:
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    finally:
        unreal.SystemLibrary.execute_console_command(world, 'Interchange.FeatureFlags.Import.FBX 1')


def import_mesh():
    options = unreal.FbxImportUI()
    options.automated_import_should_detect_type = False
    options.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    options.import_as_skeletal = True
    options.import_mesh = True
    options.import_materials = False
    options.import_textures = False
    options.import_animations = False
    options.create_physics_asset = True
    data = options.skeletal_mesh_import_data
    data.set_editor_property('import_morph_targets', True)
    data.normal_import_method = unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS
    data.vertex_color_import_option = unreal.VertexColorImportOption.REPLACE
    task = unreal.AssetImportTask()
    task.filename = FBX
    task.destination_path = DEST
    task.destination_name = MESH.rsplit('/', 1)[-1]
    task.automated = True
    task.replace_existing = True
    task.save = True
    task.options = options
    legacy_fbx(task)
    mesh = unreal.load_asset(MESH)
    assert mesh, 'FBX import failed'
    for extra in (mesh.get_editor_property('skeleton'), mesh.get_editor_property('physics_asset')):
        if extra:
            save(extra)
    save(mesh)
    b = mesh.get_bounds()
    REPORT['mesh'] = {'path': MESH, 'height_cm': round(b.box_extent.z * 2, 2),
                      'morph_targets': len(mesh.get_editor_property('morph_targets')),
                      'slots': [str(s.material_slot_name) for s in mesh.materials],
                      'skeleton': mesh.get_editor_property('skeleton').get_path_name()}
    low, high = JOB['height_cm']
    assert low < REPORT['mesh']['height_cm'] < high, REPORT['mesh']
    return mesh


def import_texture(file, srgb, kind):
    key = (file, kind)
    if key in TEXTURES:
        return TEXTURES[key]
    name = f'T_{TAG}_' + Path(file).stem.replace('.', '_') + {'colour': '', 'masks': '_MR', 'normal': '_N',
                                                               'flow': '_F'}[kind]
    task = unreal.AssetImportTask()
    task.filename = str(TEX / file)
    task.destination_path = DEST + '/Textures'
    task.destination_name = name
    task.automated = True
    task.replace_existing = True
    task.save = True
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    tex = unreal.load_asset(f'{DEST}/Textures/{name}')
    assert tex, file
    tex.set_editor_property('srgb', srgb)
    if kind == 'masks':
        tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_MASKS)
    elif kind == 'normal':
        tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_NORMALMAP)
    save(tex)
    TEXTURES[key] = tex
    return tex


def skin_profile():
    """UE's Burley skin profile (its defaults); one per review."""
    name = f'SSP_{TAG}_Skin'
    path = f'{DEST}/{name}'
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.load_asset(path)
    profile = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST, unreal.SubsurfaceProfile,
                                                                       unreal.SubsurfaceProfileFactory())
    save(profile)
    return profile


def slot_kind(slot):
    if slot in JOB['skin_materials']:
        return 'skin'
    hair = JOB.get('hair_materials')
    if (slot in hair) if hair else ('hair' in slot.lower() or 'scalp' in slot.lower()):
        return 'hair'
    if 'teeth' in slot.lower():
        return 'teeth'
    return None


def look_for(slot, look_name=None):
    """The default look for a slot's kind, with a named look's overrides on top."""
    kind = slot_kind(slot)
    defaults = {'skin': JOB['skin_look'], 'hair': JOB['hair_look'], 'teeth': JOB.get('teeth_look', {})}
    settings = dict(defaults.get(kind, {}))
    if look_name:
        named = JOB['looks'][look_name]
        settings.update(named.get(kind, {}) if kind else {})
        settings.update(named.get(slot, {}))
    return settings


def look_touches(slot, look_name):
    named = JOB['looks'][look_name]
    return slot in named or (slot_kind(slot) in named)


def make_material(slot, e, look, suffix=''):
    """One material for a slot's textures.json entry under a look."""
    lib = unreal.MaterialEditingLibrary
    P = unreal.MaterialProperty
    name = f'M_{TAG}_{slot}{suffix}'
    path = f'{DEST}/Materials/{name}'
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        m = unreal.load_asset(path)
        lib.delete_all_material_expressions(m)
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST + '/Materials', unreal.Material,
                                                                     unreal.MaterialFactoryNew())
    m.set_editor_property('used_with_skeletal_mesh', True)
    m.set_editor_property('used_with_morph_targets', True)
    translucent = bool(e.get('alpha'))
    subsurface = look.get('subsurface')
    hair_shading = look.get('shading') == 'hair' and e.get('flow')
    if hair_shading:      # Marschner hair along the baked flow: highlights run along the strands
        m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_HAIR)
    if subsurface:
        m.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE)
        m.set_editor_property('subsurface_profile', skin_profile())
    if translucent:
        m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
        m.set_editor_property('translucency_lighting_mode', unreal.TranslucencyLightingMode.TLM_SURFACE)
    base_tex = None
    if e.get('base'):
        base_tex = lib.create_material_expression(m, unreal.MaterialExpressionTextureSample, -900, 0)
        base_tex.texture = import_texture(e['base'], True, 'colour')
        colour, pin = base_tex, 'RGB'
        if translucent:
            lib.connect_material_property(base_tex, 'A', P.MP_OPACITY)
    else:
        colour = lib.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -900, 0)
        colour.constant = unreal.LinearColor(*e['base_factor'][:3], 1)
        pin = ''
    saturation, albedo, tint = look.get('saturation', 1.0), look.get('albedo', 1.0), look.get('base_tint')
    if saturation != 1.0:
        des = lib.create_material_expression(m, unreal.MaterialExpressionDesaturation, -650, 0)
        lib.connect_material_expressions(colour, pin, des, '')
        fraction = lib.create_material_expression(m, unreal.MaterialExpressionConstant, -850, 150)
        fraction.r = 1 - saturation
        lib.connect_material_expressions(fraction, '', des, 'Fraction')
        colour, pin = des, ''
    if albedo != 1.0 or tint:
        k = lib.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -650, 150)
        t = tint or [1.0, 1.0, 1.0]
        k.constant = unreal.LinearColor(t[0] * albedo, t[1] * albedo, t[2] * albedo, 1)
        mul = lib.create_material_expression(m, unreal.MaterialExpressionMultiply, -450, 0)
        lib.connect_material_expressions(colour, pin, mul, 'A')
        lib.connect_material_expressions(k, '', mul, 'B')
        colour, pin = mul, ''
    lib.connect_material_property(colour, pin, P.MP_BASE_COLOR)
    textured_rough = e.get('rough') and ('roughness' not in look or look.get('roughness_from_texture'))
    if textured_rough:
        t = lib.create_material_expression(m, unreal.MaterialExpressionTextureSample, -900, 300)
        t.texture = import_texture(e['rough'], False, 'masks')
        t.sampler_type = unreal.MaterialSamplerType.SAMPLERTYPE_MASKS
        lib.connect_material_property(t, 'G', P.MP_ROUGHNESS)     # glTF packs roughness in G, metal in B
        lib.connect_material_property(t, 'B', P.MP_METALLIC)
    else:
        r = lib.create_material_expression(m, unreal.MaterialExpressionConstant, -450, 300)
        r.r = look.get('roughness', e.get('roughness', 0.6))
        lib.connect_material_property(r, '', P.MP_ROUGHNESS)
    strength = look.get('normal_strength', 1.0)
    if e.get('normal') and strength > 0:
        n = lib.create_material_expression(m, unreal.MaterialExpressionTextureSample, -900, 600)
        n.texture = import_texture(e['normal'], False, 'normal')
        n.sampler_type = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
        flip = lib.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -900, 800)
        flip.constant = unreal.LinearColor(strength, -strength, 1, 1)      # green flipped; xy scaled by strength
        mul = lib.create_material_expression(m, unreal.MaterialExpressionMultiply, -450, 600)
        lib.connect_material_expressions(n, 'RGB', mul, 'A')
        lib.connect_material_expressions(flip, '', mul, 'B')
        lib.connect_material_property(mul, '', P.MP_NORMAL)
    if 'specular' in look:
        spec = lib.create_material_expression(m, unreal.MaterialExpressionConstant, -450, 450)
        spec.r = look['specular']
        if look.get('specular_from_base') and base_tex and e.get('base_mean_linear'):
            # brighter strands shine, the dark gaps between them do not: specular x base / mean base, at most 3x
            lum = lib.create_material_expression(m, unreal.MaterialExpressionDotProduct, -650, 450)
            weights = lib.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -900, 450)
            weights.constant = unreal.LinearColor(0.2126, 0.7152, 0.0722, 1)
            lib.connect_material_expressions(base_tex, 'RGB', lum, 'A')
            lib.connect_material_expressions(weights, '', lum, 'B')
            scale = lib.create_material_expression(m, unreal.MaterialExpressionConstant, -650, 550)
            scale.r = look['specular'] / max(e['base_mean_linear'], 1e-4)
            mul = lib.create_material_expression(m, unreal.MaterialExpressionMultiply, -450, 500)
            lib.connect_material_expressions(lum, '', mul, 'A')
            lib.connect_material_expressions(scale, '', mul, 'B')
            cap = lib.create_material_expression(m, unreal.MaterialExpressionMin, -300, 500)
            top = lib.create_material_expression(m, unreal.MaterialExpressionConstant, -450, 650)
            top.r = min(1.0, 3 * look['specular'])
            lib.connect_material_expressions(mul, '', cap, 'A')
            lib.connect_material_expressions(top, '', cap, 'B')
            spec = cap
        lib.connect_material_property(spec, '', P.MP_SPECULAR)
    if hair_shading:
        flow = lib.create_material_expression(m, unreal.MaterialExpressionTextureSample, -900, 1000)
        flow.texture = import_texture(e['flow'], False, 'flow')
        flow.sampler_type = unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR
        two = lib.create_material_expression(m, unreal.MaterialExpressionConstantBiasScale, -650, 1000)
        two.set_editor_property('bias', -0.5)
        two.set_editor_property('scale', 2.0)
        lib.connect_material_expressions(flow, 'RGB', two, '')
        axes = lib.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -650, 1150)
        axes.constant = unreal.LinearColor(1, -1, 0, 1)      # baked in Blender's (OpenGL) frame: flip y for Unreal
        tangent = lib.create_material_expression(m, unreal.MaterialExpressionMultiply, -450, 1000)
        lib.connect_material_expressions(two, '', tangent, 'A')
        lib.connect_material_expressions(axes, '', tangent, 'B')
        lib.connect_material_property(tangent, '', P.MP_TANGENT)
        scatter = lib.create_material_expression(m, unreal.MaterialExpressionConstant, -450, 1150)
        scatter.r = look.get('scatter', 0.3)
        lib.connect_material_property(scatter, '', P.MP_METALLIC)      # the hair model's Scatter input
    if subsurface:      # the profile's opacity is how much the skin scatters
        op = lib.create_material_expression(m, unreal.MaterialExpressionConstant, -450, 750)
        op.r = look.get('scatter', 1.0)
        if look.get('scatter_mask'):      # game_review_finish.py ScatterMask: none in the band under the hair
            vc = lib.create_material_expression(m, unreal.MaterialExpressionVertexColor, -650, 800)
            mm = lib.create_material_expression(m, unreal.MaterialExpressionMultiply, -300, 750)
            lib.connect_material_expressions(op, '', mm, 'A')
            lib.connect_material_expressions(vc, 'G', mm, 'B')
            op = mm
        lib.connect_material_property(op, '', P.MP_OPACITY)
    lib.recompile_material(m)
    save(m)
    return m


def make_materials(mesh):
    slots = mesh.materials
    done = {}
    for i, slot in enumerate(slots):
        name = str(slot.material_slot_name)
        entry = SPEC.get(name)
        if entry is None:
            done[name] = 'no textures.json entry'
            continue
        slot.material_interface = make_material(name, entry, look_for(name))
        slots[i] = slot
        done[name] = {'material': slot.material_interface.get_path_name(), 'kind': slot_kind(name),
                      'look': look_for(name)}
    mesh.materials = slots
    save(mesh)
    REPORT['materials'] = done
    REPORT['material_sets'] = {
        look: {name: make_material(name, SPEC[name], look_for(name, look), '_' + look).get_path_name()
               for name in SPEC if name in done and look_touches(name, look)}
        for look in JOB['looks']}


def player_anim_sources():
    """What the player Blueprint's character and components currently play: (owner, property, path)."""
    bp = unreal.load_asset(UE['player_blueprint'])
    cdo = unreal.get_default_object(bp.generated_class())
    found = []
    for cls_name, props in ANIM_SLOTS:
        owners = [cdo]
        if cls_name:
            cls = getattr(unreal, cls_name, None)
            comp = cdo.get_component_by_class(cls) if cls else None
            owners = [comp] if comp else []
        for owner in owners:
            for prop in props:
                value = owner.get_editor_property(prop)
                if value:
                    found.append((cls_name, prop, value.get_path_name().split('.')[0]))
    return found


def retarget(target):
    """Manny's combat AnimBP and montages through the game's installer, plus the traversal clips."""
    ci.CHARACTER, ci.NAME, ci.DEST, ci.MESH = {}, TAG, DEST, MESH
    ci.IK_RIG, ci.RETARGETER, ci.ANIM_DIR, ci.ANIM_PREFIX = f'IK_{TAG}', f'RTG_Manny_{TAG}', ANIM_DIR, PREFIX
    calibration = UE.get('retarget_pose')
    if calibration:      # the installer's retargeter, built here so the character's calibration lands before the batch
        manny = unreal.load_asset(ci.SOURCE_MESH)
        rtg, _ = build_retargeter(manny, target, 'Manny')
        REPORT['retarget_pose'] = {'spec': calibration, 'changed': rc.calibrate(
            rtg, manny, target, calibration, ci.ref_local_rotations(manny), ci.ref_local_rotations(target))}
        save(rtg)
        created = batch_retarget(ci._retarget_sources(target), manny, target, rtg)
        ci.repair_blendspaces()      # relinks blend space samples, then montage segments (the installer's repairs)
    else:
        created = ci.prepare_animations()
    extra_paths = [p for p in [*TRAVERSAL.values(), *CASTS.values()] if unreal.EditorAssetLibrary.does_asset_exist(p)]
    inputs = unreal.IKRetargetBatchOperationInputs()
    inputs.assets_to_retarget = [unreal.EditorAssetLibrary.find_asset_data(p) for p in extra_paths]
    inputs.source_mesh = unreal.load_asset(ci.SOURCE_MESH)
    inputs.target_mesh = target
    inputs.ik_retarget_asset = unreal.load_asset(f'{DEST}/RTG_Manny_{TAG}')
    inputs.target_path = ANIM_DIR
    inputs.prefix = PREFIX
    inputs.include_referenced_assets = True
    inputs.overwrite_existing_files = True
    inputs.retain_additive_flags = True
    created_t = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    for data in registry.get_assets_by_path(ANIM_DIR):
        save(data.get_asset())
    ci.repair_montages()
    if UE.get('gait_style'):
        REPORT['gait_style'] = rc.apply_gait_style(ANIM_DIR, PREFIX, target, unreal.load_asset(ci.SOURCE_MESH),
                                                   UE['gait_style'])
    if UE.get('glider_grip'):
        REPORT['glider_grip'] = glider_grip(target)
    REPORT['retargeted'] = len(created) + len(created_t)
    abps = [d for d in registry.get_assets_by_path(ANIM_DIR) if str(d.asset_class_path.asset_name) == 'AnimBlueprint']
    REPORT['anim_blueprints'] = [str(d.package_name) for d in abps]
    assert REPORT['anim_blueprints'], 'no animation blueprint was retargeted'
    sources = {('', k): v for k, v in ci.ANIM_PROPERTIES.items()}
    sources[('', 'backstep_montage')] = ci.ANIM_PROPERTIES['dodge_montage']
    sources.update({('AetherTraversalAnimComponent', k): v for k, v in TRAVERSAL.items()})
    sources.update({('AetherPowersComponent', k): v for k, v in CASTS.items() if unreal.EditorAssetLibrary.does_asset_exist(v)})
    slots, cut = [], []
    for cls_name, prop, current in player_anim_sources():
        if cls_name == 'AetherGliderComponent':
            continue                      # animates the glider's own mesh, not the character
        src = sources.get((cls_name or '', prop))
        if src is None:
            cut.append(f'{cls_name or "character"}.{prop} ({current})')
            continue
        copy = f"{ANIM_DIR}/{PREFIX}{src.rsplit('/', 1)[-1]}"
        assert unreal.EditorAssetLibrary.does_asset_exist(copy), copy
        slots.append((cls_name, prop, current))
        REPORT.setdefault('mapping', {})[current] = copy
    REPORT['player_anim_slots'] = slots
    REPORT['cut_no_manny_source'] = cut
    REPORT['idle_clip'] = f'{ANIM_DIR}/{PREFIX}MM_Idle'
    secondary = UE.get('secondary_source_mesh')
    if secondary and cut:
        retarget_secondary(target, secondary)


def glider_grip(target):
    """The Sailwing hangs where the hero's hands are; on another body the hands miss the handles (Remora: open hands
    a few cm under them, arms uneven, wrists bent back). Fit this character's glide clip to the handles from the
    hero's own glide clip and record the glider offset the play script hangs it at (retarget_calibration)."""
    bp = unreal.load_asset(UE['player_blueprint'])
    cdo = unreal.get_default_object(bp.generated_class())
    glider = cdo.get_component_by_class(unreal.AetherGliderComponent)
    traversal = cdo.get_component_by_class(unreal.AetherTraversalAnimComponent)
    body = cdo.get_component_by_class(unreal.SkeletalMeshComponent)
    hero_clip = traversal.get_editor_property('glide') if traversal else None
    clip = unreal.load_asset(f"{ANIM_DIR}/{PREFIX}{TRAVERSAL['glide'].rsplit('/', 1)[-1]}")
    assert glider and hero_clip and clip, 'glider_grip needs the player glider, its glide slot and this glide clip'
    receipt = rc.fit_glider_grip(clip, target, rc.skeleton_info(target), hero_clip,
                                 body.get_editor_property('skeletal_mesh_asset'),
                                 str(glider.get_editor_property('back_socket')),
                                 glider.get_editor_property('flight_offset'))
    receipt['clip'] = clip.get_path_name().split('.')[0]
    return receipt


def build_retargeter(source, target, name):
    """An IK retargeter from source to target built the installer's way: auto IK rigs plus twist chains, exact chain
    map, one-to-one chains, IK bones pinned, and the target's retarget pose offset to the source's reference rotations
    bone for bone. Returns (retargeter, number of offset bones)."""
    rigs = []
    for rig_name, mesh in ((f'IK_{TAG}_{name}Source', source), (f'IK_{TAG}', target)):
        rig = ci.asset(rig_name, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory)
        controller = unreal.IKRigController.get_controller(rig)
        assert controller.set_skeletal_mesh(mesh)
        assert controller.apply_auto_generated_retarget_definition(), rig_name
        existing = {str(c.chain_name) for c in controller.get_retarget_chains()}
        for bone in ci.TWIST:
            if bone not in existing:
                controller.add_retarget_chain(bone, bone, bone, 'None')
        save(rig)
        rigs.append(rig)
    rtg = ci.asset(f'RTG_{name}_{TAG}', unreal.IKRetargeter, unreal.IKRetargetFactory)
    controller = unreal.IKRetargeterController.get_controller(rtg)
    controller.remove_all_ops()
    for side, rig, mesh in zip([unreal.RetargetSourceOrTarget.SOURCE, unreal.RetargetSourceOrTarget.TARGET], rigs,
                               [source, target]):
        controller.set_ik_rig(side, rig)
        controller.set_preview_mesh(side, mesh)
    controller.add_default_ops()
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    pin = controller.get_op_controller(controller.add_retarget_op('/Script/IKRig.IKRetargetPinBoneOp'))
    for source_bone, ik_bone in ci.PIN_BONES:
        pin.set_bone_pair(source_bone, ik_bone)
    pin_settings = pin.get_settings()
    pin_settings.set_editor_property('skeleton_to_copy_from', unreal.RetargetSourceOrTarget.TARGET)
    pin.set_settings(pin_settings)
    for i in range(controller.get_num_retarget_ops()):
        op = controller.get_op_controller(i)
        if isinstance(op, unreal.IKRetargetFKChainsController):
            settings = op.get_settings()
            chains = settings.get_editor_property('chains_to_retarget')
            for c in range(len(chains)):
                chain = chains[c]
                chain.set_editor_property('rotation_mode', unreal.FKChainRotationMode.ONE_TO_ONE)
                chains[c] = chain
            settings.set_editor_property('chains_to_retarget', chains)
            op.set_settings(settings)
    pose = controller.get_current_retarget_pose_name(unreal.RetargetSourceOrTarget.TARGET)
    controller.reset_retarget_pose(pose, [], unreal.RetargetSourceOrTarget.TARGET)
    src_ref, tgt_ref = ci.ref_local_rotations(source), ci.ref_local_rotations(target)
    offsets = 0
    for bone, local in tgt_ref.items():
        if bone in src_ref and bone != 'root':
            delta = local.inversed() * src_ref[bone]
            if abs(delta.get_angle()) > 1e-4:
                controller.set_rotation_offset_for_retarget_pose_bone(bone, delta, unreal.RetargetSourceOrTarget.TARGET)
                offsets += 1
    save(rtg)
    return rtg, offsets


def batch_retarget(paths, source, target, rtg):
    inputs = unreal.IKRetargetBatchOperationInputs()
    inputs.assets_to_retarget = [unreal.EditorAssetLibrary.find_asset_data(p) for p in paths]
    inputs.source_mesh = source
    inputs.target_mesh = target
    inputs.ik_retarget_asset = rtg
    inputs.target_path = ANIM_DIR
    inputs.prefix = PREFIX
    inputs.include_referenced_assets = True
    inputs.overwrite_existing_files = True
    inputs.retain_additive_flags = True
    created = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    for data in unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_path(ANIM_DIR):
        save(data.get_asset())
    return created


def copy_of(path):
    return f"{ANIM_DIR}/{PREFIX}{path.rsplit('/', 1)[-1]}"


def retarget_player(target):
    """The player's own animation set, retargeted from the mesh the player Blueprint uses: its AnimBP (the batch
    copies everything it references: locomotion blend space, idles, turns, starts, stops, jumps) and every slot.
    Blend spaces and montages are relinked after the batch (the installer's repairs)."""
    ci.CHARACTER, ci.NAME, ci.DEST, ci.MESH = {}, TAG, DEST, MESH
    ci.ANIM_DIR, ci.ANIM_PREFIX = ANIM_DIR, PREFIX
    bp = unreal.load_asset(UE['player_blueprint'])
    body = unreal.get_default_object(bp.generated_class()).get_component_by_class(unreal.SkeletalMeshComponent)
    source = body.get_editor_property('skeletal_mesh_asset')
    abp = body.get_editor_property('anim_class').get_path_name().split('.')[0]
    skeleton = source.get_editor_property('skeleton')
    slots, cut = [], []
    for cls_name, prop, current in player_anim_sources():
        if cls_name == 'AetherGliderComponent':
            continue                      # animates the glider's own mesh, not the character
        anim = unreal.load_asset(current)
        if anim and anim.get_editor_property('skeleton') == skeleton:
            slots.append((cls_name, prop, current))
        else:
            cut.append(f'{cls_name or "character"}.{prop} ({current}: not on the player mesh skeleton)')
    rtg, offsets = build_retargeter(source, target, 'Player')
    created = batch_retarget([abp] + sorted({c for _, _, c in slots}), source, target, rtg)
    repaired = ci.repair_blendspaces()      # relinks blend space samples, then montage segments
    REPORT['anim_blueprints'] = [copy_of(abp)]
    assert unreal.EditorAssetLibrary.does_asset_exist(REPORT['anim_blueprints'][0]), REPORT['anim_blueprints']
    REPORT['mapping'], REPORT['player_anim_slots'] = {}, []
    for cls_name, prop, current in slots:
        if unreal.EditorAssetLibrary.does_asset_exist(copy_of(current)):
            REPORT['mapping'][current] = copy_of(current)
            REPORT['player_anim_slots'].append((cls_name, prop, current))
        else:
            cut.append(f'{cls_name or "character"}.{prop} ({current}: no copy)')
    REPORT['cut_no_manny_source'] = cut
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    idles = sorted(str(d.package_name) for d in registry.get_assets_by_path(ANIM_DIR)
                   if str(d.asset_class_path.asset_name) == 'AnimSequence' and str(d.asset_name).endswith('MM_Idle'))
    assert idles, 'no idle among the retargeted clips'
    REPORT['idle_clip'] = idles[0]
    REPORT['retargeted'] = len(created)
    REPORT['animation_source'] = {'mode': 'player', 'source_mesh': source.get_path_name().split('.')[0],
                                  'anim_blueprint': abp, 'pose_offsets': offsets, 'repaired': repaired}


def retarget_secondary(target, source_path):
    """The player's animations with no Manny source (Character02's Aether push, left push and recall) come from the
    character that owns them, through a second retargeter built the installer's way: its own IK rigs, exact chain
    map, one-to-one chains, IK bones pinned, and the target pose offset to the source's reference rotations (the
    installer offsets to Manny's). Everything new lives in this review's folder; the source's assets are not touched."""
    source = unreal.load_asset(source_path)
    assert source, source_path
    skeleton = source.get_editor_property('skeleton')
    wanted = []
    for cls_name, prop, current in player_anim_sources():
        if (cls_name, prop, current) in [tuple(s) for s in REPORT['player_anim_slots']]:
            continue
        anim = unreal.load_asset(current)
        if anim and anim.get_editor_property('skeleton') == skeleton:
            wanted.append((cls_name, prop, current))
    if not wanted:
        REPORT['secondary_retarget'] = {'source': source_path, 'retargeted': [], 'note': 'no cut slot uses its skeleton'}
        return
    rigs = []
    for name, mesh in ((f'IK_{TAG}_SecondarySource', source), (f'IK_{TAG}', target)):
        rig = ci.asset(name, unreal.IKRigDefinition, unreal.IKRigDefinitionFactory)
        controller = unreal.IKRigController.get_controller(rig)
        assert controller.set_skeletal_mesh(mesh)
        assert controller.apply_auto_generated_retarget_definition(), name
        existing = {str(c.chain_name) for c in controller.get_retarget_chains()}
        for bone in ci.TWIST:
            if bone not in existing:
                controller.add_retarget_chain(bone, bone, bone, 'None')
        save(rig)
        rigs.append(rig)
    rtg = ci.asset(f'RTG_Secondary_{TAG}', unreal.IKRetargeter, unreal.IKRetargetFactory)
    controller = unreal.IKRetargeterController.get_controller(rtg)
    controller.remove_all_ops()
    for side, rig, mesh in zip([unreal.RetargetSourceOrTarget.SOURCE, unreal.RetargetSourceOrTarget.TARGET], rigs,
                               [source, target]):
        controller.set_ik_rig(side, rig)
        controller.set_preview_mesh(side, mesh)
    controller.add_default_ops()
    controller.auto_map_chains(unreal.AutoMapChainType.EXACT, True)
    pin = controller.get_op_controller(controller.add_retarget_op('/Script/IKRig.IKRetargetPinBoneOp'))
    for source_bone, ik_bone in ci.PIN_BONES:
        pin.set_bone_pair(source_bone, ik_bone)
    pin_settings = pin.get_settings()
    pin_settings.set_editor_property('skeleton_to_copy_from', unreal.RetargetSourceOrTarget.TARGET)
    pin.set_settings(pin_settings)
    for i in range(controller.get_num_retarget_ops()):
        op = controller.get_op_controller(i)
        if isinstance(op, unreal.IKRetargetFKChainsController):
            settings = op.get_settings()
            chains = settings.get_editor_property('chains_to_retarget')
            for c in range(len(chains)):
                chain = chains[c]
                chain.set_editor_property('rotation_mode', unreal.FKChainRotationMode.ONE_TO_ONE)
                chains[c] = chain
            settings.set_editor_property('chains_to_retarget', chains)
            op.set_settings(settings)
    pose = controller.get_current_retarget_pose_name(unreal.RetargetSourceOrTarget.TARGET)
    controller.reset_retarget_pose(pose, [], unreal.RetargetSourceOrTarget.TARGET)
    src_ref, tgt_ref = ci.ref_local_rotations(source), ci.ref_local_rotations(target)
    offsets = 0
    for bone, local in tgt_ref.items():
        if bone in src_ref and bone != 'root':
            delta = local.inversed() * src_ref[bone]
            if abs(delta.get_angle()) > 1e-4:
                controller.set_rotation_offset_for_retarget_pose_bone(bone, delta, unreal.RetargetSourceOrTarget.TARGET)
                offsets += 1
    save(rtg)
    inputs = unreal.IKRetargetBatchOperationInputs()
    inputs.assets_to_retarget = [unreal.EditorAssetLibrary.find_asset_data(c) for _, _, c in wanted]
    inputs.source_mesh = source
    inputs.target_mesh = target
    inputs.ik_retarget_asset = rtg
    inputs.target_path = ANIM_DIR
    inputs.prefix = PREFIX
    inputs.include_referenced_assets = True
    inputs.overwrite_existing_files = True
    inputs.retain_additive_flags = True
    created = unreal.IKRetargetBatchOperation.run_batch_retarget(inputs)
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    for data in registry.get_assets_by_path(ANIM_DIR):
        save(data.get_asset())
    relinked = ci.repair_montages()      # the batch can leave copied montages' segments empty
    done, still_cut = [], []
    for cls_name, prop, current in wanted:
        copy = f"{ANIM_DIR}/{PREFIX}{current.rsplit('/', 1)[-1]}"
        if unreal.EditorAssetLibrary.does_asset_exist(copy):
            REPORT['player_anim_slots'].append((cls_name, prop, current))
            REPORT['mapping'][current] = copy
            done.append(f'{cls_name or "character"}.{prop}')
        else:
            still_cut.append(current)
    REPORT['cut_no_manny_source'] = [c for c in REPORT['cut_no_manny_source']
                                     if not any(c.endswith(f'({w})') for _, _, w in wanted if w not in still_cut)]
    REPORT['secondary_retarget'] = {'source': source_path, 'retargeted': done, 'assets_created': len(created),
                                    'pose_offsets': offsets, 'montages': relinked}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT['fbx'] = FBX
    REPORT['fbx_sha256'] = hashlib.sha256(Path(FBX).read_bytes()).hexdigest()
    REPORT['dest'] = DEST
    try:
        if unreal.EditorAssetLibrary.does_directory_exist(DEST):      # this review's folder alone: start fresh
            assert unreal.EditorAssetLibrary.delete_directory(DEST), f'could not clear {DEST}'
        mesh = import_mesh()
        make_materials(mesh)
        hero_cfg = json.loads((PROJECT / 'Tools/Characters/Character02.json').read_text(encoding='utf-8'))
        if UE.get('animation_source', 'manny') == 'player' and hero_cfg.get('library_anims'):
            retarget_player(mesh)
        else:
            retarget(mesh)
        REPORT['ok'] = True
    except Exception:
        REPORT['ok'] = False
        REPORT['error'] = traceback.format_exc()
        unreal.log_error(REPORT['error'])
    (OUT / 'import.json').write_text(json.dumps(REPORT, indent=2, default=str), encoding='utf-8')
    unreal.log_warning('RAC_GAME_REVIEW_IMPORT_DONE ok=%s' % REPORT.get('ok'))


main()
