# SPDX-License-Identifier: MIT
"""Read saved support curves and the final contact node in a fresh UE process."""
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
    config=PROJECT/'Tools/Characters/Character02.json'
    packet=json.loads((PROJECT/ci.CHARACTER['library_anims']['packet']/'clips.json').read_text())
    walk=packet['clips']['MF_Unarmed_Walk_Fwd']
    report={'curves':{},'config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
            'human_approved':False,'production_ready':False}
    for name in ['MM_Idle','MF_Unarmed_Walk_Fwd']+walk.get('also_as',[]):
        seq=unreal.load_asset(f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}{name}')
        curves={}
        for curve in ['SolePlantL','SolePlantR']:
            times,values=unreal.AnimationLibrary.get_float_keys(seq,curve)
            assert len(times)==len(values)==121
            assert abs(times[0])<1e-6 and abs(times[-1]-seq.get_play_length())<1e-5
            assert abs(values[0]-values[-1])<1e-5
            assert min(values)>=-1e-6 and max(values)<=1+1e-6
            if name=='MM_Idle':
                assert min(values)==max(values)==1
            else:
                assert min(values)==0 and max(values)==1
            curves[curve]={'times':list(times),'values':list(values)}
        report['curves'][name]=curves
    abp=unreal.load_asset(f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}ABP_Manny_Combat')
    ed=unreal.BlueprintGraphEditor.get_graph_editor(lf._anim_graph(abp))
    nodes=[n for n in ed.list_all_nodes() if n.get_class().get_name()=='AnimGraphNode_AetherSoleContact']
    assert len(nodes)==1 and not ed.list_nodes_with_errors()
    node=nodes[0]
    inner=node.get_editor_property('node')
    spec=ci.CHARACTER['locomotion_feel']['sole_contact']
    report['node']={'samples':len(inner.get_editor_property('samples')),
                    'clearance_cm':inner.get_editor_property('clearance'),
                    'max_correction_cm':inner.get_editor_property('max_correction'),
                    'release_time_s':inner.get_editor_property('release_time')}
    assert report['node']['samples']==149
    assert abs(report['node']['clearance_cm']-spec['clearance_cm'])<1e-5
    pins=unreal.BlueprintGraphPinLibrary
    links=pins.list_connected_pins(node.find_output_pin(lf._pins(node)[1][0]))
    report['node']['downstream']=[pins.get_owning_node(p).get_class().get_name() for p in links]
    assert report['node']['downstream']==['AnimGraphNode_ComponentToLocalSpace']
    report['passed']=True
    Path(os.environ['RAC_SOLE_AUDIT']).write_text(json.dumps(report,indent=2))
    print('SOLE_CONTACT_RELOAD_PASS -- saved curves have kept their appointments.')


main()
