"""Split a character's reference image into its parts automatically: grounded detection, then SAM masks.

The Raider's part map was made by hand (scripts/revamp/raider/sam_parts.py lists automatic mask ids and click
prompts read off that one image), so it could not be repeated on another character. Here the parts of a
vocabulary (profiles/segmentation/humanoid-gear.json) are found with Grounding DINO
(IDEA-Research/grounding-dino-base, Apache-2.0, run through transformers' own implementation) and every box is
turned into a mask by Segment Anything (ViT-B, Apache-2.0), clipped to its box (SAM spills past a small box into
its neighbours). Measured on the Raider against the hand map, each rule below earned its place:

- Candidates come from one joint query (every part's phrase in the same prompt, so the parts compete for each
  box: asked one at a time, "holster" took the knee pads and "shirt" the whole torso) and from each part's own
  prompts (the joint query never named the chest plate; "a shoulder pad" finds the shoulder plate and "a bare
  forearm" the bare skin between glove and sleeve, which the joint "forearm" box drew round the whole arm).
- A box bigger than its part can be (max_box, a fraction of the figure's bounding box) or centred outside the
  part's vertical zone (0 at the crown, 1 at the soles: belt pouches are not thigh holsters) is dropped.
- A box scoring under rel_score of an overlapping box of the same part is dropped: weak duplicates are the
  detector naming the region around the part. (Measured against the part's best box anywhere, this dropped
  shoulder plates whenever the chest plate scored high.) A part the character has one of (single: a waist
  belt, a face) keeps only its best box.
- A thin part (max_width, a fraction of the figure's height) keeps only the parts of its mask no wider than
  that: a harness box's mask is the whole harness region with the plates in it.
- A paired part (mirror) found on one side only is looked for in its mirrored box about the face's centre line,
  and kept when SAM's mask there is a similar size and colour: the detector found one pauldron of two.
- Masks are layered: the higher layer wins, so a buckle sits on a belt. A non-base part whose mask lies mostly
  inside a bigger mask of a part at most one layer above it wins there anyway: a harness box drawn round the
  whole chest otherwise swallows the plate it frames.
- Character pixels no part claims take the nearest base part (the cloth and skin everything else is worn over).
- Cloth pixels with the face's colour that touch the face or detected skin are bare skin: the neck under the
  beard is face, the forearms skin. (The colour comes from the face alone: a detected "forearm" can be a
  cloth wrap, and its colour then turned the grey sleeves to skin.)

The background is whatever matches the image's border colour, so the reference must be on a plain backdrop.
On the Raider this reaches 0.89 pixel agreement with the hand map (it was 0.55 with one query per part).

Out come, in <out>: parts.npy (H x W part names, '' for background), the projection inputs part-ids.npy (index
into part-names.json, 255 for background) and body-ids.npy (the same with equipment replaced by the body or cloth
under it, project_parts.py's prior for hidden faces), part-names.json, landmarks.json (the face box's chin row,
for a character without a beard), parts.png, review.jpg (reference, overlay with legend, and the --compare map
when given) and detections.json (every candidate, kept or why dropped).

  python scripts/auto_part_map.py <reference.png> <out-dir> [--vocab profiles/segmentation/humanoid-gear.json]
      [--detector <grounding-dino dir>] [--sam <sam_vit_b.pth>] [--compare <hand-made parts.npy>]

--detector defaults to RAC_GROUNDING_DINO, then C:/Comfy/rac-models/grounding-dino-base; --sam to
RAC_SAM_CHECKPOINT, then ComfyUI's sams folder. --compare reports per-part IoU against another part map.
"""
import argparse
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

DETECTOR = 'C:/Comfy/rac-models/grounding-dino-base'
SAM = 'C:/Comfy/ComfyUI/models/sams/sam_vit_b_01ec64.pth'
PALETTE = {"hair": (70, 35, 15), "face": (240, 180, 140), "beard": (120, 70, 40), "skin": (215, 140, 100),
           "sleeve_roll": (40, 150, 170), "jacket": (25, 140, 165), "shirt": (60, 90, 110), "plate": (215, 215, 230),
           "pouch": (230, 205, 80), "buckle": (255, 240, 120), "belt": (200, 100, 40), "strap": (205, 90, 40),
           "kneepad": (240, 115, 180), "glove": (140, 50, 155), "boot": (140, 75, 25), "boot_strap": (190, 120, 60),
           "trousers": (75, 75, 90), "thigh_pouch": (250, 170, 60)}


def foreground(rgb, tol=30.0):
    """Pixels that differ from the border's median colour, with holes inside the figure filled."""
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(float)
    bg = np.median(border, 0)
    fg = np.linalg.norm(rgb.astype(float) - bg, axis=2) > tol
    fg = ndimage.binary_opening(fg, iterations=1)
    return ndimage.binary_fill_holes(fg)


def to_lab(rgb):
    """sRGB (uint8) to CIE Lab under D65."""
    c = rgb.astype(float) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def detect(processor, detector, image, text, threshold, device):
    """Boxes, scores and text labels for one prompt."""
    import torch
    inputs = processor(images=image, text=text, return_tensors='pt').to(device)
    with torch.no_grad():
        outputs = detector(**inputs)
    res = processor.post_process_grounded_object_detection(
        outputs, inputs.input_ids, threshold=threshold, text_threshold=threshold,
        target_sizes=[image.size[::-1]])[0]
    labels = res.get('text_labels', res.get('labels'))
    return list(zip(res['boxes'].cpu().numpy(), res['scores'].cpu().numpy(), labels))


def parts_of(label, phrases):
    """The parts a joint-query label names: every part whose phrase it contains, else the one whose word comes first."""
    words = str(label).lower().split()
    full = [n for n, ph in phrases.items() if all(w in words for w in ph.split())]
    if full:
        return full
    first = {n: min(words.index(w) for w in ph.split() if w in words) for n, ph in phrases.items()
             if any(w in words for w in ph.split())}
    return [min(first, key=first.get)] if first else []


def candidates(processor, detector, image, vocab, device):
    """(part, box, score, query) from the joint query and from every part's own prompts."""
    names = list(vocab['parts'])
    floor = vocab['box_threshold']
    phrases = {n: vocab['parts'][n]['phrase'] for n in names}
    found = [(n, box, float(score), 'joint: ' + str(label)) for box, score, label in
             detect(processor, detector, image, ' . '.join(phrases.values()) + ' .', floor, device)
             for n in parts_of(label, phrases)]
    for n in names:
        for prompt in vocab['parts'][n]['prompts']:
            text = prompt.lower().rstrip('.') + '.'
            found += [(n, box, float(score), 'single: ' + prompt)
                      for box, score, _ in detect(processor, detector, image, text, floor, device)]
    return found


def select(found, vocab, fg):
    """Indices of the candidates kept, and why each other one was dropped."""
    ys, xs = np.nonzero(fg)
    figure = float((xs.max() - xs.min()) * (ys.max() - ys.min()))
    top, bottom = ys.min(), ys.max()
    dropped, kept = {}, []
    for i, (n, box, score, _) in enumerate(found):
        spec = vocab['parts'][n]
        if (box[2] - box[0]) * (box[3] - box[1]) > spec.get('max_box', 0.85) * figure:
            dropped[i] = 'box bigger than max_box'
            continue
        zone = spec.get('zone')
        centre = ((box[1] + box[3]) / 2 - top) / (bottom - top)
        if zone and not zone[0] <= centre <= zone[1]:
            dropped[i] = f'centre {centre:.2f} outside zone {zone}'
            continue
        kept.append(i)
    rel = vocab.get('rel_score', 0.6)
    weak = {}
    for i in kept:
        for j in kept:
            (pi, bi, si, _), (pj, bj, sj, _) = found[i], found[j]
            if pi != pj or si >= rel * sj:
                continue
            ix = max(0.0, min(bi[2], bj[2]) - max(bi[0], bj[0])) * max(0.0, min(bi[3], bj[3]) - max(bi[1], bj[1]))
            if ix >= 0.5 * min((bi[2] - bi[0]) * (bi[3] - bi[1]), (bj[2] - bj[0]) * (bj[3] - bj[1])):
                weak[i] = max(weak.get(i, 0.0), sj)
    for i, sj in weak.items():
        dropped[i] = f'score below {rel} of an overlapping {found[i][0]} box scoring {sj:.2f}'
    kept = [i for i in kept if i not in weak]
    # a part the character has one of keeps its best box only
    for n, spec in vocab['parts'].items():
        mine = [i for i in kept if found[i][0] == n]
        if spec.get('single') and len(mine) > 1:
            top = max(mine, key=lambda i: found[i][2])
            for i in mine:
                if i != top:
                    dropped[i] = f'{n} is single; its best box scores {found[top][2]:.2f}'
                    kept.remove(i)
    return kept, dropped


def thin(mask, width):
    """The parts of a mask no wider than width pixels: a strap's box mask is often the whole harness region."""
    r = width / 2.0
    core = ndimage.distance_transform_edt(mask) > r
    if not core.any():
        return mask
    return mask & ~(ndimage.distance_transform_edt(~core) <= r)


def mirror(found, masks, kept, vocab, sam, fg, lab):
    """Look for the other side of a paired part the detector missed: its mirrored box, kept when the mask there
    is a similar size and colour (the Raider's one shoulder plate has teal cloth opposite it, so gets no twin)."""
    H, W = fg.shape
    xs = np.nonzero(fg)[1]
    axis = (xs.min() + xs.max()) / 2.0
    face = [i for i in kept if found[i][0] == 'face']
    if face:
        b = found[face[0]][1]
        axis = (b[0] + b[2]) / 2.0
    added = []
    for i in list(kept):
        n, box, score, _ = found[i]
        if not vocab['parts'][n].get('mirror'):
            continue
        mb = np.array([2 * axis - box[2], box[1], 2 * axis - box[0], box[3]])
        if abs((mb[0] + mb[2]) / 2 - (box[0] + box[2]) / 2) < 0.5 * (box[2] - box[0]):
            continue   # straddles the centre line: it is its own mirror image

        def iou(a, b):
            ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
            return ix / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix)
        if any(found[j][0] == n and iou(found[j][1], mb) > 0.3 for j in kept + added):
            continue
        m, ms, _ = sam.predict(box=mb, multimask_output=True)
        inside = np.zeros((H, W), bool)
        x0, y0, x1, y1 = (int(round(v)) for v in mb)
        inside[max(y0, 0):y1 + 1, max(x0, 0):x1 + 1] = True
        mask = m[int(np.argmax(ms))] & fg & inside
        ratio = mask.sum() / max(masks[i].sum(), 1)
        if not 0.5 <= ratio <= 2.0:
            continue
        delta = float(np.linalg.norm(np.median(lab[mask], 0) - np.median(lab[masks[i]], 0)))
        if delta > vocab.get('mirror_delta_e', 12):
            continue
        found.append((n, mb, score * 0.9, f'mirror of candidate {i} (area x{ratio:.2f}, colour dE {delta:.1f})'))
        masks[len(found) - 1] = mask
        added.append(len(found) - 1)
    return added


def layer_keys(found, masks, kept, vocab):
    """Layer plus half the score; a non-base part nested in a bigger mask at most one layer above it wins there."""
    layer = {n: vocab['parts'][n]['layer'] for n in vocab['parts']}
    key = {i: layer[found[i][0]] + 0.5 * found[i][2] for i in kept}
    area = {i: int(masks[i].sum()) for i in kept}
    for _ in range(3):
        for a in kept:
            for b in kept:
                pa, pb = found[a][0], found[b][0]
                if pa == pb or pb in vocab['base'] or area[a] < 1.25 * area[b] or layer[pb] < layer[pa] - 1:
                    continue
                if key[b] <= key[a] and (masks[a] & masks[b]).sum() >= 0.8 * area[b]:
                    key[b] = key[a] + 0.01
    return key


def bare_skin(part, lab, vocab):
    """Cloth pixels with the face's colour that touch the face or detected skin become face (near it) or skin."""
    rule = vocab.get('bare_skin')
    face = part == 'face'
    if not rule or face.sum() < 200:
        return 0
    skin = part == 'skin'
    ref = np.median(lab[ndimage.binary_erosion(face, iterations=3) if face.sum() > 2000 else face], 0)
    dist = np.linalg.norm(lab - ref, axis=2)
    cand = ndimage.binary_opening(np.isin(part, rule['over']) & (dist < rule['max_delta_e']), iterations=2)
    regions, k = ndimage.label(cand)
    seed = ndimage.binary_dilation(face | skin, iterations=4)
    near_face = ndimage.binary_dilation(face, iterations=4)
    moved = 0
    for j in range(1, k + 1):
        c = regions == j
        if c.sum() < rule.get('min_px', 300) or not (c & seed).any():
            continue
        part[c] = 'face' if (c & near_face).any() else 'skin'
        moved += int(c.sum())
    return moved


def overlay(rgb, part):
    """The reference dimmed, each part tinted with its palette colour."""
    vis = rgb.astype(float) * 0.35
    for n in np.unique(part):
        if n:
            vis[part == n] = rgb[part == n] * 0.35 + np.array(PALETTE.get(n, (255, 0, 255))) * 0.65
    return vis.astype(np.uint8)


def review_sheet(rgb, tiles, path):
    """Reference, then each (title, part map) as an overlay with its legend."""
    try:
        font, small = ImageFont.truetype('arial.ttf', 30), ImageFont.truetype('arial.ttf', 22)
    except OSError:
        font = small = ImageFont.load_default()
    H, W = rgb.shape[:2]
    lw = 230
    panels = [('Reference', rgb, [])] + [(t, overlay(rgb, m), sorted(set(np.unique(m)) - {''})) for t, m in tiles]
    sheet = Image.new('RGB', (len(panels) * (W + lw), H + 60), (24, 24, 28))
    d = ImageDraw.Draw(sheet)
    for i, (title, img, names) in enumerate(panels):
        x = i * (W + lw)
        sheet.paste(Image.fromarray(img), (x, 60))
        d.text((x + 10, 12), title, fill=(240, 240, 240), font=font)
        for k, n in enumerate(names):
            y = 80 + k * 34
            d.rectangle([x + W + 10, y, x + W + 36, y + 26], fill=PALETTE.get(n, (255, 0, 255)))
            d.text((x + W + 44, y), n, fill=(230, 230, 230), font=small)
    sheet.thumbnail((2600, 2600))
    sheet.save(path, quality=90)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('reference', type=Path)
    ap.add_argument('out', type=Path)
    ap.add_argument('--vocab', type=Path,
                    default=Path(__file__).resolve().parents[1] / 'profiles/segmentation/humanoid-gear.json')
    ap.add_argument('--detector', default=os.environ.get('RAC_GROUNDING_DINO', DETECTOR))
    ap.add_argument('--sam', default=os.environ.get('RAC_SAM_CHECKPOINT', SAM))
    ap.add_argument('--compare', type=Path)
    args = ap.parse_args()
    import torch
    from segment_anything import SamPredictor, sam_model_registry
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    vocab = json.loads(args.vocab.read_text())
    image = Image.open(args.reference).convert('RGB')
    rgb = np.asarray(image)
    H, W = rgb.shape[:2]
    fg = foreground(rgb)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    processor = AutoProcessor.from_pretrained(args.detector)
    detector = AutoModelForZeroShotObjectDetection.from_pretrained(args.detector, use_safetensors=True).to(device)
    found = candidates(processor, detector, image, vocab, device)
    del detector
    kept, dropped = select(found, vocab, fg)
    ys = np.nonzero(fg)[0]
    figure_h = float(ys.max() - ys.min())

    sam = SamPredictor(sam_model_registry['vit_b'](checkpoint=args.sam).to(device))
    sam.set_image(rgb)
    masks = {}
    for i in kept:
        box = found[i][1]
        m, mscores, _ = sam.predict(box=np.asarray(box, float), multimask_output=True)
        # SAM can spill past the box it was given; a part stays inside its own box
        inside = np.zeros((H, W), bool)
        x0, y0, x1, y1 = (int(round(v)) for v in box)
        inside[max(y0, 0):y1 + 1, max(x0, 0):x1 + 1] = True
        masks[i] = m[int(np.argmax(mscores))] & fg & inside
    kept = [i for i in kept if masks[i].any()]
    lab = to_lab(rgb)
    kept += mirror(found, masks, kept, vocab, sam, fg, lab)
    # nesting is judged on the whole masks (a plate inside the harness region), painting uses the thinned ones:
    # thinned first, the harness's slivers along the shoulder plate's rim no longer contained it and won there
    key = layer_keys(found, masks, kept, vocab)
    for i in kept:
        width = vocab['parts'][found[i][0]].get('max_width')
        if width:
            masks[i] = thin(masks[i], width * figure_h)

    best = np.full((H, W), -1.0)
    part = np.full((H, W), '', dtype='U12')
    claimed = {}
    for i in kept:
        take = masks[i] & (key[i] > best)
        part[take] = found[i][0]
        best[take] = key[i]
    for i in kept:
        claimed[i] = int((masks[i] & (best == key[i]) & (part == found[i][0])).sum())

    # character pixels nobody claimed take the nearest base part
    base = np.isin(part, vocab['base'])
    open_px = fg & (part == '')
    if base.any() and open_px.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~base, return_indices=True)
        part[open_px] = part[iy[open_px], ix[open_px]]
    part[~fg] = ''
    skin_px = bare_skin(part, lab, vocab)
    for n, spec in vocab['parts'].items():
        if spec.get('as'):
            part[part == n] = spec['as']

    args.out.mkdir(parents=True, exist_ok=True)
    np.save(args.out / 'parts.npy', part)
    names = sorted(set(np.unique(part)) - {''})
    ids = np.full((H, W), 255, np.uint8)
    for k, n in enumerate(names):
        ids[part == n] = k
    np.save(args.out / 'part-ids.npy', ids)
    # project_parts.py's prior for hidden faces: the equipment taken off, the body or cloth under it showing
    body = np.isin(part, vocab['body'])
    body_ids = ids.copy()
    hide = fg & ~body
    if body.any() and hide.any():
        _, (iy, ix) = ndimage.distance_transform_edt(~body, return_indices=True)
        body_ids[hide] = ids[iy[hide], ix[hide]]
    np.save(args.out / 'body-ids.npy', body_ids)
    (args.out / 'part-names.json').write_text(json.dumps(names))
    # the chin for project_parts.py on a character without a beard: the bottom of the face box
    face = [i for i in kept if found[i][0] == 'face']
    ys_fg = np.nonzero(fg)[0]
    landmarks = {'figure_top_row': int(ys_fg.min()), 'figure_bottom_row': int(ys_fg.max())}
    if face:
        landmarks['chin_row'] = int(round(float(found[face[0]][1][3])))
    (args.out / 'landmarks.json').write_text(json.dumps(landmarks, indent=1))
    vis = np.full((H, W, 3), 90, np.uint8)
    for n in names:
        vis[part == n] = PALETTE.get(n, (255, 0, 255))
    Image.fromarray(vis).save(args.out / 'parts.png')

    records = []
    for i, (n, box, score, query) in enumerate(found):
        rec = {'part': n, 'query': query, 'score': round(score, 3), 'box': [round(float(v)) for v in box]}
        if i in dropped:
            rec['dropped'] = dropped[i]
        elif i not in masks or not masks[i].any():
            rec['dropped'] = 'empty mask'
        else:
            rec.update(mask_px=int(masks[i].sum()), kept_px=claimed[i], key=round(key[i], 3))
        records.append(rec)
    report = {'reference': str(args.reference), 'vocab': str(args.vocab), 'detector': args.detector, 'sam': args.sam,
              'pixels': {n: int((part == n).sum()) for n in names}, 'foreground_px': int(fg.sum()),
              'bare_skin_px': skin_px, 'candidates': records}
    tiles = [('Auto part map', part)]
    if args.compare:
        ref = np.load(args.compare)
        if ref.shape != part.shape:
            raise SystemExit(f'compare map is {ref.shape}, this one {part.shape}')
        iou = {}
        for n in sorted((set(np.unique(ref)) | set(names)) - {''}):
            a, b = ref == n, part == n
            union = (a | b).sum()
            iou[n] = round(float((a & b).sum() / union), 3) if union else None
        both = (ref != '') & (part != '')
        report['compare'] = {'map': str(args.compare), 'iou': iou,
                             'pixel_agreement': round(float((ref[both] == part[both]).mean()), 3)}
        print('COMPARE agreement', report['compare']['pixel_agreement'], json.dumps(iou))
        tiles.append(('Compared map', ref))
    review_sheet(rgb, tiles, args.out / 'review.jpg')
    (args.out / 'detections.json').write_text(json.dumps(report, indent=1))
    print('AUTO_PART_MAP_OK', args.out, report['pixels'])


if __name__ == '__main__':
    main()
