"""Explicit, relocatable authoring profiles; paths are supplied, never guessed."""
from __future__ import annotations

import copy
from pathlib import Path
import re

from .animation_workflow import SCHEMA, binding, load_recipe
from .animation_motion import validate_packet
from .io import read_json, write_retained_json


def create_recipe(profile_path, output, inputs=None):
    """Bind a reusable profile to real inputs and validate before publishing it."""
    profile_path, output = Path(profile_path).resolve(), Path(output).resolve()
    profile = read_json(profile_path)
    if profile.get('schema') != 'reference-asset-compiler.animation-profile.v1':
        raise ValueError('unsupported animation profile schema')
    inputs = dict(inputs or {})
    used = set()

    def path(value):
        if not isinstance(value, str):
            raise ValueError('profile paths must be strings')
        def replace(match):
            key = match.group(1)
            if key not in inputs:
                raise ValueError(f'missing explicit input: {key}')
            used.add(key)
            return str(inputs[key])
        resolved = re.sub(r'\$\{([A-Z][A-Z0-9_]*)\}', replace, value)
        if '${' in resolved:
            raise ValueError('invalid input placeholder')
        p = Path(resolved)
        return p.resolve() if p.is_absolute() else (profile_path.parent / p).resolve()

    provider = copy.deepcopy(profile['provider'])
    for component in provider['components']:
        for field in ('artifact', 'license_evidence'):
            component[field] = binding(path(component[field]))
    packet_path, character = path(profile['packet']), path(profile['character'])
    packet = validate_packet(read_json(packet_path))
    benchmark = copy.deepcopy(profile.get('benchmark', {}))
    if not benchmark:
        benchmark = {name: {'contacts': [], 'joins': []} for name in packet['clips']}
    if set(benchmark) - set(packet['clips']):
        raise ValueError('profile benchmark references missing clips')
    recipe = {'schema': SCHEMA, 'asset': profile['asset'], 'pose_intent': profile['pose_intent'],
              'character': binding(character), 'packet': binding(packet_path),
              'coordinates': profile.get('coordinates', {'units': 'cm', 'up': 'Z',
                  'rotation': 'xyzw', 'space': 'UE-local'}),
              'provider': provider, 'mapping': [binding(path(p)) for p in profile.get('mapping', [])],
              'benchmark': benchmark, 'operations': copy.deepcopy(profile.get('operations', [])),
              'skeleton': binding(path(profile['skeleton'])) if profile.get('skeleton') else None,
              'profile': binding(profile_path), 'human_approved': False, 'production_ready': False}
    if profile.get('configuration'):
        recipe['configuration'] = binding(path(profile['configuration']))
    if set(inputs) - used:
        raise ValueError(f'unknown/unused inputs: {sorted(set(inputs)-used)}')
    # Validate using the normal contract before creating an output directory.
    # The temporary recipe contains absolute bindings; it cannot change an authority.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='rac-recipe-') as raw:
        candidate = Path(raw) / 'recipe.json'
        write_retained_json(candidate, recipe)
        load_recipe(candidate)
    output.mkdir(parents=True, exist_ok=False)
    write_retained_json(output / 'recipe.json', recipe)
    return {'recipe': binding(output / 'recipe.json'), 'asset': recipe['asset'],
            'clip_count': len(packet['clips']), 'human_approved': False, 'production_ready': False}


def parse_inputs(values):
    result = {}
    for value in values:
        key, sep, path = value.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or not path or key in result:
            raise ValueError('inputs must be unique NAME=path pairs')
        result[key] = path
    return result
