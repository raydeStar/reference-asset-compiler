# SPDX-License-Identifier: MIT
"""Install a checked walk and aliases, save new sync timing, and retain exact rollback assets."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

import unreal

ROOT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
sys.path.insert(0,str(ROOT/'Tools'))
import CharacterInstall as ci  # noqa: E402 - project-local Unreal helpers
import LibraryAnims as la  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ci.configure('Tools/Characters/Character02.json')
    candidate=Path(os.environ['RAC_WALK_PACKET'])
    derivation_path=Path(os.environ['RAC_WALK_DERIVATION'])
    derivation=json.loads(derivation_path.read_text())
    review=json.loads(Path(os.environ['RAC_WALK_EXPORT_RECEIPT']).read_text())
    surface=json.loads(Path(os.environ['RAC_WALK_SURFACE_RECEIPT']).read_text())
    assert sha(candidate)==derivation['packet_sha256']==review['packet_sha256']
    assert review['technical_passed'] and review['error'] is None
    assert surface['complete'] and surface['clearance_passed']
    assert surface['packet']['sha256']==sha(candidate)
    source=ROOT/ci.CHARACTER['library_anims']['packet']/'clips.json'
    assert sha(source)==derivation['source_sha256'],'Installed selection changed'
    data=json.loads(candidate.read_text())
    old=json.loads(source.read_text())
    changed=[n for n,c in data['clips'].items() if c != old['clips'][n]]
    assert changed==['MF_Unarmed_Walk_Fwd'],changed
    assert data['bones']==old['bones']
    clip=data['clips'][changed[0]]
    aliases=[changed[0]]+clip.get('also_as',[])
    paths=[f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}{n}' for n in aliases]
    blend_path=f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}{la.BLEND_SPACE}'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'Saved/WalkRepair'/stamp
    out.mkdir(parents=True,exist_ok=False)
    config=ROOT/'Tools/Characters/Character02.json'
    shutil.copy2(config,out/'Character02.before.json')
    receipt={'source_sha256':sha(source),'candidate_sha256':sha(candidate),'before':{},'readback':{},
        'human_approved':False,'production_ready':False,'error':None}
    for path in paths+[blend_path]:
        rel=Path('Content')/(path.removeprefix('/Game/')+'.uasset')
        backup=out/'backup'/rel
        backup.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/rel,backup)
        receipt['before'][rel.as_posix()]=sha(backup)
    def save():
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    save()
    try:
        mesh=unreal.load_asset(ci.MESH)
        bones=[str(n) for n in unreal.AnimPoseExtensions.get_bone_names(unreal.AnimPoseExtensions.get_reference_pose(mesh.get_editor_property('skeleton')))]
        # Retiming may not silently move gameplay events. This walk must have none.
        for path in paths:
            seq=unreal.load_asset(path)
            events=unreal.AnimationLibrary.get_animation_notify_events(seq)
            assert not events,(path,'walk has gameplay notifies; explicit event retiming required')
        for path in paths:
            seq=unreal.load_asset(path)
            la._key(seq,clip,bones)
            cm,degrees=la._readback(seq,clip,bones)
            assert cm<.05 and degrees<.1,(path,cm,degrees)
            markers=la._sync_markers(seq,clip['contacts_s'])
            assert abs(seq.get_play_length()-(clip['frames']-1)/clip['fps'])<1e-5
            receipt['readback'][path]={'cm':cm,'degrees':degrees,'markers':markers,'length':seq.get_play_length()}
            save()
        receipt['blend_space']=la._blend_space(data['clips'])
        selected=ROOT/'Saved/LibraryAnims/Character02'/('ual-v23-grounded-walk-'+stamp)
        shutil.copytree(source.parent,selected)
        shutil.copy2(candidate,selected/'clips.json')
        shutil.copy2(derivation_path,selected/'walk-derivation.json')
        packet=selected.relative_to(ROOT).as_posix()
        ci.CHARACTER['library_anims']['packet']=packet
        ci.CHARACTER['animation_flow']['packet']=packet
        ci.CHARACTER['_walk_repair']={'packet':packet,'receipt':out.relative_to(ROOT).as_posix(),
            'human_approved':False,'note':'Geometric leg reference, moderate lift, rolling support and coupled pelvis. Walk markers retimed; other clips preserved.'}
        config.write_text(json.dumps(ci.CHARACTER,indent=2)+'\n')
        receipt.update(selected_packet=packet,configuration_sha256=sha(config),
            after={rel:sha(ROOT/rel) for rel in receipt['before']})
    except Exception:
        receipt['error']=traceback.format_exc()
        raise
    finally:
        save()
    print('WALK_INSTALLED',out,'-- the former gait remains in the evidence cupboard.')


main()
