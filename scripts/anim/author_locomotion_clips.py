# SPDX-License-Identifier: MIT
"""Add authored cycles and turn-in-place clips to a copy of an existing packet (CPU).

  python scripts/anim/author_locomotion_clips.py --packet <clips.json> --skeleton <skeleton.json> \
      --profile profiles/animation/authoring/<name>.json --out <fresh dir>

Every existing clip is kept unchanged; the new clips, their measurements and the
input hashes are written beside them. The output folder must not exist.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from reference_asset_compiler.animation_authoring import author_packet  # noqa: E402
from reference_asset_compiler.animation_motion import validate_packet  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--skeleton', type=Path, required=True)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    packet = json.loads(args.packet.read_text(encoding='utf-8-sig'))
    skeleton = json.loads(args.skeleton.read_text())
    profile = json.loads(args.profile.read_text())
    if profile.get('schema') != 'rac.locomotion-authoring.v1':
        raise ValueError('unsupported authoring profile')
    validate_packet(packet)
    if packet['bones'] != skeleton['bones']:
        raise ValueError('skeleton bones differ from the packet')
    if packet['provenance'].get('character_blend_sha256') != skeleton.get('source_sha256'):
        raise ValueError('skeleton belongs to another character')
    result, measurements = author_packet(packet, skeleton, profile)
    added = sorted(set(result['clips']) - set(packet['clips']))
    result['provenance'] = dict(packet['provenance'])
    result['provenance']['authoring'] = {
        'input_packet': str(args.packet.resolve()), 'input_sha256': digest(args.packet),
        'skeleton_sha256': digest(args.skeleton), 'profile': str(args.profile.resolve()),
        'profile_sha256': digest(args.profile), 'script_sha256': digest(__file__),
        'module_sha256': digest(Path(__file__).resolve().parents[2] / 'src/reference_asset_compiler/animation_authoring.py'),
        'added_clips': added, 'existing_clips_unchanged': True}
    validate_packet(result)
    for name, clip in packet['clips'].items():
        if result['clips'][name] != clip:
            raise AssertionError(f'existing clip changed: {name}')
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'clips.json').write_text(json.dumps(result, separators=(',', ':')), encoding='utf-8')
    (args.out / 'measurements.json').write_text(json.dumps(measurements, indent=2), encoding='utf-8')
    (args.out / 'authoring-derivation.json').write_text(json.dumps(
        {**result['provenance']['authoring'], 'packet_sha256': digest(args.out / 'clips.json'),
         'human_approved': False, 'production_ready': False}, indent=2), encoding='utf-8')
    print('CLIPS_AUTHORED', ', '.join(added), '-- new steps, old shoes untouched.')


if __name__ == '__main__':
    main()
