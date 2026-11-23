"""Labelled sheets of a game review's in-game closeups, and a before/after against an earlier attempt.

python scripts/game_review_sheet.py <attempt> [--compare <earlier attempt>] [--looks a,b]

Writes <attempt>/07-closeups/closeups.jpg: one row per look (face front, three-quarter, low) and one row of the body
(front, three-quarter, side, back). A pose run (-Poses) adds poses.jpg: the body row and one row per pose. With
--compare, also compare.jpg: each row is BEFORE (the earlier attempt) above AFTER (this one), for the default look's
face and the body, and the poses when both runs have them. A face pass (-Face) adds face.jpg: each expression the game
plays, then each lip-sync mouth shape, from the front and the three-quarter, with --compare its BEFORE/AFTER as
face-compare.jpg.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FACE_CROP = (300, 60, 1140, 900)          # 1440x900 shots: the long-lens head fills the middle
BODY_CROP = (440, 0, 1000, 900)
CELL = 420


def font(size):
    try:
        return ImageFont.truetype('arial.ttf', size)
    except OSError:
        return ImageFont.load_default()


def cell(path, crop):
    size = (CELL, CELL) if crop is FACE_CROP else (int(CELL * 560 / 900), CELL)
    if not Path(path).is_file():
        blank = Image.new('RGB', size, (40, 20, 20))
        ImageDraw.Draw(blank).text((10, 10), 'missing', font=font(18), fill=(255, 120, 120))
        return blank
    return Image.open(path).convert('RGB').crop(crop).resize(size)


def sheet(rows, out):
    """rows: [(label, [(caption, image)])] -> one labelled image."""
    width = max(sum(im.width for _, im in cells) for _, cells in rows)
    height = sum(34 + CELL + 26 for _ in rows)
    canvas = Image.new('RGB', (width, height), (20, 20, 22))
    draw = ImageDraw.Draw(canvas)
    y = 0
    for label, cells in rows:
        draw.text((8, y + 6), label, font=font(22), fill=(255, 220, 120))
        x = 0
        for caption, im in cells:
            canvas.paste(im, (x, y + 34))
            draw.text((x + 6, y + 34 + CELL + 3), caption, font=font(16), fill=(200, 200, 200))
            x += im.width
        y += 34 + CELL + 26
    canvas.save(out, quality=90)
    return out


def rows_for(attempt, looks, tag='', poses=False):
    shots = Path(attempt) / '07-closeups'
    job = json.loads((Path(attempt) / 'job.json').read_text(encoding='utf-8'))
    title = f"{job['name']} {job['version']}"
    rows = []
    for look in looks:
        cells = [(v[0].replace('_', ' '), cell(shots / f'{look}_face_{v[0]}.png', FACE_CROP)) for v in job['face_views']]
        rows.append((f'{tag}{title} - face, look: {look}', cells))
    cells = [(v[0].replace('_', ' '), cell(shots / f'body_{v[0]}.png', BODY_CROP)) for v in job['body_views']]
    rows.append((f'{tag}{title} - body, idle', cells))
    done = shots / 'done.json'
    for pose in (json.loads(done.read_text(encoding='utf-8')).get('poses', []) if done.is_file() and poses else []):
        cells = [(v[0].replace('_', ' '), cell(shots / f'pose_{pose}_{v[0]}.png', BODY_CROP)) for v in job['body_views']]
        rows.append((f'{tag}{title} - pose: {pose}', cells))
    hands = [(f'{pose} {side}', shots / f'hand_{pose}_{side}.png') for pose in ('idle', 'attack') for side in ('l', 'r')]
    if poses and any(path.is_file() for _, path in hands):
        rows.append((f'{tag}{title} - hands (left, right; relaxed, then the attack fist)',
                     [(label, cell(path, FACE_CROP)) for label, path in hands]))
    return rows


def motion_sheet(attempt, done):
    """One row per animation the player uses: each view across, sampled through the clip's length."""
    shots = Path(attempt) / '07-closeups'
    w, h = 190, 305
    cols = [(view, f) for view in done['motion_views'] for f in done['motion_fractions']]
    problems = done.get('motion_problems', [])
    top = 40 + 24 * len(problems)
    rows = done['motion']
    canvas = Image.new('RGB', (w * len(cols), top + len(rows) * (h + 52)), (20, 20, 22))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), 'Every player animation, sampled at ' + ', '.join(f'{int(f * 100)}%' for f in done['motion_fractions'])
              + ' (three-quarter, then side)', font=font(22), fill=(255, 220, 120))
    for k, problem in enumerate(problems):
        draw.text((8, 40 + 24 * k), 'PROBLEM: ' + problem, font=font(18), fill=(255, 110, 110))
    for r, clip in enumerate(rows):
        y = top + r * (h + 52)
        draw.text((8, y + 4), f"{clip['clip']}  ({clip['length_s']} s; {', '.join(clip['used_by'])})", font=font(18),
                  fill=(255, 220, 120))
        for c, (view, f) in enumerate(cols):
            path = shots / f"motion_{clip['clip']}_{view}_{int(round(f * 100)):02d}.png"
            im = (Image.open(path).convert('RGB').crop(BODY_CROP).resize((w, h)) if path.is_file()
                  else Image.new('RGB', (w, h), (40, 20, 20)))
            canvas.paste(im, (c * w, y + 28))
            draw.text((c * w + 4, y + 28 + h + 2), f'{view.replace("_", " ")} {int(round(f * 100))}%', font=font(14),
                      fill=(200, 200, 200))
    out = shots / 'motion.jpg'
    canvas.save(out, quality=88)
    return out


EXPRESSION_CAPTIONS = {
    'rest': 'no expression', 'idle': 'idle (resting smirk)', 'combat': 'combat (attacks, dodges)',
    'hurt': 'hurt (a hit)', 'climb': 'climbing', 'hang': 'hanging, mantling', 'glide': 'gliding',
    'blink': 'blink (lids shut)'}
VISEME_CAPTIONS = {'X': 'X rest', 'A': 'A  M B P', 'B': 'B  K S T EE', 'C': 'C  EH AE', 'D': 'D  AA (wide)',
                   'E': 'E  AO ER', 'F': 'F  OO W', 'G': 'G  F V', 'H': 'H  L'}
FACE_CELL = 300


def face_rows(attempt, done, tag=''):
    """(label, [(caption, path)]) rows of a face pass: expressions, then mouth shapes, per view."""
    shots = Path(attempt) / '07-closeups'
    face = done['face_pass']
    rows = []
    for view in face['views']:
        rows.append((f'{tag}Expressions, {view.replace("_", "-")}',
                     [(EXPRESSION_CAPTIONS.get(s, s), shots / f'face_{s}_{view}.png') for s in face['states']]))
    for view in face['views']:
        rows.append((f'{tag}Lip-sync mouth shapes (over the idle face), {view.replace("_", "-")}',
                     [(VISEME_CAPTIONS.get(v, v), shots / f'face_viseme_{v}_{view}.png') for v in face['visemes']]))
    return rows


def face_sheet(rows, title, problems, out):
    size = FACE_CELL
    width = max(len(cells) for _, cells in rows) * size
    top = 40 + 24 * len(problems)
    canvas = Image.new('RGB', (width, top + len(rows) * (size + 56)), (20, 20, 22))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), title, font=font(22), fill=(255, 220, 120))
    for k, problem in enumerate(problems):
        draw.text((8, 40 + 24 * k), 'PROBLEM: ' + problem, font=font(18), fill=(255, 110, 110))
    for r, (label, cells) in enumerate(rows):
        y = top + r * (size + 56)
        draw.text((8, y + 4), label, font=font(18), fill=(255, 220, 120))
        for c, (caption, path) in enumerate(cells):
            im = (Image.open(path).convert('RGB').crop(FACE_CROP).resize((size, size)) if Path(path).is_file()
                  else Image.new('RGB', (size, size), (40, 20, 20)))
            canvas.paste(im, (c * size, y + 28))
            draw.text((c * size + 4, y + 30 + size), caption, font=font(15), fill=(200, 200, 200))
    canvas.save(out, quality=90)
    return out


def face_problems(done):
    face = done['face_pass']
    problems = []
    if face.get('unknown_morphs'):
        problems.append('the face drives morphs this mesh does not have (the game skips them silently): '
                        + ', '.join(face['unknown_morphs']))
    return problems


def motion_compare(attempt, done, base):
    """Each animation on the game's hero (baseline) above the same clip on the character, at the same frames."""
    shots = Path(attempt) / '07-closeups'
    job = json.loads((Path(attempt) / 'job.json').read_text(encoding='utf-8'))
    prefix = job['tag'] + '_'
    w, h = 170, 272
    cols = [(view, f) for view in done['motion_views'] for f in done['motion_fractions']]
    base_clips = {c['clip']: c for c in base['motion']}
    pairs = [(base_clips[c['clip'][len(prefix):]], c) for c in done['motion'] if c['clip'][len(prefix):] in base_clips]
    canvas = Image.new('RGB', (w * len(cols), 40 + len(pairs) * (2 * h + 76)), (20, 20, 22))
    draw = ImageDraw.Draw(canvas)
    draw.text((8, 8), f"Each animation: the game's hero (top) and {job['name']} {job['version']} (bottom), same frames "
              '(' + ', '.join(f'{int(f * 100)}%' for f in done['motion_fractions']) + '; three-quarter, then side)',
              font=font(22), fill=(255, 220, 120))
    y = 40
    for b, c in pairs:
        draw.text((8, y + 2), f"{b['clip']}  ({', '.join(c['used_by'])})", font=font(18), fill=(255, 220, 120))
        for row, (folder, clip, label) in enumerate(((shots / 'baseline', b, 'hero'), (shots, c, job['name']))):
            for k, (view, f) in enumerate(cols):
                path = folder / f"motion_{clip['clip']}_{view}_{int(round(f * 100)):02d}.png"
                im = (Image.open(path).convert('RGB').crop(BODY_CROP).resize((w, h)) if path.is_file()
                      else Image.new('RGB', (w, h), (40, 20, 20)))
                canvas.paste(im, (k * w, y + 24 + row * (h + 24)))
                if k == 0:
                    draw.text((4, y + 24 + row * (h + 24) + h + 2), label, font=font(15), fill=(200, 200, 200))
        y += 2 * h + 76
    out = shots / 'motion-compare.jpg'
    canvas.save(out, quality=86)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('attempt', type=Path)
    parser.add_argument('--compare', type=Path)
    parser.add_argument('--looks', help='comma-separated looks to show (default: every look in done.json)')
    args = parser.parse_args(argv)
    done = json.loads((args.attempt / '07-closeups' / 'done.json').read_text(encoding='utf-8'))
    looks = args.looks.split(',') if args.looks else done['looks']
    print('SHEET', sheet(rows_for(args.attempt, looks), args.attempt / '07-closeups' / 'closeups.jpg'))
    if done.get('poses'):
        pose_rows = rows_for(args.attempt, [], poses=True)
        print('SHEET', sheet(pose_rows, args.attempt / '07-closeups' / 'poses.jpg'))
    if done.get('motion'):
        print('SHEET', motion_sheet(args.attempt, done))
        base_done = args.attempt / '07-closeups' / 'baseline' / 'done.json'
        if base_done.is_file():
            print('SHEET', motion_compare(args.attempt, done, json.loads(base_done.read_text(encoding='utf-8'))))
    if done.get('face_pass'):
        job = json.loads((args.attempt / 'job.json').read_text(encoding='utf-8'))
        gains = done['face_pass'].get('mouth_morph_gain') or {}
        title = (f"{job['name']} {job['version']} - the game's face component, held in each state; lip-sync gains: "
                 + (', '.join(f'{k} x{v:g}' for k, v in gains.items()) or 'none (the table as tuned)'))
        print('SHEET', face_sheet(face_rows(args.attempt, done), title, face_problems(done),
                                  args.attempt / '07-closeups' / 'face.jpg'))
    if args.compare:
        both = bool(done.get('poses')) and (args.compare / '07-closeups' / 'pose_bind_front.png').is_file()
        before = rows_for(args.compare, ['default'], 'BEFORE  ', poses=both)
        after = rows_for(args.attempt, ['default'], 'AFTER  ', poses=both)
        paired = [row for pair in zip(before, after) for row in pair]
        print('SHEET', sheet(paired, args.attempt / '07-closeups' / 'compare.jpg'))
        earlier_done = args.compare / '07-closeups' / 'done.json'
        earlier = json.loads(earlier_done.read_text(encoding='utf-8')) if earlier_done.is_file() else {}
        if done.get('face_pass') and earlier.get('face_pass'):
            before = face_rows(args.compare, earlier, 'BEFORE  ')
            after = face_rows(args.attempt, done, 'AFTER  ')
            paired = [row for pair in zip(before, after) for row in pair]
            print('SHEET', face_sheet(paired, 'Face pass: BEFORE (earlier attempt) above AFTER (this attempt)',
                                      face_problems(done), args.attempt / '07-closeups' / 'face-compare.jpg'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
