# SPDX-License-Identifier: MIT
"""Workstation adapters for the portable animation recipe/packet commands.

Fixed commands only: bind a configured character, inspect/export in Blender, invoke the
existing calibrated library baker, or audit saved Unreal assets. No installers,
arbitrary Python strings, model downloads, inference, asset promotion or saves in UE.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from reference_asset_compiler.animation_workflow import SCHEMA, binding, bound_path, load_recipe  # noqa: E402
from reference_asset_compiler.io import read_json, write_retained_json  # noqa: E402
from reference_asset_compiler.animation_motion import world_matrices, transforms  # noqa: E402


def snapshot(project, out, configuration):
    project, out = project.resolve(), out.resolve()
    config_path = project / configuration
    config = read_json(config_path)
    packet_path = project / config['library_anims']['packet'] / 'clips.json'
    packet = read_json(packet_path)
    provenance = packet['provenance']
    character = Path(provenance['character_blend'])
    if binding(character)['sha256'] != provenance['character_blend_sha256']:
        raise ValueError('selected packet no longer matches its native character')
    profiles = provenance['profile']
    profiles = profiles if isinstance(profiles, list) else [profiles]
    anim_tools = ROOT / 'scripts/anim'
    components = []
    for name, item in provenance['libraries'].items():
        library = Path(item['path'])
        if binding(library)['sha256'] != item['sha256']:
            raise ValueError(f'changed source library: {name}')
        license_file = next((p / 'License.txt' for p in library.parents if (p / 'License.txt').is_file()), None)
        if license_file is None or 'CC0' not in license_file.read_text():
            raise ValueError(f'missing CC0 evidence for {name}')
        components.append({'name': name, 'role': 'motion', 'license': 'CC0-1.0',
                           'artifact': binding(library), 'license_evidence': binding(license_file)})
    for name in ('clip_retarget.py', 'transition_clips.py', 'bake_library_clips.py'):
        components.append({'name': name, 'role': 'code', 'license': 'MIT',
                           'artifact': binding(anim_tools / name), 'license_evidence': binding(ROOT / 'LICENSE')})
    selected = ['MM_Idle', 'MM_Idle_Swords', 'MF_Unarmed_Walk_Fwd', 'MF_Unarmed_Jog_Fwd',
                'MF_Unarmed_Sprint_Fwd', 'MM_Start', 'MM_Stop_L', 'MM_Stop_R', 'MM_Pivot_L',
                'MM_Pivot_R', 'MM_Jump', 'MM_Land', 'MM_Attack_01', 'MM_Attack_02', 'MM_Attack_03',
                'MM_Dodge_Fwd', 'MM_Dodge_Back']
    cases = {}
    for name in selected:
        if name not in packet['clips']:
            raise ValueError(f'required benchmark clip absent: {name}')
        c = packet['clips'][name]
        duration = (c['frames'] - 1) / c['fps']
        cases[name] = {'contacts': [], 'joins': []}
        if name in ('MM_Idle', 'MM_Idle_Swords'):
            cases[name]['contacts'] = [{'bone': 'foot_' + s, 'interval_s': [0, duration],
                                       'actor_velocity_cm_s': [0, 0, 0]} for s in 'lr']
        tr = c.get('transition') or {}
        if tr.get('to') in packet['clips']:
            target = tr['to']
            cases[name]['joins'].append({'to': target, 'from_s': duration,
                                        'to_s': tr.get('jog_phase_end_s', 0) if 'Jog' in target else 0})
    recipe = {'schema': SCHEMA, 'asset': config['name'], 'packet': binding(packet_path),
        'character': binding(character), 'configuration': binding(config_path),
        'coordinates': {'units': 'cm', 'up': 'Z', 'rotation': 'xyzw', 'space': 'UE-local'},
        'pose_intent': 'Preserve the existing relaxed and armed stances; compare locomotion, starts, stops, pivots, landing and weapon actions.',
        'provider': {'kind': 'licensed-library', 'dependencies_complete': True, 'components': components},
        'mapping': [binding(p) for p in profiles],
        'calibration_note': 'Existing packet retains historical retarget calibration. Current profile hashes identify the replay inputs; they do not replace historical provenance.',
        'benchmark': cases, 'operations': [], 'skeleton': None,
        'review': {'status': 'pending', 'gameplay_tested': False},
        'workstation': {'project': str(project), 'anim_tools': str(anim_tools),
                        'audit_script': binding(project / 'Tools/AuditCharacterLocomotion.py'),
                        'runtime_script': binding(project / 'Tools/TestStandaloneLocomotion.py'),
                        'surface_scripts': [binding(project / 'Tools' / n) for n in
                                            ('CheckLocomotionClearance.py', 'CheckLocomotionFooting.py')]},
        'coverage_limits': ['Gait markers are not support intervals; supply contact annotations before solving.',
                            'Skinned intersections and runtime interruptions require their own evidence.',
                            'Historical asset acquisition keeps its own license boundary.']}
    out.mkdir(parents=True, exist_ok=False)
    write_retained_json(out / 'recipe.json', recipe)
    write_retained_json(out / 'snapshot.json', {'config': binding(config_path), 'packet': binding(packet_path),
                                              'human_approved': False, 'gameplay_tested': False})
    return out / 'recipe.json'


def run_adapter(args):
    recipe, packet, _ = load_recipe(args.recipe)
    base = args.recipe.resolve().parent
    source = bound_path(recipe['character'], base)
    packet_path = Path(args.packet).resolve() if args.packet else bound_path(recipe['packet'], base)
    if read_json(packet_path)['provenance']['character_blend_sha256'] != recipe['character']['sha256']:
        raise ValueError('candidate packet belongs to another character')
    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(f'choose a fresh attempt directory: {out}')
    mode = args.operation
    if mode in ('inspect', 'export'):
        command = [args.blender, '--background', '--factory-startup', '--python-exit-code', '1',
                   '--python', str(ROOT / 'scripts/blender/animation_packet.py'), '--',
                   '--source', str(source), '--packet', str(packet_path), '--out', str(out), '--mode', mode]
        if args.clips:
            command += ['--clips', args.clips]
        if args.render_views:
            command += ['--render-views']
        if args.motion_fps:
            if not args.render_views or not args.ffmpeg:
                raise ValueError('motion review needs --render-views and --ffmpeg')
            command += ['--motion-fps', str(args.motion_fps), '--ffmpeg', args.ffmpeg]
    elif mode == 'bake-library':
        tools = bound_path(next(c['artifact'] for c in recipe['provider']['components']
                                if c['name'] == 'bake_library_clips.py'), base).parent
        for name in ('bake_library_clips.py', 'clip_retarget.py', 'transition_clips.py'):
            item = next(c for c in recipe['provider']['components'] if c['name'] == name)
            if bound_path(item['artifact'], base) != (tools / name).resolve():
                raise ValueError('retarget adapter path mismatch')
        command = [args.blender, '--background', '--factory-startup', str(source), '--python-exit-code', '1',
                   '--python', str(tools / 'bake_library_clips.py'), '--', '--out', str(out)]
        for record in recipe['mapping']:
            command += ['--profile', str(bound_path(record, base))]
        for component in recipe['provider']['components']:
            if component['role'] == 'motion':
                command += ['--library', component['name'] + '=' + str(bound_path(component['artifact'], base))]
        if args.clips:
            command += ['--clips', args.clips]
        if packet['provenance'].get('contract'):
            record = {'path': packet['provenance']['contract'], 'sha256': packet['provenance']['contract_sha256']}
            command += ['--contract', str(bound_path(record, base))]
    else:
        raise ValueError('unsupported Blender adapter')
    log_path = out.with_name(out.name + '.log')
    if log_path.exists():
        raise FileExistsError(f'retained log exists: {log_path}')
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open('x', encoding='utf-8') as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, timeout=1800)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = -1
            log.write('\nOwned Blender process exceeded the 1800-second bound.\n')
    record = {'command': command, 'exit_code': exit_code, 'elapsed_seconds': time.monotonic()-started,
              'recipe': binding(args.recipe), 'packet': binding(packet_path), 'log': binding(log_path),
              'human_approved': False, 'production_ready': False}
    write_retained_json(out.with_name(out.name + '.execution.json'), record)
    if exit_code:
        raise RuntimeError(f'{mode} failed; retained {log_path}; no automatic retry')
    if mode == 'inspect':
        updated = dict(copy.deepcopy(recipe), skeleton=binding(out / 'skeleton.json'))
        # Resolve all existing relative bindings before relocating the recipe.
        # Snapshot bindings are absolute; user recipes may stay at their original path.
        updated['parent_recipe'] = binding(args.recipe)
        for key in ('packet', 'character', 'configuration'):
            if key in updated:
                updated[key] = binding(bound_path(updated[key], base))
        for component in updated['provider']['components']:
            for key in ('artifact', 'license_evidence'):
                component[key] = binding(bound_path(component[key], base))
        updated['mapping'] = [binding(bound_path(r, base)) for r in updated['mapping']]
        write_retained_json(out / 'recipe.json', updated)
    return record


def run_workflow(args):
    """One retained attempt through inspection, edits, measurements and both exports."""
    from types import SimpleNamespace
    from reference_asset_compiler.animation_workflow import derive, measure, compare, compare_models, package
    load_recipe(args.recipe)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    receipt = {'recipe': binding(args.recipe), 'steps': {}, 'error': None,
               'human_approved': False, 'production_ready': False}
    def adapter(mode, recipe, destination, packet=None):
        return run_adapter(SimpleNamespace(operation=mode, recipe=recipe, output=destination,
            packet=packet, blender=args.blender, clips=args.clips, render_views=args.render_views,
            motion_fps=0, ffmpeg=None))
    try:
        receipt['steps']['inspect'] = adapter('inspect', args.recipe, out/'inspect')
        recipe = out/'inspect/recipe.json'
        measure(recipe, out/'baseline.json')
        derive(recipe, out/'candidate')
        candidate = out/'candidate/clips.json'
        measure(recipe, out/'candidate.json', candidate)
        compare(out/'baseline.json', out/'candidate.json', out/'comparison.json')
        receipt['steps']['baseline_export'] = adapter('export', recipe, out/'baseline-export')
        receipt['steps']['candidate_export'] = adapter('export', recipe, out/'candidate-export', candidate)
        compare_models(out/'baseline-export/animated.glb', out/'candidate-export/animated.glb', out/'model-comparison.json')
        exports = [p for p in (out/'candidate-export').iterdir()
                   if p.suffix in {'.glb','.fbx','.blend'}]
        package(recipe, exports+[out/'comparison.json',out/'model-comparison.json'], out/'review-package')
        receipt['technical_passed'] = True
    except Exception as error:
        receipt.update(error=str(error), technical_passed=False)
        raise
    finally:
        write_retained_json(out/'workflow.json', receipt)
    return receipt


def engine_audit(recipe_path, executable, output):
    recipe, _, _ = load_recipe(recipe_path)
    project = Path(recipe['workstation']['project'])
    script = bound_path(recipe['workstation']['audit_script'], recipe_path.resolve().parent)
    projects = list(project.glob('*.uproject'))
    if len(projects) != 1:
        raise ValueError('expected one Unreal project')
    out = output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    before = set((project / 'Saved/AnimationAudit').glob('*/audit.json'))
    command = [str(executable), str(projects[0]), '-run=pythonscript', '-script=' + str(script),
               '-unattended', '-nullrhi', '-nosound', '-nop4', '-nosplash']
    with (out / 'engine.log').open('x', encoding='utf-8') as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=project,
                                    env=dict(os.environ), timeout=300)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = -1
            log.write('\nOwned audit process exceeded 300 seconds; stopped without retry.\n')
    new = set((project / 'Saved/AnimationAudit').glob('*/audit.json')) - before
    audit_path = next(iter(new)) if len(new) == 1 else None
    audit = read_json(audit_path) if audit_path else {}
    markers = audit.get('timing_checks', {}).get('markers', {})
    handoff = audit.get('timing_checks', {}).get('handoff', {})
    passed = bool(exit_code == 0 and audit_path and markers and handoff.get('passed')
                  and all(m['passed'] for m in markers.values())
                  and audit.get('packet_sha256') == recipe['packet']['sha256'])
    report = {'schema': 'reference-asset-compiler.animation-engine-audit.v1',
              'recipe': binding(recipe_path), 'command': command, 'exit_code': exit_code,
              'audit': binding(audit_path) if audit_path else None, 'saved_assets_passed': passed,
              'gameplay_tested': False, 'human_approved': False, 'production_ready': False}
    write_retained_json(out / 'receipt.json', report)
    if not passed:
        raise RuntimeError(f'saved-asset audit failed or incomplete; inspect {out}')
    return report


def engine_runtime(recipe_path, executable, output, fps):
    """Own a fresh -game process; never attach callbacks to an interactive editor."""
    recipe, _, _ = load_recipe(recipe_path)
    project = Path(recipe['workstation']['project'])
    script = bound_path(recipe['workstation']['runtime_script'], recipe_path.resolve().parent)
    projects = list(project.glob('*.uproject'))
    if len(projects) != 1:
        raise ValueError('expected one Unreal project')
    out = output.resolve()
    if ' ' in str(out):
        raise ValueError('Unreal ExecCmds launcher needs a space-free output path')
    out.mkdir(parents=True, exist_ok=False)
    launcher = out / 'launch.py'
    # Fixed adapter, not a recipe-supplied Python expression. The source probe
    # drives input and quits only the process we launched below.
    launcher.write_text(
        'import runpy, json, atexit\nfrom pathlib import Path\nimport unreal\n'
        + f'probe = runpy.run_path({str(script)!r})\n'
        + 'frame_deltas = []\n'
        + 'def observe(delta):\n    frame_deltas.append(float(delta))\n'
        + 'frame_handle = unreal.register_slate_post_tick_callback(observe)\n'
        + 'def retain():\n'
        + f'    Path({str(out / "frame-times.json")!r}).write_text(json.dumps(frame_deltas))\n'
        + 'atexit.register(retain)\n', encoding='utf-8')
    command = [str(executable), str(projects[0]), '/Game/MCP/L_AetherVault_MCP', '-game',
               '-unattended', '-RenderOffscreen', '-nosound', '-nop4', '-nosplash',
               '-windowed', '-ResX=640', '-ResY=480', '-log',
               '-ExecCmds=' + f't.MaxFPS {fps},py {launcher.as_posix()}']
    env = dict(os.environ, AETHER_STANDALONE_PROOF=str(out / 'probe'), AETHER_STANDALONE_RUN_GAITS='1')
    started = time.monotonic()
    with (out / 'process.log').open('x', encoding='utf-8') as log:
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=project,
                                    env=env, timeout=180, creationflags=0x08000000 if os.name == 'nt' else 0)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = -1
            log.write('\nOwned game process exceeded 180 seconds; stopped without retry.\n')
    report_path = out / 'probe/report.json'
    report = read_json(report_path) if report_path.exists() else {}
    times_path = out / 'frame-times.json'
    times = read_json(times_path) if times_path.exists() else []
    passed = exit_code == 0 and report.get('verdict') == 'PASS'
    receipt = {'recipe': binding(recipe_path), 'probe_script': binding(script), 'command': command,
               'exit_code': exit_code, 'elapsed_seconds': time.monotonic()-started,
               'requested_fps_cap': fps, 'frame_times': binding(times_path) if times else None,
               'observed_mean_fps': len(times)/sum(times) if times and sum(times) else None,
               'probe': binding(report_path) if report else None, 'runtime_checks_passed': passed,
               'human_approved': False, 'production_ready': False,
               'scope': 'Fresh editor -game process; idle/walk/jog/sprint-speed/stop input probe. No cooked-build, turn, jump, combat-interruption or Shift-binding proof.'}
    write_retained_json(out / 'receipt.json', receipt)
    if not passed:
        raise RuntimeError(f'owned runtime probe failed/incomplete; inspect {out}')
    return receipt


def surface_audit(args):
    """Skin check on packet poses through the game's surface adapter; not a runtime pose dump."""
    import math
    recipe, packet, skeleton = load_recipe(args.recipe)
    if not skeleton or not math.isfinite(args.floor_z_cm):
        raise ValueError('surface audit needs inspected skeleton and finite declared floor')
    base = args.recipe.resolve().parent
    packet_path = bound_path(recipe['packet'], base)
    if args.packet:
        packet_path = args.packet.resolve()
        packet = read_json(packet_path)
        if packet['provenance']['character_blend_sha256'] != recipe['character']['sha256']:
            raise ValueError('surface candidate belongs to another character')
    from reference_asset_compiler.animation_motion import validate_packet
    validate_packet(packet)
    selected = args.clips.split(',') if args.clips else list(recipe['benchmark'])
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(packet['clips']):
        raise ValueError('select existing unique surface-audit clips')
    if any((packet['clips'][n]['frames']-1)/packet['clips'][n]['fps'] < .5 for n in selected):
        raise ValueError('the footing adapter requires clips at least 0.5 seconds long')
    scripts = [bound_path(r, base) for r in recipe['workstation']['surface_scripts']]
    if [p.name for p in scripts] != ['CheckLocomotionClearance.py', 'CheckLocomotionFooting.py']:
        raise ValueError('unexpected surface adapter')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rest_clip = {'tracks': {n: [v] for n, v in skeleton['rest_local'].items()}}
    rest = transforms(world_matrices(rest_clip, skeleton))[0]
    proof = {'error': None, 'kind': 'offline-packet', 'fps': args.sample_hz,
             'stage': {'floor_z_cm': args.floor_z_cm, 'scope': 'Explicit hypothetical plane in source space, not measured gameplay terrain.'},
             'reference_component': dict(zip(skeleton['bones'], rest.tolist(), strict=True)), 'frames': []}
    for name in selected:
        c = packet['clips'][name]
        poses = transforms(world_matrices(c, skeleton))
        step = max(1, round(c['fps']/args.sample_hz))
        for f in sorted(set(range(0, c['frames'], step)) | {c['frames']-1}):
            proof['frames'].append({'case': name, 'frame': f, 'time': f/c['fps'],
                'mesh_world': [0, 0, 0, 0, 0, 0, 1], 'bones': dict(zip(skeleton['bones'], poses[f].tolist(), strict=True))})
    write_retained_json(out / 'poses.json', proof)
    receipt = {'packet': binding(packet_path), 'recipe': binding(args.recipe), 'poses': binding(out / 'poses.json'),
               'scope': 'Sampled source-rig skinning of packet poses; declared floor plane. No gameplay, continuous-collision or whole-body clearance claim.',
               'human_approved': False, 'production_ready': False, 'runs': [], 'complete': False}
    for script, label in zip(scripts, ('clearance', 'footing'), strict=True):
        command = [args.blender, '--background', '--factory-startup', '--python-exit-code', '1',
                   '--python', str(script), '--', '--source', str(bound_path(recipe['character'], base)),
                   '--proof', str(out / 'poses.json'), '--output', str(out / (label + '.json'))]
        with (out / (label + '.log')).open('x', encoding='utf-8') as log:
            try:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=900)
                exit_code = result.returncode
            except subprocess.TimeoutExpired:
                exit_code = -1
        receipt['runs'].append({'script': binding(script), 'command': command, 'exit_code': exit_code,
                               'result': binding(out / (label + '.json')) if (out / (label + '.json')).exists() else None})
        if exit_code:
            write_retained_json(out / 'receipt.json', receipt)
            raise RuntimeError(f'surface adapter failed; inspect {out}; no automatic retry')
    receipt['complete'] = True
    receipt['clearance_passed'] = read_json(out / 'clearance.json')['passed']
    write_retained_json(out / 'receipt.json', receipt)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='operation', required=True)
    q = sub.add_parser('snapshot')
    q.add_argument('--project', type=Path, required=True)
    q.add_argument('--config', required=True, help='Game character configuration, e.g. Tools/Characters/<name>.json')
    q.add_argument('--output', type=Path, required=True)
    q = sub.add_parser('run', help='Reusable recipe-to-review workflow; never installs game assets')
    q.add_argument('recipe', type=Path)
    q.add_argument('--output', type=Path, required=True)
    q.add_argument('--blender', required=True)
    q.add_argument('--clips', default='')
    q.add_argument('--render-views', action='store_true')
    for name in ('inspect', 'export', 'bake-library'):
        q = sub.add_parser(name)
        q.add_argument('recipe', type=Path)
        q.add_argument('--output', type=Path, required=True)
        q.add_argument('--blender', required=True)
        q.add_argument('--packet', type=Path)
        q.add_argument('--clips', default='')
        q.add_argument('--render-views', action='store_true')
        q.add_argument('--motion-fps', type=int, choices=(0, 12, 24, 30), default=0)
        q.add_argument('--ffmpeg')
    for name in ('engine-audit', 'engine-runtime'):
        q = sub.add_parser(name)
        q.add_argument('recipe', type=Path)
        q.add_argument('--unreal', type=Path, required=True)
        q.add_argument('--output', type=Path, required=True)
        if name == 'engine-runtime':
            q.add_argument('--fps', type=int, choices=(30, 60, 120), required=True)
    q = sub.add_parser('surface-audit')
    q.add_argument('recipe', type=Path)
    q.add_argument('--output', type=Path, required=True)
    q.add_argument('--blender', required=True)
    q.add_argument('--packet', type=Path)
    q.add_argument('--clips', default='')
    q.add_argument('--sample-hz', type=int, choices=(6, 15, 30), default=6)
    q.add_argument('--floor-z-cm', type=float, required=True)
    args = p.parse_args()
    if args.operation == 'snapshot':
        result = {'recipe': str(snapshot(args.project, args.output, args.config))}
    elif args.operation == 'run':
        result = run_workflow(args)
    elif args.operation == 'engine-audit':
        result = engine_audit(args.recipe, args.unreal, args.output)
    elif args.operation == 'engine-runtime':
        result = engine_runtime(args.recipe, args.unreal, args.output, args.fps)
    elif args.operation == 'surface-audit':
        result = surface_audit(args)
    else:
        result = run_adapter(args)
    print(json.dumps(result, indent=2))
    print('ANIMATION_WORKFLOW_COMPLETE -- the receipts have learned their steps.')


if __name__ == '__main__':
    main()
