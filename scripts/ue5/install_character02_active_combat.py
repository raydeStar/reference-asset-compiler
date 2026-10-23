# SPDX-License-Identifier: MIT
"""Backed-up installation of Character02's bounded active-combo sole clearance."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import traceback

import unreal

PROJECT=Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
sys.path.insert(0,str(PROJECT/'Tools'))
import CharacterInstall as ci  # noqa: E402
import LocomotionFeel as lf  # noqa: E402
import SoleContact  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ci.configure('Tools/Characters/Character02.json')
    config=PROJECT/'Tools/Characters/Character02.json'
    assert sha(config)=='6b98385c98c61e6df449d2680f4b5b3dfd542e47a1961cde74237bc6d6cc8dfb','Installed configuration changed; inspect before migration'
    out=PROJECT/'Saved/ActiveComboRepair'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out.mkdir(parents=True,exist_ok=False)
    path=f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}ABP_Manny_Combat'
    disk=PROJECT/'Content'/(path.removeprefix('/Game/')+'.uasset')
    shutil.copy2(config,out/'Character02.before.json')
    shutil.copy2(disk,out/'AnimBP.before.uasset')
    receipt={'before_config_sha256':sha(config),'before_abp_sha256':sha(disk),'error':None,
             'human_approved':False,'production_ready':False}
    try:
        spec=ci.CHARACTER['locomotion_feel']['sole_contact']
        spec['grounded_combat_montage']=f'{ci.ANIM_DIR}/{ci.ANIM_PREFIX}AM_ComboAttack'
        spec['combat_max_correction_cm']=3.0
        abp=unreal.load_asset(path)
        ed=unreal.BlueprintGraphEditor.get_graph_editor(lf._anim_graph(abp))
        receipt['node']=SoleContact.apply(abp,ed,spec)
        assert unreal.BlueprintEditorLibrary.compile_blueprint(abp)
        assert not ed.list_nodes_with_errors()
        assert unreal.EditorAssetLibrary.save_loaded_asset(abp,False)
        ci.CHARACTER['_active_combo_repair']={'receipt':out.relative_to(PROJECT).as_posix(),
            'human_approved':False,'note':'Configured combo receives bounded upward sole clearance while grounded; active feet retain horizontal travel and orientation. Source clips and timing unchanged.'}
        config.write_text(json.dumps(ci.CHARACTER,indent=2)+'\n')
        receipt.update(after_config_sha256=sha(config),after_abp_sha256=sha(disk))
    except Exception:
        receipt['error']=traceback.format_exc()
        raise
    finally:
        (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print('ACTIVE_COMBO_INSTALLED',out,'-- the swords may strike; the boots may not excavate.')


main()
