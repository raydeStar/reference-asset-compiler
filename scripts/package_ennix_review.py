"""Package a review and its frozen inputs locally; read back every copied hash."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--candidate', required=True)
    p.add_argument('--inputs', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--ue-content', required=True)
    p.add_argument('--verification-log', required=True)
    a = p.parse_args()
    source, out = Path(a.candidate).resolve(), Path(a.out).resolve()
    if out.exists():
        raise ValueError('Refusing to overwrite a delivery; the previous suitcase stays packed, sir.')
    out.mkdir(parents=True)
    records = {}

    def copy(src, name):
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        digest = sha(Path(src))
        if sha(target) != digest:
            raise ValueError('Copied hash differs: ' + name)
        records[name] = {'sha256': digest, 'bytes': target.stat().st_size}

    def tree(src, prefix, predicate=lambda p: True):
        for path in sorted(src.rglob('*')):
            if path.is_file() and predicate(path):
                copy(path, prefix + '/' + path.relative_to(src).as_posix())

    tree(Path(a.inputs).resolve(), 'rebuild-inputs')
    tree(source / 'rigged', 'character', lambda p: p.suffix in ('.blend', '.fbx', '.json'))
    tree(source / 'pose', 'pose', lambda p: p.suffix in ('.blend', '.png', '.json'))
    tree(source / 'assembly', 'review/assembly', lambda p: p.suffix in ('.png', '.json'))
    tree(source / 'head-review', 'review/head', lambda p: p.suffix == '.png')
    tree(source / 'visual-validation', 'review/reference')
    tree(source / 'export', 'export')
    for name in ('build-receipt.json', 'repeatability.json', 'semantic-canonical.json'):
        copy(source / name, 'evidence/' + name)
    copy(Path(a.verification_log), 'evidence/repository-verification.log')
    copy(ROOT / 'docs/ENNIX_REBUILD.md', 'README.md')
    copy(ROOT / 'recipes/ennix-open-review-20261007.json', 'recipe.json')
    copy(ROOT / 'LICENSE', 'CODE-LICENSE.txt')
    tree(Path(a.ue_content).resolve(), 'unreal/Content/EnnixReview/20261007/V5', lambda p: p.suffix == '.uasset')
    archive = out / 'rebuild-source.zip'
    subprocess.run(['git', 'archive', '--format=zip', '--output', str(archive), 'HEAD'], cwd=ROOT, check=True)
    records[archive.name] = {'sha256': sha(archive), 'bytes': archive.stat().st_size}
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    manifest = {'schema': 'ennix-local-review-delivery.v1', 'source_revision': revision,
        'candidate': str(source), 'files': records, 'file_count': len(records),
        'total_bytes': sum(x['bytes'] for x in records.values()), 'readback_hashes_passed': True,
        'production_ready': False, 'published': False,
        'limitations': ['Human approval pending', 'Silhouette below target', 'Triangle budget exceeded',
                        'No gameplay/cooked runtime proof', 'Held pose only; no moving idle']}
    (out / 'DELIVERY.json').write_text(json.dumps(manifest, indent=2))
    print(f"Packed and checked {len(records)} files, sir. No mystery parcels: {out}")


if __name__ == '__main__':
    main()
