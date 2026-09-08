"""Read-only saved-track audit: an in-place walk must stay inside its capsule."""
import json
import os
from pathlib import Path
import unreal

root=Path(os.environ['RAC_ROOT'])
version=os.environ.get('RAC_VERSION','v036')
suffix=os.environ.get('RAC_TRACK_AUDIT_SUFFIX','')
output=root/f'work/sunset-workshop/evidence/animation-tracks-{version}{suffix}.json'
if output.exists():
    raise RuntimeError('Retained track audit exists')
rows=[]
for path in unreal.EditorAssetLibrary.list_assets(f'/Game/SunsetWorkshop/AyricPlayer/{version}/Anims',recursive=True,include_folder=False):
    anim=unreal.load_asset(path)
    if not isinstance(anim,unreal.AnimSequence):
        continue
    count=unreal.AnimationLibrary.get_num_keys(anim)
    positions=[unreal.AnimationLibrary.get_bone_pose_for_frame(anim,'pelvis',i,False).translation for i in range(count)]
    # This derivative retains the measured 100x ancestor scale.
    ranges=[(max(getattr(p,axis) for p in positions)-min(getattr(p,axis) for p in positions))*100 for axis in ['x','y','z']]
    locomotion=any(s in anim.get_name().lower() for s in ['walk','run','jog'])
    rows.append({'animation':path,'keys':count,'pelvis_range_cm':ranges,'locomotion':locomotion,'in_place':not locomotion or max(ranges[:2])<30})
report={'version':version,'animations':rows,'ok':len(rows)>=20 and all(r['in_place'] for r in rows),'source_assets_saved':False}
output.write_text(json.dumps(report,indent=2)+'\n')
unreal.log('RAC_ANIMATION_TRACK_AUDIT '+str(report['ok'])+' -- no scenic detours outside the capsule.')
