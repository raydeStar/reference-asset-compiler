# SPDX-License-Identifier: MIT
"""Measure or compare runtime contact proofs from an owned engine probe.

  python scripts/anim/analyze_runtime_contact.py walk PROOF OUTPUT --criteria PROFILE
  python scripts/anim/analyze_runtime_contact.py turns PROOF OUTPUT --criteria PROFILE [--before PROOF]
  python scripts/anim/analyze_runtime_contact.py recovery PROOF OUTPUT --criteria PROFILE
  python scripts/anim/analyze_runtime_contact.py combat PROOF OUTPUT --criteria PROFILE [--before PROOF]
  python scripts/anim/analyze_runtime_contact.py compare-recovery BEFORE AFTER OUTPUT

Per-character speeds and windows live in the criteria profile
(profiles/animation/runtime-contact/<name>.json). OUTPUT must not exist.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))
from reference_asset_compiler import animation_runtime_contact as rc  # noqa: E402

MEASURES = {'walk': (rc.analyze_locomotion, None), 'turns': (rc.measure_turns, rc.compare_turns),
            'recovery': (rc.analyze_recovery, None), 'combat': (rc.measure_combat, rc.compare_combat)}


def binding(path):
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='measure', required=True)
    for name, (_, comparison) in MEASURES.items():
        q = sub.add_parser(name)
        q.add_argument('proof', type=Path)
        q.add_argument('output', type=Path)
        q.add_argument('--criteria', type=Path)
        if comparison:
            q.add_argument('--before', type=Path)
    q = sub.add_parser('compare-recovery')
    q.add_argument('before', type=Path)
    q.add_argument('after', type=Path)
    q.add_argument('output', type=Path)
    args = p.parse_args(argv)
    if args.measure == 'compare-recovery':
        result = rc.compare_recovery(json.loads(args.before.read_text()), json.loads(args.after.read_text()))
        result['inputs'] = {'before': binding(args.before), 'after': binding(args.after)}
    else:
        proof = json.loads(args.proof.read_text())
        profile = json.loads(args.criteria.read_text()) if args.criteria else None
        measure, comparison = MEASURES[args.measure]
        result = measure(proof, rc.criteria(profile, proof))
        result['proof'] = binding(args.proof)
        if args.criteria:
            result['criteria_profile'] = binding(args.criteria)
        if getattr(args, 'before', None):
            result['comparison'] = comparison(json.loads(args.before.read_text()), proof)
            result['before'] = binding(args.before)
    with args.output.open('x') as handle:
        json.dump(result, handle, indent=2)
    print('RUNTIME_CONTACT_MEASURED', args.measure, '-- the numbers describe the boots; they do not applaud them.')


if __name__ == '__main__':
    main()
