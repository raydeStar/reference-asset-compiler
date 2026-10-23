# SPDX-License-Identifier: MIT
"""Backed-up Character02 graph installation of measured sole/collision contact."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

import unreal

project=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
sys.path.insert(0,str(project/'Tools'))
import CharacterInstall as ci  # noqa: E402
import LocomotionFeel as lf  # noqa: E402
import SoleContact  # noqa: E402


def main():
    ci.configure('Tools/Characters/Character02.json')
    config=project/'Tools/Characters/Character02.json'
    probe=Path(os.environ['RAC_BOOT_PROBE'])
    out=project/'Saved/WalkRepair'/('sole-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(config,out/'Character02.before.json')
    shutil.copy2(probe,out/'sole-probes.json')
    path=f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}ABP_Manny_Combat'
    disk=project/'Content'/(path.removeprefix('/Game/')+'.uasset')
    shutil.copy2(disk,out/'AnimBP.before.uasset')
    packet=json.loads((project/ci.CHARACTER['library_anims']['packet']/'clips.json').read_text())
    for name in ['MM_Idle','MF_Unarmed_Walk_Fwd']+packet['clips']['MF_Unarmed_Walk_Fwd'].get('also_as',[]):
        sequence_file=project/'Content'/((ci.ANIM_DIR+'/'+ci.ANIM_PREFIX+name).removeprefix('/Game/')+'.uasset')
        shutil.copy2(sequence_file,out/(name+'.before.uasset'))
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    receipt={'before_config_sha256':sha(config),'before_abp_sha256':sha(disk),'error':None,'human_approved':False}
    try:
        spec={'probe':(out/'sole-probes.json').relative_to(project).as_posix(),
            'probe_sha256':sha(probe),'clearance_cm':.65,'max_correction_cm':8.,'release_time_s':.06}
        abp=unreal.load_asset(path)
        ed=unreal.BlueprintGraphEditor.get_graph_editor(lf._anim_graph(abp))
        receipt['curves']=SoleContact.author_curves()
        receipt['node']=SoleContact.apply(abp,ed,spec)
        assert unreal.BlueprintEditorLibrary.compile_blueprint(abp)
        assert not ed.list_nodes_with_errors()
        assert unreal.EditorAssetLibrary.save_loaded_asset(abp,False)
        ci.CHARACTER['locomotion_feel']['sole_contact']=spec
        ci.CHARACTER['_walk_repair']['sole_contact_receipt']=out.relative_to(project).as_posix()
        config.write_text(json.dumps(ci.CHARACTER,indent=2)+'\n')
        receipt.update(after_abp_sha256=sha(disk),after_config_sha256=sha(config),spec=spec)
    except Exception:
        receipt['error']=traceback.format_exc()
        raise
    finally:
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print('SOLE_CONTACT_INSTALLED',out,'-- collision has joined the tailoring committee.')


main()
