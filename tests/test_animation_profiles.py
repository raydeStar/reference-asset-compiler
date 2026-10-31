"""Profiles must travel across directories without silently rebinding sources."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from reference_asset_compiler.animation_profiles import create_recipe, parse_inputs
from reference_asset_compiler.animation_workflow import load_recipe


def profile_for(recipe_path):
    source = json.loads(recipe_path.read_text())
    source['schema'] = 'reference-asset-compiler.animation-profile.v1'
    source['asset'] = 'DifferentRig'
    for field in ('packet','character','skeleton'):
        source[field] = Path(source[field]['path']).name
    source['packet'] = '${PACKET}'
    for component in source['provider']['components']:
        for key in ('artifact','license_evidence'):
            component[key] = Path(component[key]['path']).name
    p = recipe_path.parent/'profile.json'
    p.write_text(json.dumps(source))
    return p


def test_profile_resolves_relative_files_after_output_relocation(recipe, tmp_path):
    profile = profile_for(recipe)
    target = tmp_path/'somewhere/else'
    result = create_recipe(profile, target, {'PACKET':str(tmp_path/'clips.json')})
    loaded, packet, skeleton = load_recipe(Path(result['recipe']['path']))
    assert loaded['asset'] == 'DifferentRig'
    assert packet['bones'] == skeleton['bones']
    assert result['human_approved'] is False
    with pytest.raises(FileExistsError):
        create_recipe(profile, target, {'PACKET':str(tmp_path/'clips.json')})


def test_profile_refuses_missing_and_unused_inputs(recipe, tmp_path):
    profile = profile_for(recipe)
    with pytest.raises(ValueError, match='missing explicit input'):
        create_recipe(profile, tmp_path/'out')
    with pytest.raises(ValueError, match='unused'):
        create_recipe(profile, tmp_path/'out', {'PACKET':str(tmp_path/'clips.json'),'TYPO':'oops'})
    assert not (tmp_path/'out').exists()


def test_profile_does_not_relabel_another_characters_packet(recipe, tmp_path):
    profile = profile_for(recipe)
    (tmp_path/'authority.blend').write_bytes(b'a different character')
    with pytest.raises(ValueError, match='character authority'):
        create_recipe(profile, tmp_path/'out', {'PACKET':str(tmp_path/'clips.json')})
    assert not (tmp_path/'out').exists()


def test_profile_checks_benchmark_and_license_inventory(recipe, tmp_path):
    profile = profile_for(recipe)
    data = json.loads(profile.read_text())
    data['benchmark']['absent'] = {}
    profile.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='missing clips'):
        create_recipe(profile, tmp_path/'out', {'PACKET':str(tmp_path/'clips.json')})
    del data['benchmark']['absent']
    data['provider']['components'][0]['license'] = 'research-only'
    profile.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='strict-open'):
        create_recipe(profile, tmp_path/'out', {'PACKET':str(tmp_path/'clips.json')})


@pytest.mark.parametrize('values', [['A=x','A=y'],['a=x'],['A'],['A=']])
def test_ambiguous_input_bindings_fail(values):
    with pytest.raises(ValueError, match='unique NAME=path'):
        parse_inputs(values)
