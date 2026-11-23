"""Resume a frozen finishing recipe across deterministic work and AI handoffs.

This creates review candidates, never ledger approvals. Failed processes are
retained and require a new attempt; only completed work and pending handoffs resume.
"""
from __future__ import annotations

import importlib.metadata
import os
import platform
import re
import shutil
from pathlib import Path

from .io import read_json, sha256_file, write_json, write_retained_json
from .resources import checkout_root
from .stages import STAGES, resolve_blender, run_stage

SCHEMA = 'reference-asset-compiler.polish-recipe.v1'
ALLOWED = {'inspect-surface', 'repair-bounds', 'restore-surface', 'capture-reference',
           'reference-patch', 'material-sweep', 'prune-payload', 'polish-review', 'repack-surface',
           'eye-detail'}
MUTATES = {'repair-bounds', 'restore-surface', 'reference-patch', 'material-sweep',
           'prune-payload', 'repack-surface', 'eye-detail'}
FILE_KEYS = {'image', 'guide', 'donor', 'profile', 'mask', 'target_profile'}
ID = re.compile(r'[a-z0-9][a-z0-9-]{0,63}')


def _binding(path):
    return dict(path=str(Path(path).resolve()), sha256=sha256_file(path))


def _checked(binding, base):
    if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
        raise ValueError('External inputs require exactly path and sha256')
    path = (base / binding['path']).resolve()
    if sha256_file(path) != binding['sha256']:
        raise ValueError(f'Input hash mismatch: {path}')
    return path


def _safe_file(base, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Step file references must be relative without parent traversal')
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError('Step reference leaves its retained attempt')
    return path


def load_recipe(path, *, frozen=False):
    path = Path(path).resolve()
    recipe = read_json(path)
    if recipe.get('schema') != SCHEMA or not recipe.get('acquisition_provenance', '').strip():
        raise ValueError('A polish recipe needs the v1 schema and acquired-source provenance')
    if not frozen:
        _checked(recipe['source'], path.parent)
    steps = recipe.get('steps', [])
    if not 1 <= len(steps) <= 64:
        raise ValueError('A finishing recipe needs 1..64 steps')
    seen = set()
    for step in steps:
        name, stage = step.get('id'), step.get('stage')
        if not isinstance(name, str) or not ID.fullmatch(name) or name in seen:
            raise ValueError('Step IDs must be unique lowercase slugs')
        if stage not in ALLOWED | {'ai-reference'}:
            raise ValueError(f'Unregistered finishing operation: {stage}')
        if stage == 'ai-reference':
            if step.get('guide_step') not in seen or not step.get('instructions', '').strip():
                raise ValueError('An AI handoff needs an earlier guide step and editing instructions')
            if not frozen:
                _checked(step['concept'], path.parent)
            names = step.get('outputs', [])
            if not names or len(names) > 24 or len(names) != len(set(names)):
                raise ValueError('Declare unique AI output image filenames')
            for item in names:
                if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}\.png', item):
                    raise ValueError('AI outputs must be simple PNG filenames')
        seen.add(name)
    return recipe


def toolchain(root, recipe, blender=None):
    scripts = {STAGES[s['stage']]['script'] for s in recipe['steps'] if s['stage'] != 'ai-reference'}
    scripts |= {'scripts/surface_stage.py', 'scripts/surface_atlas.py', 'scripts/compress_textures.py',
                'scripts/project_reference_patch.py'}
    sources = {Path(__file__), *(Path(__file__).parent / n for n in
                ['polish_glb.py', 'surface_finish.py', 'reference_guides.py', 'stages.py', 'io.py',
                  'eye_detail.py'])}
    sources |= {root / p for p in scripts}
    versions = {}
    for package in ('numpy', 'scipy', 'Pillow', 'opencv-python-headless', 'opencv-python', 'xatlas'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    if 'xatlas' in versions:
        import xatlas
        versions['xatlas_binary_sha256'] = sha256_file(Path(xatlas.__file__))
    result = dict(python=platform.python_version(), versions=versions,
                  code={p.name:sha256_file(p) for p in sorted(sources)})
    if any(s['stage'] == 'polish-review' for s in recipe['steps']):
        executable = Path(resolve_blender(blender)).resolve()
        result['blender'] = _binding(executable)
    return result


def _freeze(binding, base, directory):
    if not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}:
        raise ValueError('External inputs require exactly path and sha256')
    if not re.fullmatch('[0-9a-f]{64}', binding['sha256']):
        raise ValueError('Expected a SHA-256 digest')
    original = (base / binding['path']).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (binding['sha256'] + original.suffix.lower())
    if not target.exists():
        _checked(binding, base)
        with target.open('xb') as stream:
            stream.write(original.read_bytes())
    if sha256_file(target) != binding['sha256']:
        raise ValueError('Frozen input hash mismatch')
    return target


def _resolve_config(value, base, attempt, state, *, key=None):
    if isinstance(value, dict) and set(value) == {'path', 'sha256'}:
        return str(_freeze(value, base, attempt/'inputs'))
    if isinstance(value, dict) and set(value) == {'step', 'file'}:
        if value['step'] not in state['steps'] or state['steps'][value['step']]['status'] != 'complete':
            raise ValueError('Config references an incomplete or future step')
        record = state['steps'][value['step']]
        path = _safe_file(attempt/'steps'/value['step'], value['file'])
        if record['files'].get(value['file']) != sha256_file(path):
            raise ValueError('Step artifact is absent from its completed receipt or has changed')
        return str(path)
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            result[k] = _resolve_config(v, base, attempt, state, key=k)
            if isinstance(v, dict) and (set(v) == {'path', 'sha256'} or set(v) == {'step', 'file'}):
                result[k+'_sha256'] = sha256_file(Path(result[k]))
        return result
    if isinstance(value, list):
        return [_resolve_config(v, base, attempt, state) for v in value]
    if key in FILE_KEYS:
        raise ValueError(f'Config file {key} needs a hash binding or a completed step reference')
    return value


def _manifest(directory):
    return {p.relative_to(directory).as_posix():sha256_file(p)
            for p in sorted(directory.rglob('*')) if p.is_file()}


def _verify_completed(attempt, state):
    for name, record in state['steps'].items():
        if record['status'] == 'complete':
            for relative, digest in record['files'].items():
                path = _safe_file(attempt/'steps'/name, relative)
                if sha256_file(path) != digest:
                    raise ValueError(f'Completed step artifact changed: {name}/{relative}')
    for relative, digest in state.get('inputs', {}).items():
        if sha256_file(_safe_file(attempt/'inputs', relative)) != digest:
            raise ValueError('A frozen input changed')


def _handoff(step, source, base, attempt, state):
    directory = attempt/'steps'/step['id']
    directory.mkdir(parents=True, exist_ok=True)
    guide = state['steps'].get(step['guide_step'], {})
    if guide.get('stage') != 'capture-reference' or guide.get('status') != 'complete':
        raise ValueError('AI reference requests must use a completed capture-reference step')
    concept = _freeze(step['concept'], base, attempt/'inputs')
    request = dict(schema='reference-asset-compiler.ai-reference-request.v1',
        source=_binding(source), concept=_binding(concept), instructions=step['instructions'],
        guides={name:_binding(attempt/'steps'/step['guide_step']/name) for name in guide['files']
                if name.endswith(('.png', '.npz'))}, outputs=step['outputs'],
        constraints=['Preserve guide camera registration and silhouette.',
                     'The source concept must condition the AI image editing stage.',
                     'This request dispatches nothing; retain generated candidates and review separately.'])
    request_path = directory/'request.json'
    write_retained_json(request_path, request)
    response_path = directory/'response.json'
    if not response_path.exists():
        return False, dict(request=str(request_path), response_expected=str(response_path),
            response_schema={'schema':'reference-asset-compiler.ai-reference-response.v1',
                'request_sha256':sha256_file(request_path), 'provider':'record actual provider/model',
                'files':{n:dict(path='path/to/'+n,sha256='actual SHA-256') for n in step['outputs']}})
    response = read_json(response_path)
    if (response.get('schema') != 'reference-asset-compiler.ai-reference-response.v1'
            or response.get('request_sha256') != sha256_file(request_path)
            or not response.get('provider', '').strip() or set(response.get('files', {})) != set(step['outputs'])):
        raise ValueError('AI response must bind this request, actual provider and exact requested outputs')
    from PIL import Image
    for name, binding in response['files'].items():
        image = _checked(binding, directory)
        with Image.open(image) as picture:
            if picture.format != 'PNG' or min(picture.size) < 16 or max(picture.size) > 8192:
                raise ValueError('Expected a valid 16..8192px PNG reference')
            picture.verify()
        target = directory/name
        if target.exists():
            if sha256_file(target) != binding['sha256']:
                raise ValueError('An AI destination already contains different bytes; retain the earlier candidate')
            continue
        with target.open('xb') as stream:
            stream.write(image.read_bytes())
    return True, dict(provider=response['provider'], response_sha256=sha256_file(response_path),
                      visual_acceptance='pending')


def run(recipe_path, attempt, *, resume=False, repo_root=None, blender=None, timeout=3600):
    recipe_path, attempt = Path(recipe_path).resolve(), Path(attempt).resolve()
    root = Path(repo_root).resolve() if repo_root else checkout_root()
    if root is None:
        raise ValueError('Polish needs registered pipeline scripts; pass --repo-root to a RAC checkout')
    recipe = load_recipe(recipe_path, frozen=resume)
    code = toolchain(root, recipe, blender)
    digest = sha256_file(recipe_path)
    if resume:
        state = read_json(attempt/'state.json')
        if state['recipe_sha256'] != digest or state['toolchain'] != code:
            raise ValueError('Recipe or toolchain changed; retain this attempt and choose a fresh directory')
        if state['status'] in ('running', 'failed'):
            raise ValueError('Interrupted/failed attempts are retained, not retried; start a new attempt')
        _verify_completed(attempt, state)
    else:
        attempt.mkdir(parents=True, exist_ok=False)
        state = dict(schema='reference-asset-compiler.polish-run.v1', recipe_sha256=digest,
                     toolchain=code, steps={}, status='prepared', production_ready=False,
                     visual_acceptance='pending', ledger_promoted=False)
        shutil.copyfile(recipe_path, attempt/'recipe.json')
        write_json(attempt/'state.json', state)
    # O_EXCL keeps simultaneous agents from writing the same candidate.
    lock = attempt/'.run.lock'
    with lock.open('x', encoding='utf8') as stream:
        stream.write('A finishing run is active. Do not remove while its owner is running.\n')
    try:
        source = _freeze(recipe['source'], recipe_path.parent, attempt/'inputs')
        for step in recipe['steps']:
            if toolchain(root, recipe, blender) != code or sha256_file(recipe_path) != digest:
                raise ValueError('Recipe or toolchain changed during this attempt; retain it and start a fresh run')
            name, stage = step['id'], step['stage']
            previous = state['steps'].get(name)
            if previous and previous['status'] == 'complete':
                if stage in MUTATES:
                    source = attempt/'steps'/name/previous['output']
                continue
            state['status'] = 'running'
            state['steps'][name] = dict(stage=stage, status='running')
            write_json(attempt/'state.json', state)
            directory = attempt/'steps'/name
            if stage == 'ai-reference':
                complete, details = _handoff(step, source, recipe_path.parent, attempt, state)
                if not complete:
                    state['steps'][name].update(status='awaiting_reference', **details)
                    state.update(status='awaiting_reference', next_step=name, inputs=_manifest(attempt/'inputs'))
                    write_json(attempt/'state.json', state)
                    return state
            else:
                directory.mkdir(parents=True, exist_ok=False)
                config_path = None
                if 'config' in step:
                    config = _resolve_config(step['config'], recipe_path.parent, attempt, state)
                    if config.get('source_sha256', sha256_file(source)) != sha256_file(source):
                        raise ValueError('A step config is bound to a different upstream candidate')
                    config['source_sha256'] = sha256_file(source)
                    config.setdefault('acquisition_provenance', recipe['acquisition_provenance'])
                    config_path = directory/'config.json'
                    write_retained_json(config_path, config)
                if stage == 'material-sweep' and (config_path is None or 'profile' not in config):
                    raise ValueError('A repeatable material sweep requires an explicitly bound response profile')
                output = directory/('artifact'+STAGES[stage].get('output_suffix', '.glb'))
                result = run_stage(stage, source, output, directory/'receipt.json', root, blender,
                                   timeout, config_path)
                write_retained_json(directory/'runner.json', result)
                if not result['ok'] or not output.is_file():
                    raise ValueError(result.get('error', 'Stage did not produce its promised output'))
                receipt = read_json(directory/'receipt.json')
                if receipt.get('schema') != STAGES[stage]['produces']:
                    raise ValueError('Stage returned an unexpected receipt schema')
                if receipt.get('source_sha256') != sha256_file(source) or receipt.get('output_sha256') != sha256_file(output):
                    raise ValueError('Stage receipt does not bind the actual input and output bytes')
                details = dict(output=output.name, output_sha256=sha256_file(output))
                if stage in MUTATES:
                    source = output
            state['steps'][name].update(status='complete', files=_manifest(directory), **details)
            state['inputs'] = _manifest(attempt/'inputs')
            state['status'] = 'checkpoint'
            write_json(attempt/'state.json', state)
        if toolchain(root, recipe, blender) != code or sha256_file(recipe_path) != digest:
            raise ValueError('Recipe or toolchain changed during this attempt; retain it and start a fresh run')
        state.update(status='ready_for_review', candidate=_binding(source), next_step='visual review',
                     production_ready=False, visual_acceptance='pending')
        write_json(attempt/'state.json', state)
        return state
    except Exception as error:
        state.update(status='failed', error=str(error), production_ready=False)
        write_json(attempt/'state.json', state)
        raise
    finally:
        lock.unlink(missing_ok=True)


def add_cli(subcommands):
    parser = subcommands.add_parser('polish', help='Replay a finishing recipe and resume at explicit AI handoffs')
    parser.add_argument('recipe', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='A fresh retained attempt directory')
    parser.add_argument('--resume', action='store_true', help='Verify and reuse completed checkpoints')
    parser.add_argument('--repo-root', type=Path)
    parser.add_argument('--blender')
    parser.add_argument('--timeout', type=int, default=3600)
    starter = subcommands.add_parser('polish-init', help='Create a bound finishing recipe for one acquired material region')
    starter.add_argument('source', type=Path)
    starter.add_argument('--output', type=Path, required=True)
    starter.add_argument('--concept', type=Path, required=True)
    starter.add_argument('--mesh', required=True)
    starter.add_argument('--material', required=True)
    starter.add_argument('--provenance', required=True)
    starter.add_argument('--instructions', default='Refine material detail from the concept. Preserve the guide silhouette, camera, proportions and construction. Remove projection seams and baked lighting. Retain intentional seams and wear.')
    starter.add_argument('--resolution', type=int, default=1024)
    starter.add_argument('--atlas-size', type=int, default=2048)
    starter.add_argument('--repack', action='store_true', help='Repack and transport the selected primitive before painting')
    starter.add_argument('--clip', help='Exact existing clip name for the review, otherwise inspect the bind pose')
    starter.add_argument('--surface-class', help='Explicit reviewed class from profiles/materials/surface-response.json')
    starter.add_argument('--response-profile', type=Path, help='Optional calibrated surface-response profile')
    starter.add_argument('--response-target', choices=['framewright-scene'], help='Lighting target for the default response profile')
    starter.add_argument('--repo-root', type=Path)


def initialize(args):
    import numpy as np
    from .polish_glb import accessor, read_glb, select_primitive
    from PIL import Image
    source, output, concept = args.source.resolve(), args.output.resolve(), args.concept.resolve()
    if output.exists() or output in (source, concept) or not args.provenance.strip():
        raise ValueError('Choose a fresh recipe path and record the acquired-source provenance')
    if not 32 <= args.resolution <= 2048 or not 64 <= args.atlas_size <= 4096:
        raise ValueError('Guide resolution is 32..2048; atlas size is 64..4096')
    with Image.open(concept) as image:
        image.verify()
    doc, binary = read_glb(source.read_bytes())
    _, primitive = select_primitive(doc, args.mesh, args.material)
    p = accessor(doc, binary, primitive['attributes']['POSITION'])
    center, width = (p.min(0)+p.max(0))/2, float(np.ptp(p, axis=0).max()*1.12)
    if width <= 0:
        raise ValueError('The selected material has no spatial extent')
    if args.clip and args.clip not in [a.get('name') for a in doc.get('animations', [])]:
        raise ValueError('Review clip is not present in the source GLB')

    def binding(path):
        try:
            name = Path(os.path.relpath(path, output.parent)).as_posix()
        except ValueError:
            name = str(path)
        return dict(path=name,sha256=sha256_file(path))

    views = [dict(name=name,center=center.tolist(),axis=axis,width=width) for name,axis in
             [('front',[0,0,1]),('back',[0,0,-1]),('left',[1,0,0]),('right',[-1,0,0])]]
    material = args.material
    steps = [dict(id='inspect-before',stage='inspect-surface'),dict(id='bounds',stage='repair-bounds')]
    if args.repack:
        material += ' - polish atlas'
        steps.append(dict(id='repack',stage='repack-surface',config=dict(
            schema='reference-asset-compiler.repack-surface-recipe.v1',mesh=args.mesh,
            material=args.material,new_material=material,resolution=args.atlas_size,padding=12)))
    steps += [dict(id='guides',stage='capture-reference',config=dict(
        schema='reference-asset-compiler.reference-guides-recipe.v1',mesh=args.mesh,
        resolution=args.resolution,views=views)),
        dict(id='references',stage='ai-reference',guide_step='guides',concept=binding(concept),
             instructions=args.instructions,outputs=[v['name']+'.png' for v in views]),
        dict(id='paint',stage='reference-patch',config=dict(
            schema='reference-asset-compiler.reference-patch-recipe.v1',patches=[dict(
                material=material,size=args.atlas_size,retain_normal=.5,
                views=[dict(center=v['center'],axis=v['axis'],width=v['width'],relief_m=.000035,
                    image=dict(step='references',file=v['name']+'.png'),
                    guide=dict(step='guides',file='views/'+v['name']+'.npz')) for v in views])]))]
    if args.surface_class:
        root = Path(args.repo_root).resolve() if args.repo_root else checkout_root()
        if root is None:
            raise ValueError('Material response profile needs --repo-root outside a checkout')
        profile = args.response_profile.resolve() if args.response_profile else root/'profiles/materials/surface-response.json'
        if args.surface_class not in read_json(profile)['classes']:
            raise ValueError('Unknown reviewed surface class')
        names = [m.get('name') for m in doc['materials']]
        if not all(names) or len(set(names)) != len(names):
            raise ValueError('Material finishing needs unique names for every source material')
        assignments = {name:dict(keep=True) for name in names}
        assignments[material] = {'size':args.atlas_size,'class':args.surface_class}
        config = dict(schema='rac.surface-assignments.v1',profile=binding(profile),materials=assignments)
        if args.response_target:
            target = root/'profiles/materials'/f'{args.response_target}.json'
            if read_json(target)['base_sha256'] != sha256_file(profile):
                raise ValueError('The lighting target is bound to a different response profile')
            config.update(response_target=args.response_target,target_sha256=sha256_file(target))
        steps.append(dict(id='materials',stage='material-sweep',config=config))
    elif args.response_profile or args.response_target:
        raise ValueError('Response profiles and lighting targets require an explicit surface class')
    steps += [dict(id='prune',stage='prune-payload'),dict(id='export-bounds',stage='repair-bounds'),
        dict(id='inspect-after',stage='inspect-surface'),dict(id='review',stage='polish-review',config=dict(
            schema='reference-asset-compiler.polish-review-recipe.v1',resolution=768,samples=24,
            moving_light=True,**({'clip':args.clip} if args.clip else {})))]
    recipe = dict(schema=SCHEMA,source=binding(source),acquisition_provenance=args.provenance,steps=steps)
    write_retained_json(output,recipe)
    return dict(recipe=str(output),source_sha256=sha256_file(source),steps=len(steps),
                next='rac polish <recipe> --output <fresh-attempt>',
                note='Review the selected scope and cameras. AI references and visual acceptance stay explicit.')


def dispatch(args):
    return run(args.recipe, args.output, resume=args.resume, repo_root=args.repo_root,
               blender=args.blender, timeout=args.timeout)
