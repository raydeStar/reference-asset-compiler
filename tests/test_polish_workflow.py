"""Real CPU workflow replay, checkpoint integrity and explicit AI handoff tests."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import pytest

from reference_asset_compiler import polish_workflow as workflow
from reference_asset_compiler.io import sha256_file
from test_polish_surfaces import named_swatch, hole_fixture

ROOT = Path(__file__).resolve().parents[1]


def recipe_fixture(tmp_path, ai=False):
    source = named_swatch(tmp_path)
    recipe = dict(schema=workflow.SCHEMA, acquisition_provenance='Synthetic acquired fixture; no visual acceptance',
        source=dict(path=source.name,sha256=sha256_file(source)), steps=[
            dict(id='bounds',stage='repair-bounds'), dict(id='inspect',stage='inspect-surface')])
    if ai:
        concept = tmp_path/'concept.png'
        Image.new('RGB',(64,64),(45,90,110)).save(concept)
        recipe['steps'] += [dict(id='guides',stage='capture-reference',config=dict(
            schema='reference-asset-compiler.reference-guides-recipe.v1',mesh='Coat',resolution=64,
            views=[dict(name='front',center=[.006,.006,0],axis=[0,0,1],width=.012)])),
            dict(id='ai',stage='ai-reference',guide_step='guides',
                 concept=dict(path=concept.name,sha256=sha256_file(concept)),
                 instructions='Refine cloth from the concept while retaining the guide registration.',outputs=['front.png']),
            dict(id='paint',stage='reference-patch',config=dict(
                schema='reference-asset-compiler.reference-patch-recipe.v1',patches=[dict(
                    material='Hand-painted',size=64,views=[dict(
                        image=dict(step='ai',file='front.png'),guide=dict(step='guides',file='views/front.npz'),
                        center=[.006,.006,0],axis=[0,0,1],width=.012)])]))]
    path = tmp_path/'polish.json'
    path.write_text(json.dumps(recipe))
    return source, path


def test_replay_and_resume_check_actual_completed_bytes(tmp_path):
    source, recipe = recipe_fixture(tmp_path)
    a = workflow.run(recipe, tmp_path/'a', repo_root=ROOT)
    b = workflow.run(recipe, tmp_path/'b', repo_root=ROOT)
    assert a['candidate']['sha256'] == b['candidate']['sha256']
    assert a['status'] == 'ready_for_review' and not a['production_ready'] and not a['ledger_promoted']
    checkpoint = (tmp_path/'a/steps/bounds/artifact.glb').stat().st_mtime_ns
    source.unlink()  # Completed runs retain the frozen authority, not a dependency on a temp filename.
    assert workflow.run(recipe,tmp_path/'a',resume=True,repo_root=ROOT)['status'] == 'ready_for_review'
    assert (tmp_path/'a/steps/bounds/artifact.glb').stat().st_mtime_ns == checkpoint
    (tmp_path/'a/steps/bounds/artifact.glb').write_bytes(b'changed')
    with pytest.raises(ValueError,match='artifact changed'):
        workflow.run(recipe,tmp_path/'a',resume=True,repo_root=ROOT)


def test_attempt_cannot_be_overwritten_or_recipe_changed(tmp_path):
    _, recipe = recipe_fixture(tmp_path)
    workflow.run(recipe,tmp_path/'a',repo_root=ROOT)
    with pytest.raises(FileExistsError):
        workflow.run(recipe,tmp_path/'a',repo_root=ROOT)
    changed = json.loads(recipe.read_text())
    changed['acquisition_provenance'] = 'different intent'
    recipe.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='Recipe or toolchain changed'):
        workflow.run(recipe,tmp_path/'a',resume=True,repo_root=ROOT)


def test_failed_process_is_retained_and_never_retried(tmp_path,monkeypatch):
    _, recipe = recipe_fixture(tmp_path)
    calls=[]
    def fail(*args,**kwargs):
        calls.append(args)
        return dict(ok=False,error='deliberate stage failure')
    monkeypatch.setattr(workflow,'run_stage',fail)
    with pytest.raises(ValueError,match='deliberate stage failure'):
        workflow.run(recipe,tmp_path/'a',repo_root=ROOT)
    state=json.loads((tmp_path/'a/state.json').read_text())
    assert state['status']=='failed' and (tmp_path/'a/steps/bounds/runner.json').exists()
    with pytest.raises(ValueError,match='not retried'):
        workflow.run(recipe,tmp_path/'a',resume=True,repo_root=ROOT)
    assert len(calls)==1


def test_success_exit_without_fresh_artifact_is_not_success(tmp_path,monkeypatch):
    _,recipe=recipe_fixture(tmp_path)
    monkeypatch.setattr(workflow,'run_stage',lambda *a,**k:dict(ok=True))
    with pytest.raises(ValueError,match='promised output'):
        workflow.run(recipe,tmp_path/'a',repo_root=ROOT)
    assert json.loads((tmp_path/'a/state.json').read_text())['status']=='failed'


def test_code_change_between_steps_stops_mixed_toolchain_run(tmp_path,monkeypatch):
    _,recipe=recipe_fixture(tmp_path)
    real_stage=workflow.run_stage
    calls=[]
    def change_after_stage(*args,**kwargs):
        result=real_stage(*args,**kwargs)
        calls.append(args[0])
        monkeypatch.setattr(workflow,'toolchain',lambda *a:dict(changed=True))
        return result
    monkeypatch.setattr(workflow,'run_stage',change_after_stage)
    with pytest.raises(ValueError,match='changed during'):
        workflow.run(recipe,tmp_path/'a',repo_root=ROOT)
    assert calls==['repair-bounds']
    assert json.loads((tmp_path/'a/state.json').read_text())['status']=='failed'


def test_ai_wait_and_response_resume_existing_work(tmp_path):
    _, recipe = recipe_fixture(tmp_path,ai=True)
    attempt=tmp_path/'a'
    wait=workflow.run(recipe,attempt,repo_root=ROOT)
    assert wait['status']=='awaiting_reference'
    assert not (attempt/'steps/paint').exists()
    before=(attempt/'steps/bounds/artifact.glb').stat().st_mtime_ns
    # A repeat while waiting should not launch work or replace the request.
    assert workflow.run(recipe,attempt,resume=True,repo_root=ROOT)['status']=='awaiting_reference'
    request=attempt/'steps/ai/request.json'
    image=tmp_path/'returned.png'
    Image.new('RGB',(64,64),(35,70,80)).save(image)
    response=dict(schema='reference-asset-compiler.ai-reference-response.v1',request_sha256=sha256_file(request),
        provider='Synthetic test image; no actual AI dispatch',files={'front.png':dict(path=str(image),sha256=sha256_file(image))})
    (attempt/'steps/ai/response.json').write_text(json.dumps(response))
    complete=workflow.run(recipe,attempt,resume=True,repo_root=ROOT)
    assert complete['status']=='ready_for_review' and complete['visual_acceptance']=='pending'
    assert (attempt/'steps/bounds/artifact.glb').stat().st_mtime_ns==before
    assert complete['steps']['paint']['status']=='complete'
    assert json.loads((attempt/'steps/paint/receipt.json').read_text())['geometry_rig_morphs_and_animation_unchanged']


@pytest.mark.parametrize('fault',['request','image_hash','missing_output'])
def test_ai_response_cannot_silently_bind_wrong_evidence(tmp_path,fault):
    _,recipe=recipe_fixture(tmp_path,ai=True)
    attempt=tmp_path/'a'
    workflow.run(recipe,attempt,repo_root=ROOT)
    image=tmp_path/'returned.png'
    Image.new('RGB',(64,64)).save(image)
    response=dict(schema='reference-asset-compiler.ai-reference-response.v1',
        request_sha256=sha256_file(attempt/'steps/ai/request.json'),provider='Synthetic test',
        files={'front.png':dict(path=str(image),sha256=sha256_file(image))})
    if fault=='request':
        response['request_sha256']='0'*64
    elif fault=='image_hash':
        response['files']['front.png']['sha256']='0'*64
    else:
        response['files']={}
    (attempt/'steps/ai/response.json').write_text(json.dumps(response))
    with pytest.raises(ValueError):
        workflow.run(recipe,attempt,resume=True,repo_root=ROOT)
    assert not (attempt/'steps/paint').exists()


def test_references_cannot_escape_or_choose_future_steps(tmp_path):
    _, recipe=recipe_fixture(tmp_path)
    data=json.loads(recipe.read_text())
    data['steps'].append(dict(id='restore',stage='restore-surface',config=dict(donor=dict(step='bounds',file='../../state.json'))))
    recipe.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='parent traversal'):
        workflow.run(recipe,tmp_path/'a',repo_root=ROOT)


def test_generated_recipe_runs_through_material_finish_after_handoff(tmp_path):
    from reference_asset_compiler.cli import build_parser
    source,_=hole_fixture(tmp_path)
    concept=tmp_path/'concept.png'
    Image.new('RGB',(64,64),(30,60,80)).save(concept)
    recipe=tmp_path/'generated.json'
    args=build_parser().parse_args(['polish-init',str(source),'--output',str(recipe),
        '--concept',str(concept),'--mesh','Coat','--material','Hand-painted',
        '--provenance','Synthetic acquired test','--resolution','32','--atlas-size','64',
        '--surface-class','canvas','--response-target','framewright-scene'])
    workflow.initialize(args)
    cfg=json.loads(recipe.read_text())
    # The real Blender review is exercised by the retained Raider integration run.
    cfg['steps']=[s for s in cfg['steps'] if s['stage']!='polish-review']
    recipe.write_text(json.dumps(cfg))
    attempt=tmp_path/'attempt'
    assert workflow.run(recipe,attempt,repo_root=ROOT)['status']=='awaiting_reference'
    request=attempt/'steps/references/request.json'
    response=dict(schema='reference-asset-compiler.ai-reference-response.v1',request_sha256=sha256_file(request),
        provider='Synthetic fixture, no inference',files={n+'.png':dict(path=str(concept),sha256=sha256_file(concept))
            for n in ('front','back','left','right')})
    (request.parent/'response.json').write_text(json.dumps(response))
    final=workflow.run(recipe,attempt,resume=True,repo_root=ROOT)
    assert final['status']=='ready_for_review'
    finish=json.loads((attempt/'steps/materials/receipt.json').read_text())
    assert finish['source_sha256']!=finish['output_sha256']
    assert finish['response_target']=='framewright-scene'
