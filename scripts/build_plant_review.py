"""Show retained plant acquisition evidence without granting a visual gate."""
from __future__ import annotations

import argparse
import html
import os
from pathlib import Path

from reference_asset_compiler.io import read_json, sha256_file, write_json
from reference_asset_compiler.workspace import audit_workspace

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ('front', 'three-quarter', 'side', 'back')


def build(output: Path) -> None:
    output = output.resolve()
    if output.exists() or output.with_suffix('.json').exists():
        raise ValueError('Retained evidence cannot be overwritten; choose a new panel.')
    job = ROOT / 'work/sunset-plant'
    review = job / 'modeling/multiview-v001'
    audit = audit_workspace(job)
    if not audit['ok']:
        raise ValueError(audit['failures'])
    records, sections = [], []

    def section(title, note, labeled_paths):
        figures = []
        for label, path in labeled_paths:
            if not path.is_file():
                raise FileNotFoundError(path)
            relative = Path(os.path.relpath(path, output.parent)).as_posix()
            figures.append('<figure><a href="{0}"><img loading="lazy" src="{0}" alt="{1}"></a>'
                           '<figcaption>{1}</figcaption></figure>'.format(
                               html.escape(relative, quote=True), html.escape(label)))
            records.append({'label': label, 'path': str(path), 'sha256': sha256_file(path)})
        sections.append('<section><h2>{0}</h2><p>{1}</p><div class="grid">{2}</div></section>'.format(
            html.escape(title), html.escape(note), ''.join(figures)))

    section('Image-conditioned acquisition',
            'Original intake is the direct front input. Built-in ImageGen supplied inferred left/back guidance, not measured orthographic rotations.',
            [('Original authority', job / 'references/primary.png'),
             ('Inferred left', job / 'references/multiview-v001/left.png'),
             ('Inferred back', job / 'references/multiview-v001/back.png')])
    section('Rejected single-view mesh', 'Retained for comparison: torn and fragmented outer leaves.',
            [(v, job / 'modeling/fixed-views' / ('matcap-' + v + '.png')) for v in VIEWS])
    verdict = read_json(review / 'delegated-modeling-review.json')
    section('Accepted multiview modeling', verdict['findings'],
            [(v, review / 'fixed-views' / ('matcap-' + v + '.png'))
             for v in (*VIEWS, 'top', 'underside', 'elevated')])
    rejected_path = job / 'retopology/multiview-rejections-v001.json'
    if rejected_path.is_file():
        rejected = read_json(rejected_path)
        for trial in rejected['trials']:
            reduced = job / 'retopology' / trial['candidate'] / 'fixed-views'
            section('Rejected topology: ' + trial['candidate'], trial['reason'],
                    [(v, reduced / ('matcap-' + v + '.png')) for v in VIEWS])
            records += trial['files']
    bound = [job / 'state.json', review / 'delegated-modeling-review.json',
             review / 'previous-candidate-rejection.json',
             job / 'references/multiview-v001/lineage.json',
             job / 'candidates/hy3d-mv-seed42-attempt002/candidate.glb',
             job / 'candidates/hy3d-mv-seed42-attempt002/candidate-receipt.json']
    if rejected_path.is_file():
        bound.append(rejected_path)
    records += [{'label': p.name, 'path': str(p), 'sha256': sha256_file(p)} for p in bound]
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sunset plant — actual mesh review</title>
<style>body{max-width:1600px;margin:36px auto;padding:0 24px;background:#171d1c;color:#e7e0cf;font:16px/1.5 system-ui}
h1,h2{color:#e9bd77}p{max-width:1100px;color:#c6cec7}section{border-top:1px solid #465349;margin-top:36px;padding-top:12px}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}figure{margin:0}img{width:100%;border-radius:9px}
figcaption{padding:8px}a{color:#a3d7c4}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:480px){.grid{grid-template-columns:1fr}}</style>
<h1>Sunset workshop · the plant repair</h1><p>Actual image-conditioned 3D mesh renders, not painted mockups.
Visual reviewer: Codex under Ayric's explicit demo delegation; human_visual_review=false. This panel is not UE or cooked-runtime proof.
Click any image for full resolution.</p>'''
    page += ''.join(sections)
    prompts = Path(os.path.relpath(job / 'references/multiview-v001/lineage.json', output.parent)).as_posix()
    page += '<section><h2>Provenance</h2><p><a href="{}">Exact ImageGen prompts and source hashes</a> · All previous candidates remain on disk.</p></section></html>'.format(html.escape(prompts, quote=True))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding='utf-8')
    write_json(output.with_suffix('.json'), {'schema': 'reference-asset-compiler.plant-review.v1',
               'audit_snapshot': audit, 'files': records})
    print('PLANT_REVIEW_READY', output, '-- no shredded foliage swept under the rug.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
