"""Build a pinned, texture-only Character02 sleeve derivative for Unreal review."""
import argparse
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    recipe = json.loads(args.recipe.read_text())
    inputs = {}
    for name, item in recipe['inputs'].items():
        path = ROOT / item['path']
        if sha(path) != item['sha256']:
            raise ValueError(f'{name} changed; the tailor checks the label, sir.')
        inputs[name] = path
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    scripts = out / 'scripts'
    scripts.mkdir()
    receipt = {'inputs': recipe['inputs'], 'recipe_sha256': sha(args.recipe),
               'python': sys.version, 'versions': {p: importlib.metadata.version(p)
                                                  for p in ('numpy', 'scipy', 'Pillow')},
               'state': 'running', 'production_ready': False, 'human_review': 'pending',
               'scripts': {}, 'outputs': {}, 'commands': []}
    shutil.copy2(args.recipe, out / 'recipe.json')
    for path in (Path(__file__), ROOT / 'scripts/wrap_sleeve_paint.py',
                 ROOT / 'src/reference_asset_compiler/view_projection.py'):
        receipt['scripts'][str(path.relative_to(ROOT))] = sha(path)
        shutil.copy2(path, scripts / path.name)

    def save():
        (out / 'sleeve-repair.json').write_text(json.dumps(receipt, indent=2))

    command = [sys.executable, str(ROOT / 'scripts/wrap_sleeve_paint.py')]
    for name in ('mesh', 'paint', 'front', 'back'):
        command += ['--' + name, str(inputs[name])]
    command += ['--out', str(out / 'outfit-paint'), '--px-per-m', str(recipe['px_per_m']),
                '--origin', *map(str, recipe['origin']), '--sleeve-range', *map(str, recipe['sleeve_range']),
                '--surface-coverage', recipe['surface_coverage']]
    entry = {'argv': command, 'returncode': None}
    receipt['commands'].append(entry)
    save()
    with (out / 'bake.log').open('w') as log:
        entry['returncode'] = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False).returncode
    if entry['returncode']:
        receipt['state'] = 'failed'
        save()
        raise RuntimeError(f'Sleeve bake failed; inspect {out / "bake.log"}')
    for name, relative in recipe['copies'].items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inputs[name], target)
        assert sha(target) == recipe['inputs'][name]['sha256'], name
        receipt['outputs'][relative] = sha(target)
    paint = out / 'outfit-paint/body_basecolor.png'
    receipt['outputs']['outfit-paint/body_basecolor.png'] = sha(paint)
    receipt['geometry_rig_and_other_textures_identical'] = True
    receipt['state'] = 'review_candidate'
    save()
    print('Texture-only derivative ready; every bone retains its original employment, sir.')


if __name__ == '__main__':
    main()
