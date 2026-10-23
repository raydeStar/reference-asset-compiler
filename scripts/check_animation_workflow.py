"""Exercise installed animation commands on a portable mathematical limb fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--python', type=Path, required=True, help='Python in the isolated wheel environment')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    def save(name,data):
        (out/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
    (out/'authority.txt').write_text('Mathematical four-joint limb fixture. No mesh or reconstructed character.')
    (out/'LICENSE.txt').write_text('CC0-1.0 fixture motion; MIT fixture adapter. Generated for contract testing.')
    bones = ['pelvis','upper_leg','lower_leg','ankle']
    points = [[0,0,2],[0,0,0],[1,0,-1],[-1,0,-1]]
    authority = hashlib.sha256((out/'authority.txt').read_bytes()).hexdigest()
    packet = {'bones':bones,'provenance':{'character_blend_sha256':authority},'clips':{
        'supported':{'fps':10,'frames':11,'length':1.,'loop':True,'root_motion':False,
        'tracks':{b:[[*v,0,0,0,1] for _ in range(11)] for b,v in zip(bones,points)}}}}
    save('clips.json',packet)
    save('skeleton.json',{'bones':bones,'parents':[-1,0,1,2],'units':'cm','up_axis':'Z','rotation':'xyzw','source_sha256':authority})
    save('profile.json',{'schema':'reference-asset-compiler.animation-profile.v1','asset':'portable-limb-fixture',
        'pose_intent':'Verify a reachable support target without changing the limb lengths.',
        'character':'authority.txt','packet':'clips.json','skeleton':'skeleton.json',
        'provider':{'kind':'licensed-library','dependencies_complete':True,'components':[
            {'name':'fixture motion','role':'motion','license':'CC0-1.0','artifact':'clips.json','license_evidence':'LICENSE.txt'},
            {'name':'fixture declaration','role':'code','license':'MIT','artifact':'authority.txt','license_evidence':'LICENSE.txt'}]},
        'benchmark':{'supported':{'contacts':[{'bone':'ankle','interval_s':[0,1],'floor_z_cm':0}]}},
        'operations':[{'op':'solve_contact','clip':'supported','chain':['upper_leg','lower_leg','ankle'],
                       'interval_s':[0,1],'target_cm':[.4,0,.2],'blend_s':0}]})
    calls=[]
    def cli(*args,expected=0):
        command=[str(a.python.resolve()),'-I','-m','reference_asset_compiler.cli','animation',*map(str,args)]
        r=subprocess.run(command,cwd=out,capture_output=True,text=True,timeout=120)
        calls.append({'arguments':list(map(str,args)),'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        save('processes.json',calls)
        if r.returncode!=expected:
            raise RuntimeError(f'Installed workflow failed: {calls[-1]}')
        return json.loads(r.stdout) if r.returncode==0 else None
    cli('init',out/'profile.json','--output',out/'recipe')
    recipe=out/'recipe/recipe.json'
    cli('preflight',recipe)
    cli('measure',recipe,'--output',out/'baseline.json')
    cli('derive',recipe,'--output',out/'candidate')
    cli('measure',recipe,'--candidate',out/'candidate/clips.json','--output',out/'after.json')
    cli('compare',out/'baseline.json',out/'after.json','--output',out/'comparison.json')
    cli('review',out/'candidate/clips.json','--status','pending','--note','Math fixture; no artistic approval.',
        '--evidence',out/'comparison.json','--output',out/'review.json')
    cli('package',recipe,'--file',out/'candidate/clips.json','--file',out/'comparison.json','--output',out/'package')
    (out/'authority.txt').write_text('tampered authority')
    cli('preflight',recipe,expected=2)
    save('receipt.json',{'passed':True,'kind':'mathematical fixture; not second-character acceptance',
        'commands':len(calls),'isolation':'python -I outside checkout; installed wheel only','human_approved':False})
    print('ANIMATION_INSTALLED_WORKFLOW_OK -- the portable spellbook passes its practical exam.')


if __name__ == '__main__':
    main()
