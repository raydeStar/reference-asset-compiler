# SPDX-License-Identifier: MIT
"""Read saved recovery wiring and verify prior animation/mesh assets remain intact."""
import hashlib
import json
import os
from pathlib import Path
import sys

import unreal

PROJECT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
sys.path.insert(0,str(PROJECT/'Tools'))
import CharacterInstall as ci  # noqa: E402
import LocomotionFeel as lf  # noqa: E402


def main():
    ci.configure('Tools/Characters/Character02.json')
    assert ci.CHARACTER['locomotion_feel']['sole_contact']['blend_grounding_during_recovery']
    abp=unreal.load_asset(f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}ABP_Manny_Combat')
    ed=unreal.BlueprintGraphEditor.get_graph_editor(lf._anim_graph(abp))
    assert not ed.list_nodes_with_errors()
    rigs=[n for n in ed.list_all_nodes() if n.get_class().get_name()=='AnimGraphNode_ControlRig']
    assert len(rigs)==1
    pins=unreal.BlueprintGraphPinLibrary
    links=pins.list_connected_pins(rigs[0].find_input_pin('Alpha'))
    assert len(links)==1
    title=str(pins.get_owning_node(links[0]).get_node_title()).replace(' ','')
    assert 'GetRecoveryGroundingAlpha' in title,title
    soles=[n for n in ed.list_all_nodes() if n.get_class().get_name()=='AnimGraphNode_AetherSoleContact']
    assert len(soles)==1 and len(soles[0].get_editor_property('node').get_editor_property('samples'))==149
    combat={}
    if os.environ.get('RAC_COMBAT_AUDIT')=='1':
        spec=ci.CHARACTER['locomotion_feel']['sole_contact']
        node=soles[0].get_editor_property('node')
        montage=node.get_editor_property('grounded_combat_montage')
        assert montage==unreal.load_asset(spec['grounded_combat_montage'])
        assert node.get_editor_property('max_combat_correction')==spec['combat_max_correction_cm']==3.0
        combat={'montage':montage.get_path_name(),'maximum_correction_cm':3.0}
    locomotion={}
    if os.environ.get('RAC_TURN_AUDIT')=='1':
        node=soles[0].get_editor_property('node')
        spec=ci.CHARACTER['locomotion_feel']['sole_contact']
        assert node.get_editor_property('max_correction')==spec['max_correction_cm']==10.0
        locomotion={'maximum_correction_cm':10.0,'clearance_cm':node.get_editor_property('clearance')}
    previous=json.loads(Path(os.environ['RAC_PREVIOUS_ASSET_AUDIT']).read_text())
    changes=[]
    checked=[]
    for relative,old in previous['sha256'].items():
        path=PROJECT/relative
        current=hashlib.sha256(path.read_bytes()).hexdigest()
        checked.append({'path':str(path),'sha256':current})
        if current!=old:
            changes.append(relative)
    assert len(changes)==1 and changes[0].endswith('Character02_ABP_Manny_Combat.uasset'),changes
    result={'passed':True,'saved_floor_rig_alpha_source':title,'measured_sole_samples':149,
            'active_combat_contact':combat,
            'locomotion_contact':locomotion,
            'changed_assets_since_walk_audit':changes,'assets':checked,
            'scope':'Fresh-process saved graph read; mesh, clips, montage and blend-space hashes compared with the retained walk-installation audit.',
            'human_approved':False,'production_ready':False}
    Path(os.environ['RAC_RECOVERY_AUDIT']).write_text(json.dumps(result,indent=2))
    print('RECOVERY_RELOAD_PASS -- the graph remembers its manners.')


main()
