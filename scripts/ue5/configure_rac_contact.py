"""Explicit, backed-up installation of the optional RAC contact node (UE 5.8).

Call install(spec_path, fresh_output_directory) from Unreal Python. No game-specific
imports, asset names, montage choices or automatic execution are embedded here.
"""
import hashlib
import json
import math
from pathlib import Path
import shutil

import unreal

# Optional profile fields; the defaults reproduce the solver's original human-scale constants.
DEFAULTS={'action_slot':'DefaultSlot','pelvis_bone':'pelvis','maximum_lock_speed_cm_s':180,
          'maximum_plant_offset_cm':15,'maximum_pelvis_drop_cm':0,
          'lock_acquire_weight':.65,'lock_release_weight':.5}
TERRAIN_DEFAULTS={'channel':'ECC_VISIBILITY','trace_up_cm':45,'trace_down_cm':180,'minimum_ground_normal_z':.5,
                  'inner_grid_spacing_cm':7.5,'maximum_predicted_travel_cm':15}


def read_spec(path):
    path = Path(path).resolve()
    spec = json.loads(path.read_text(encoding='utf-8'))
    if spec.get('schema') != 'rac.unreal-contact-profile.v1':
        raise ValueError('unsupported contact profile')
    probe_path = path.parent/spec['probe']['path']
    if hashlib.sha256(probe_path.read_bytes()).hexdigest() != spec['probe']['sha256']:
        raise ValueError('sole sample hash changed')
    probe = json.loads(probe_path.read_text(encoding='utf-8'))
    if probe['source_sha256'] != spec.get('sample_source_sha256', spec.get('native_character_sha256')):
        raise ValueError('samples belong to another declared source mesh')
    for side in ('l','r'):
        chain = spec['chains'][side]
        if len(chain)!=4 or len(set(chain))!=4 or not all(isinstance(n,str) and n for n in chain):
            raise ValueError('each leg needs four distinct thigh/calf/foot/IK names')
        if not probe['sides'][side]:
            raise ValueError('both soles need measured samples')
        for vertex in probe['sides'][side]:
            influences=vertex['influences']
            if not influences or abs(sum(i['weight'] for i in influences)-1)>.002:
                raise ValueError('normalized skin influences required')
            for item in influences:
                if not item['bone'] or len(item['point_cm'])!=3 or item['weight']<0 or not all(
                        math.isfinite(v) for v in [item['weight'],*item['point_cm']]):
                    raise ValueError('invalid sole influence')
    for field,value in DEFAULTS.items():
        spec.setdefault(field,value)
    for field,value in TERRAIN_DEFAULTS.items():
        spec.setdefault('terrain',{}).setdefault(field,value)
    ranges=[('clearance_cm',0,1),('max_correction_cm',0,30),
            ('maximum_plant_offset_cm',0,50),('maximum_pelvis_drop_cm',0,8),
            ('combat_max_correction_cm',0,10),('release_time_s',.01,1),
            ('maximum_lock_speed_cm_s',0,2000),('lock_acquire_weight',0,1),('lock_release_weight',0,1)]
    for field,minimum,maximum in ranges:
        check_number(field,spec[field],minimum,maximum)
    if spec['lock_release_weight']>spec['lock_acquire_weight']:
        raise ValueError('lock_release_weight must not exceed lock_acquire_weight')
    terrain=spec['terrain']
    if set(terrain)-set(TERRAIN_DEFAULTS):
        raise ValueError('unknown terrain field')
    for field,minimum,maximum in [('trace_up_cm',0,500),('trace_down_cm',0,1000),('minimum_ground_normal_z',0,1),
                                   ('inner_grid_spacing_cm',1,50),('maximum_predicted_travel_cm',0,100)]:
        check_number('terrain.'+field,terrain[field],minimum,maximum)
    if not isinstance(terrain['channel'],str) or not terrain['channel']:
        raise ValueError('terrain.channel must name an ECollisionChannel')
    if not isinstance(spec['action_slot'],str) or not spec['action_slot'] or not isinstance(spec['pelvis_bone'],str) or not spec['pelvis_bone']:
        raise ValueError('action_slot and pelvis_bone must be names')
    return spec,probe


def check_number(field,value,minimum,maximum):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum<=value<=maximum:
        raise ValueError(f'out of range: {field}')


def configure(node,spec,probe):
    inner=node.get_editor_property('node')
    samples=[]
    for side,vertices in probe['sides'].items():
        for vertex in vertices:
            sample=unreal.RACSoleSample()
            sample.set_editor_property('side',0 if side=='l' else 1)
            influences=[]
            for item in vertex['influences']:
                influence=unreal.RACSoleInfluence()
                bone=unreal.BoneReference()
                bone.set_editor_property('bone_name',item['bone'])
                influence.set_editor_property('bone',bone)
                influence.set_editor_property('point',unreal.Vector(*item['point_cm']))
                influence.set_editor_property('weight',item['weight'])
                influences.append(influence)
            sample.set_editor_property('influences',influences)
            samples.append(sample)
    for key,value in {'samples':samples,'left_chain':spec['chains']['l'],'right_chain':spec['chains']['r'],
                      'action_slot':spec['action_slot'],'maximum_lock_speed':spec['maximum_lock_speed_cm_s'],
                      'lock_acquire_weight':spec['lock_acquire_weight'],'lock_release_weight':spec['lock_release_weight'],
                      'trace_channel':getattr(unreal.CollisionChannel,spec['terrain']['channel']),
                      'trace_up':spec['terrain']['trace_up_cm'],'trace_down':spec['terrain']['trace_down_cm'],
                      'minimum_ground_normal_z':spec['terrain']['minimum_ground_normal_z'],
                      'inner_grid_spacing':spec['terrain']['inner_grid_spacing_cm'],
                      'maximum_predicted_travel':spec['terrain']['maximum_predicted_travel_cm'],
                      'left_plant_curve':spec['plant_curves']['l'],'right_plant_curve':spec['plant_curves']['r'],
                      'clearance':spec['clearance_cm'],'max_correction':spec['max_correction_cm'],
                      'maximum_plant_offset':spec['maximum_plant_offset_cm'],
                      'maximum_pelvis_drop':spec['maximum_pelvis_drop_cm'],
                      'max_combat_correction':spec['combat_max_correction_cm'],
                      'release_time':spec['release_time_s']}.items():
        inner.set_editor_property(key,value)
    pelvis=unreal.BoneReference()
    pelvis.set_editor_property('bone_name',spec['pelvis_bone'])
    inner.set_editor_property('pelvis_bone',pelvis)
    montage=unreal.load_asset(spec['grounded_combat_montage']) if spec.get('grounded_combat_montage') else None
    if spec.get('grounded_combat_montage') and not isinstance(montage,unreal.AnimMontage):
        raise ValueError('the explicitly selected montage is missing')
    inner.set_editor_property('grounded_combat_montage',montage)
    node.set_editor_property('node',inner)
    return len(samples)


def install(spec_path,output):
    spec,probe=read_spec(spec_path)
    project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
    asset_path=spec['anim_blueprint']
    if not asset_path.startswith('/Game/') or '..' in asset_path:
        raise ValueError('explicit /Game/ AnimBP required')
    disk=project/'Content'/(asset_path.removeprefix('/Game/')+'.uasset')
    if not disk.is_file():
        raise ValueError('save the destination AnimBP before configuring contact')
    out=Path(output).resolve()
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(disk,out/'AnimBP.before.uasset')
    shutil.copy2(spec_path,out/'profile.json')
    receipt={'asset':asset_path,'before_sha256':hashlib.sha256(disk.read_bytes()).hexdigest(),
             'error':None,'human_approved':False,'gameplay_tested':False}
    try:
        abp=unreal.load_asset(asset_path)
        graphs=[g for g in unreal.BlueprintEditorLibrary.list_graphs(abp) if g.get_name()=='AnimGraph']
        if len(graphs)!=1:
            raise ValueError('one top-level AnimGraph required')
        ed=unreal.BlueprintGraphEditor.get_graph_editor(graphs[0])
        nodes=ed.list_all_nodes()
        contacts=[n for n in nodes if n.get_class().get_name()=='AnimGraphNode_RACSoleContact']
        if len(contacts)>1:
            raise ValueError('multiple contact nodes; choose an explicit graph adapter')
        def spawn(name,x):
            node=ed.create_node_from_name(name,unreal.Vector2D(x,0),[])
            if node is None:
                raise RuntimeError('missing node factory: '+name)
            return node
        def link(output_pin,input_pin):
            if not output_pin.try_create_connection(input_pin):
                raise RuntimeError('pose connection failed')
        if contacts:
            node=contacts[0]
        else:
            roots=[n for n in nodes if n.get_class().get_name()=='AnimGraphNode_Root']
            if len(roots)!=1:
                raise ValueError('one root pose required')
            root_pin=roots[0].list_input_pins()[0]
            pins=unreal.BlueprintGraphPinLibrary
            source=pins.list_connected_pins(root_pin)
            if len(source)!=1:
                raise ValueError('root needs one authored upstream pose')
            final=pins.get_owning_node(source[0])
            if final.get_class().get_name()=='AnimGraphNode_ComponentToLocalSpace':
                destination=final.list_input_pins()[0]
                source=pins.list_connected_pins(destination)
                if len(source)!=1:
                    raise ValueError('final component pose is ambiguous')
            else:
                to_component=spawn('Animation|ConvertSpaces|LocalToComponent',3400)
                final=spawn('Animation|ConvertSpaces|ComponentToLocal',3900)
                link(source[0],to_component.list_input_pins()[0])
                link(final.list_output_pins()[0],root_pin)
                source=to_component.list_output_pins()
                destination=final.list_input_pins()[0]
            node=spawn('Animation|SkeletalControls|RACSoleContact',3650)
            link(source[0],node.find_input_pin('ComponentPose'))
            link(node.list_output_pins()[0],destination)
        receipt['samples']=configure(node,spec,probe)
        if not unreal.BlueprintEditorLibrary.compile_blueprint(abp) or ed.list_nodes_with_errors():
            raise RuntimeError('AnimBP compile failed; backup retained')
        if not unreal.EditorAssetLibrary.save_loaded_asset(abp,False):
            raise RuntimeError('AnimBP save failed; backup retained')
        receipt['after_sha256']=hashlib.sha256(disk.read_bytes()).hexdigest()
    except Exception as error:
        receipt['error']=str(error)
        raise
    finally:
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    unreal.log_warning('RAC_CONTACT_CONFIGURED -- the measured soles have entered the ledger.')
    return receipt
