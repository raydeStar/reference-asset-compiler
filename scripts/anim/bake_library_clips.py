# SPDX-License-Identifier: MIT
"""Bake open-library animation clips onto a character's game rig as UE local bone tracks (Blender).

  blender -b --factory-startup <character game .blend> --python-exit-code 1 -P scripts/anim/bake_library_clips.py --
      --profile profiles/animation/ual-to-ue-template.json --library ual1=<AL_Standard.fbx> --library ual2=<UAL2.glb>
      --out <dir> [--clips MM_Idle,MF_Unarmed_Jog_Fwd] [--fps 30]

Writes <out>/clips.json: per clip the fps, length, loop flag, measured ground speed (cm/s) and every bone's
local transform per frame in UE space ([x, y, z cm, qx, qy, qz, qw]), plus provenance (input hashes, Blender
version, script hash). The game side (TheAetherWars Tools/LibraryAnims.py) keys them into the character's
AnimSequences. Retarget method: scripts/anim/clip_retarget.py.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clip_retarget as cr  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--library', action='append', default=[], help='name=path')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--clips', default='')
    p.add_argument('--fps', type=int, default=30)
    p.add_argument('--contract', type=Path, help='the game clip timing (length, impact_s per clip) for retimed clips')
    p.add_argument('--no-coat-follow', action='store_true',
                   help='leave coat_* chains at rest (by default they swing clear of the legs)')
    a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    a.out.mkdir(parents=True, exist_ok=False)
    profile = json.loads(a.profile.read_text())
    if 'bone_map_from' in profile:      # share one bone map between clip profiles
        profile['bone_map'] = json.loads((a.profile.parent / profile['bone_map_from']).read_text())['bone_map']
    paths = dict(item.split('=', 1) for item in a.library)
    wanted = [c for c in a.clips.split(',') if c] or list(profile['clips'])
    rig = cr.TargetRig(next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE'))
    contract = json.loads(a.contract.read_text())['clips'] if a.contract else {}

    def segments_of(spec):
        return spec.get('segments') or [{'library': spec['library'], 'action': spec['action']}]
    libraries, retargets = {}, {}
    for clip in wanted:
        for seg in segments_of(profile['clips'][clip]):
            name = seg['library']
            if name not in libraries:
                if profile['adapter'] == 'ual':
                    libraries[name] = cr.UalLibrary(paths[name])
                elif profile['adapter'] == 'bvh':
                    takes = sorted({profile['clips'][c]['action'] for c in wanted
                                    if profile['clips'][c].get('library') == name})
                    libraries[name] = cr.BvhLibrary(paths[name], takes)
                else:
                    raise SystemExit(f"unknown adapter {profile['adapter']}")
                retargets[name] = cr.Retarget(rig, libraries[name], profile['bone_map'])
    def library_hashes(n):
        lib = libraries[n]
        if isinstance(lib, cr.BvhLibrary):       # a folder of takes: hash each take used
            return {t: sha(lib.folder / f'{t}.bvh') for t in lib.rigs}
        return sha(paths[n])
    forward = np.array([0.0, -1.0, 0.0])         # the rig faces -Y in Blender (UE +X after export)
    coat_follow = None if a.no_coat_follow else cr.CoatFollow(rig)
    default_coat_max = coat_follow.max_deg if coat_follow else None
    out = {'clips': {}, 'bones': rig.names,
           'provenance': {'profile': str(a.profile), 'profile_sha256': sha(a.profile),
                          'contract': str(a.contract) if a.contract else None,
                          'contract_sha256': sha(a.contract) if a.contract else None,
                          'libraries': {n: {'path': paths[n], 'sha256': library_hashes(n)} for n in libraries},
                          'character_blend': bpy.data.filepath, 'character_blend_sha256': sha(bpy.data.filepath),
                          'blender': bpy.app.version_string, 'script_sha256': sha(__file__),
                          'retarget_sha256': sha(cr.__file__)}}
    for clip in wanted:
        spec = profile['clips'][clip]
        segs = segments_of(spec)
        timing = None
        root_track, speed = None, None
        if len(segs) == 1 and not spec.get('mirror') and not spec.get('retime'):
            rt = retargets[segs[0]['library']]
            t0, t1 = spec.get('range') or (0.0, rt.lib.length(segs[0]['action']))
            length = t1 - t0
            n = max(2, round(length * a.fps) + 1)
            worlds = [rt.world(segs[0]['action'], t0 + length * i / (n - 1), loop=spec['loop']) for i in range(n)]
            if spec.get('root_motion') == 'facing':
                # Travelling mocap: ground position and heading onto UE's root bone (motion matching reads it).
                worlds, roots = cr.facing_root_motion(worlds, rig, fps=a.fps)
                root_track = [[round(v, 6) for v in cr.ue_root_matrix(rig, m)] for m in roots]
                ground = np.array([m[:3, 3] for m in roots])
                travel = float(np.linalg.norm(np.diff(ground[:, :2], axis=0), axis=1).sum())
                speed = travel / length * 100
        else:
            seq = cr.Sequence(retargets, segs, mirror=spec.get('mirror', False))
            keys, length = [], seq.length
            if spec.get('retime'):
                # The game's timing contract: clip length and the moment the hit lands.
                c = contract[clip]
                length = c['length']
                impact_src = seq.peak_speed_time(spec['retime']['impact_bone'])
                keys = [(c['impact_s'], impact_src)]
                timing = {'length_s': length, 'impact_target_s': c['impact_s'], 'impact_source_s': round(impact_src, 3),
                          'source_length_s': round(seq.length, 3)}
            n = max(2, round(length * a.fps) + 1)
            root_track = None
            _, src_t = cr.retime(length, n, seq.length, keys)
            worlds = [seq.world(t) for t in src_t]
            if spec.get('root_motion'):
                # Measured from the rest pelvis, not frame 0: a clip that starts displaced (the second cut
                # of a combo continues from where the first ended) still has its pelvis over the root.
                p0 = rig.rest[rig.index['pelvis']][:3, 3].copy()
                moved = [cr.extract_root_motion(w, rig, p0) for w in worlds]
                worlds = [w for w, _ in moved]
                if 'root' not in rig.index:
                    root_track = [[round(v, 6) for v in cr.ue_root_track(rig, sh)] for _, sh in moved]
        layers = {}
        if spec.get('stance'):
            st = cr.Stance(rig, **spec['stance'])
            lf, rf = rig.index['foot_l'], rig.index['foot_r']
            before = float(np.median([np.dot(w[lf][:3, 3] - w[rf][:3, 3], st.lat) for w in worlds]))
            worlds = [st.apply(w) for w in worlds]
            after = float(np.median([np.dot(w[lf][:3, 3] - w[rf][:3, 3], st.lat) for w in worlds]))
            layers['stance'] = {'feet_apart_before_m': round(before, 3), 'feet_apart_after_m': round(after, 3)}
        if spec.get('hands') == 'relaxed':
            hands = cr.RelaxedHands(rig)
            worlds = [hands.apply(w) for w in worlds]
            layers['hands'] = 'relaxed'
        coat = None
        if coat_follow and coat_follow.chains:
            # A clip may cap the swing (wide sword lunges would lever the panels out flat).
            coat_follow.max_deg = spec.get('coat_max_deg', default_coat_max)
            coat_follow.apply(worlds, spec['loop'])
            coat = coat_follow.last
        tracks = {b: [] for b in rig.names}
        for world in worlds:
            local = rig.world_to_local(world)
            for i, b in enumerate(rig.names):
                tracks[b].append([round(v, 6) for v in cr.ue_from_matrix(local[i])])
        if root_track is not None:
            tracks['root'] = root_track
        if spec.get('root_motion') != 'facing':
            speed = None
        if spec.get('measure_speed'):
            speed = cr.planted_speed(retargets[segs[0]['library']], segs[0]['action'], forward) * 100
        source = ' + '.join(f"{g['library']}:{g['action']}" for g in segs) + (' (mirrored)' if spec.get('mirror') else '')
        out['clips'][clip] = {'source': source, 'fps': a.fps, 'frames': n, 'length': length, 'loop': spec['loop'],
                              'speed_cm_s': speed, 'root_motion': bool(spec.get('root_motion')), 'timing': timing,
                              'trace_bone': spec.get('trace_bone'),
                              'also_as': spec.get('also_as', []), 'coat_follow': coat, 'layers': layers, 'tracks': tracks}
        print(f'BAKED {clip} <- {source}: {n} keys, {length:.2f}s, speed {speed}, timing {timing}, layers {layers}', flush=True)
    (a.out / 'clips.json').write_text(json.dumps(out, separators=(',', ':')))
    (a.out / 'summary.json').write_text(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk != 'tracks'} for k, v in out['clips'].items()} |
        {'provenance': out['provenance']}, indent=2))
    print('LIBRARY_BAKE_DONE', a.out)


if __name__ == '__main__':
    main()
