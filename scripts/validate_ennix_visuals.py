"""Retain a source overlay and honest silhouette gate for an Ennix review."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def main():
    p = argparse.ArgumentParser()
    p.add_argument("reference", help="original full illustration")
    p.add_argument("reference_mask", help="retained segmented front RGBA")
    p.add_argument("render", help="registered transparent front render")
    p.add_argument("out")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    source = Image.open(a.reference).convert("RGB")
    ref = np.asarray(Image.open(a.reference_mask).convert("RGBA"))[:, :, 3] > 127
    candidate = Image.open(a.render).convert("RGBA")
    mask = np.asarray(candidate)[:, :, 3] > 127
    if source.size != candidate.size or mask.shape != ref.shape:
        raise ValueError("Registration size differs; do not resize a candidate into a passing gate")
    iou = float(np.logical_and(ref, mask).sum() / np.logical_or(ref, mask).sum())

    def bounds(m):
        y, x = np.nonzero(m)
        box = [int(x.min()), int(y.min()), int(x.max()), int(y.max())]
        return box, [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]

    rb, rc = bounds(ref)
    cb, cc = bounds(mask)
    distance = float(np.linalg.norm(np.array(rc) - cc))
    background = Image.new("RGBA", source.size, (235, 233, 230, 255))
    background.alpha_composite(candidate)
    Image.blend(source, background.convert("RGB"), .5).save(out / "front_overlay_reference.png")
    colour = np.zeros((*mask.shape, 3), dtype=np.uint8)
    colour[ref & mask] = (125, 150, 130)
    colour[ref & ~mask] = (45, 180, 240)
    colour[mask & ~ref] = (255, 90, 75)
    Image.fromarray(colour).save(out / "front_mask_difference.png")
    report = {"sources": {name: {"path": str(Path(path).resolve()), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        for name, path in (("original", a.reference), ("segmented_reference", a.reference_mask), ("render", a.render))},
        "front_mask_iou": iou, "front_mask_iou_min": .90,
        "reference_bbox": rb, "render_bbox": cb, "bbox_center_distance_px": distance,
        "bbox_center_tolerance_px": 12, "ok": iou >= .90 and distance <= 12,
        "production_ready": False,
        "note": "Fixed source registration; no silhouette-fitting resize. The illustration is not a calibrated orthographic scan. Human likeness review remains required."}
    (out / "front_mask_validation.json").write_text(json.dumps(report, indent=2))
    board = Image.new("RGB", (source.width * 2, source.height + 50), (25, 29, 33))
    board.paste(source, (0, 50))
    board.paste(background.convert("RGB"), (source.width, 50))
    draw = ImageDraw.Draw(board)
    draw.text((20, 18), "ORIGINAL ILLUSTRATION", fill="white")
    draw.text((source.width + 20, 18), f"REBUILT CANDIDATE | silhouette IoU {iou:.3f} / 0.900 required | HUMAN REVIEW PENDING", fill="white")
    board.save(out / "reference-comparison.png")
    print(f"The mirror remains candid, sir: IoU {iou:.4f}; gate {'PASS' if report['ok'] else 'FAIL'}.")


if __name__ == "__main__":
    main()
