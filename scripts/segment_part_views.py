"""Label the pixels of pictures of a model by part: Grounding DINO boxes, Segment Anything masks.

Run with a Python that has torch, transformers and segment_anything (ComfyUI's
portable one has them); `label_parts.py` does that for you. The models are
Grounding DINO (IDEA-Research/grounding-dino-base, Apache-2.0) and SAM ViT-B
(Apache-2.0), as in `auto_part_map.py`.

The vocabulary names a base part (what is left when nothing else is found:
the hull of a boat) and the parts to look for, each with its phrases. On the
skiff, measured over 24 renders, each rule below earned its place:

- A box is judged against the model's own extent in the picture, not the
  picture's: a small part's phrase ("iron strap", "wooden pole") also matches
  the whole boat, and the whole boat filled only a fifth of a render, so a
  limit taken against the picture kept it and the part swallowed the boat.
  `max_box` is the largest share of the model's box a part's box may take.
- Parts compete for a box. Where boxes of two parts cover the same region
  (IoU above 0.6) the better score keeps it: the fin's pole was found as
  "wooden pole" and as "red fin", and the strut otherwise painted over a fin.
- Masks are resolved pixel by pixel by strength (detector score times SAM's
  own score), not by the order parts are listed in, and each mask is clipped
  to its box and to the model.
- Parts that do not separate in the pictures belong with the base: on the
  skiff the struts and iron straps are found unreliably, and are painted with
  the hull. Only parts the detector finds in most views go in a vocabulary.

  python segment_part_views.py <views dir> <vocab.json> [--pictures <png> ...] \\
      [--detector <grounding-dino dir>] [--sam <sam_vit_b.pth>]

With --pictures, labels those pictures (the reference) instead of the views;
the model is the picture's alpha, or every pixel unlike the corners' colour.
Writes <stem>-labels.npy (uint8 part index, 255 background), <stem>-score.npy
and <stem>-labels.png (an overlay to review) beside the views, or for pictures
into <views dir>, and labels.json / picture-labels.json (every box: kept, or
why dropped).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

DETECTOR = "C:/Comfy/rac-models/grounding-dino-base"
SAM = "C:/Comfy/ComfyUI/models/sams/sam_vit_b_01ec64.pth"
RIVALRY_IOU = 0.6


def iou(a, b) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    area = lambda r: max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])  # noqa: E731
    return inter / max(area(a) + area(b) - inter, 1e-9)


def model_box(foreground: np.ndarray):
    rows, columns = np.nonzero(foreground)
    if not len(rows):
        return None
    return [int(columns.min()), int(rows.min()), int(columns.max()) + 1, int(rows.max()) + 1]


def judge_boxes(candidates, parts, figure):
    """Keep the boxes a part can be, then let parts compete for the same region.

    `candidates` are dicts with index (into parts), score and box; `figure` is
    the model's box in the picture. Returns (kept, dropped), each box with its
    share of the model and, when dropped, why.
    """
    area = max((figure[2] - figure[0]) * (figure[3] - figure[1]), 1)
    kept, dropped = [], []
    viable = []
    for entry in candidates:
        x0, y0, x1, y1 = entry["box"]
        entry["share_of_model"] = round((x1 - x0) * (y1 - y0) / area, 4)
        limit = parts[entry["index"]].get("max_box", 0.3)
        if entry["share_of_model"] > limit:
            entry["dropped"] = "box covers {0:.0%} of the model; a {1} is at most {2:.0%}".format(
                entry["share_of_model"], parts[entry["index"]]["name"], limit)
            dropped.append(entry)
        else:
            viable.append(entry)
    for entry in sorted(viable, key=lambda e: -e["score"]):
        rival = next((k for k in kept if k["index"] != entry["index"]
                      and iou(k["box"], entry["box"]) > RIVALRY_IOU), None)
        if rival is None:
            kept.append(entry)
        else:
            entry["dropped"] = "lost the region to {0} ({1:.2f} against {2:.2f})".format(
                parts[rival["index"]]["name"], rival["score"], entry["score"])
            dropped.append(entry)
    return kept, dropped


def resolve(masks, base: int, foreground: np.ndarray):
    """One label a pixel: the strongest mask over it, the base where none is, 255 off the model.

    `masks` is a list of (index, strength, bool mask). Returns (labels, strength).
    """
    best = np.zeros(foreground.shape, dtype=np.float32)
    labels = np.full(foreground.shape, base, dtype=np.uint8)
    for index, strength, mask in masks:
        take = mask & foreground & (strength > best)
        labels[take] = index
        best[take] = strength
    labels[~foreground] = 255
    best[~foreground] = 0
    return labels, best


def picture_foreground(image: Image.Image) -> np.ndarray:
    if image.mode == "RGBA":
        alpha = np.asarray(image)[..., 3]
        if (alpha < 250).mean() > 0.001:
            return alpha > 127
    rgb = np.asarray(image.convert("RGB")).astype(np.int16)
    corner = np.median(np.concatenate([rgb[:8, :8].reshape(-1, 3), rgb[:8, -8:].reshape(-1, 3),
                                       rgb[-8:, :8].reshape(-1, 3), rgb[-8:, -8:].reshape(-1, 3)]), axis=0)
    return np.abs(rgb - corner).max(axis=-1) > 18


def overlay(rgb, labels, kept, parts, path):
    out = rgb.astype(np.float32).copy()
    for index, part in enumerate(parts):
        colour = np.array(part.get("colour", (200, 200, 200)), dtype=np.float32)
        out[labels == index] = out[labels == index] * 0.45 + colour * 0.55
    picture = Image.fromarray(out.astype(np.uint8))
    draw = ImageDraw.Draw(picture)
    for entry in kept:
        draw.rectangle(entry["box"], outline=tuple(parts[entry["index"]].get("colour", (0, 0, 0))), width=3)
    scale = 512 / max(picture.size)
    picture.resize((round(picture.size[0] * scale), round(picture.size[1] * scale))).save(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("views", type=Path)
    parser.add_argument("vocab", type=Path)
    parser.add_argument("--pictures", type=Path, nargs="*", default=[])
    parser.add_argument("--detector", default=os.environ.get("RAC_GROUNDING_DINO", DETECTOR))
    parser.add_argument("--sam", default=os.environ.get("RAC_SAM_CHECKPOINT", SAM))
    args = parser.parse_args(argv)

    import torch  # noqa: PLC0415 -- only the segmenting Python has these
    from segment_anything import SamPredictor, sam_model_registry  # noqa: PLC0415
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor  # noqa: PLC0415

    parts = json.loads(args.vocab.read_text(encoding="utf-8"))["parts"]
    base = next(i for i, part in enumerate(parts) if part.get("base"))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor = AutoProcessor.from_pretrained(args.detector)
    detector = AutoModelForZeroShotObjectDetection.from_pretrained(args.detector, use_safetensors=True).to(device)
    sam = SamPredictor(sam_model_registry["vit_b"](checkpoint=args.sam).to(device))

    def detect(image, phrases, threshold):
        inputs = processor(images=image, text=". ".join(phrases) + ".", return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = detector(**inputs)
        result = processor.post_process_grounded_object_detection(
            outputs, inputs.input_ids, threshold=threshold, text_threshold=threshold,
            target_sizes=[image.size[::-1]])[0]
        names = result.get("text_labels", result.get("labels"))
        return [(box.tolist(), float(score), str(text))
                for box, score, text in zip(result["boxes"], result["scores"], names)]

    def label(image, foreground):
        rgb = np.asarray(image)
        figure = model_box(foreground)
        candidates = []
        for index, part in enumerate(parts):
            if part.get("base"):
                continue
            for box, score, text in detect(image, part["prompts"], part.get("threshold", 0.3)):
                candidates.append({"index": index, "part": part["name"], "text": text,
                                   "score": round(score, 4), "box": [round(v, 1) for v in box]})
        kept, dropped = judge_boxes(candidates, parts, figure)
        sam.set_image(rgb)
        masks = []
        for entry in kept:
            x0, y0, x1, y1 = entry["box"]
            found, scores, _ = sam.predict(box=np.asarray(entry["box"], float), multimask_output=True)
            mask = found[int(np.argmax(scores))]
            clip = np.zeros_like(mask)
            clip[int(y0):int(y1) + 1, int(x0):int(x1) + 1] = True
            mask &= clip
            entry["pixels"] = int((mask & foreground).sum())
            masks.append((entry["index"], entry["score"] * float(np.max(scores)), mask))
        labels, strength = resolve(masks, base, foreground)
        return labels, strength, kept, dropped

    found = {}
    if args.pictures:
        for picture in args.pictures:
            image = Image.open(picture)
            foreground = picture_foreground(image)
            image = image.convert("RGB")
            labels, strength, kept, dropped = label(image, foreground)
            stem = args.views / picture.stem
            np.save(str(stem) + "-labels.npy", labels)
            np.save(str(stem) + "-score.npy", strength)
            overlay(np.asarray(image), labels, kept, parts, str(stem) + "-labels.png")
            found[picture.name] = {"kept": kept, "dropped": dropped}
            print("[SEGMENT] {0}: {1}".format(picture.name, {p["name"]: int((labels == i).sum())
                                                              for i, p in enumerate(parts)}), flush=True)
        (args.views / "picture-labels.json").write_text(json.dumps({"parts": parts, "pictures": found}, indent=1),
                                                        encoding="utf-8")
        return 0

    meta = json.loads((args.views / "views.json").read_text(encoding="utf-8"))
    for record in meta["views"]:
        number = record["view"]
        image = Image.open(args.views / "view-{0:02d}.png".format(number)).convert("RGB")
        faces = np.load(args.views / "view-{0:02d}-faces.npy".format(number))
        id_size = faces.shape[0]
        foreground = np.asarray(Image.fromarray((faces >= 0).astype(np.uint8) * 255).resize(
            image.size, Image.NEAREST)) > 0
        labels, strength, kept, dropped = label(image, foreground)
        np.save(args.views / "view-{0:02d}-labels.npy".format(number),
                np.asarray(Image.fromarray(labels).resize((id_size, id_size), Image.NEAREST)))
        np.save(args.views / "view-{0:02d}-score.npy".format(number),
                np.asarray(Image.fromarray(strength).resize((id_size, id_size), Image.NEAREST)))
        overlay(np.asarray(image), labels, kept, parts, args.views / "view-{0:02d}-labels.png".format(number))
        found[number] = {"kept": kept, "dropped": dropped}
        print("[SEGMENT] view {0}: {1}".format(number, {p["name"]: int((labels == i).sum())
                                                       for i, p in enumerate(parts)}), flush=True)
    (args.views / "labels.json").write_text(json.dumps({"parts": parts, "views": found}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
