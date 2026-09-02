"""Split an equal-width front/left/back turnaround into square conditioning views.

The split is deterministic and records every source/crop/output hash. It does
not claim the generated side and back are source truth; callers must label them
as secondary depth guidance while retaining the supplied primary authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def square_panel(panel: Image.Image, size: int) -> Image.Image:
    panel = panel.convert("RGB")
    scale = min(size / panel.width, size / panel.height)
    resized = panel.resize(
        (round(panel.width * scale), round(panel.height * scale)),
        Image.Resampling.LANCZOS,
    )
    background = Image.new("RGB", (size, size), (235, 235, 235))
    background.paste(
        resized,
        ((size - resized.width) // 2, (size - resized.height) // 2),
    )
    return background


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--primary-source", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1024)
    parser.add_argument("--gutter", type=int, default=24,
                        help="pixels trimmed from both sides of each panel boundary")
    args = parser.parse_args()

    sheet = args.sheet.resolve()
    primary = args.primary_source.resolve()
    if not sheet.is_file() or not primary.is_file():
        raise ValueError("sheet and primary source must both exist")
    output = args.output_directory.resolve()
    if output.exists():
        raise ValueError(f"refusing to overwrite turnaround directory: {output}")
    output.mkdir(parents=True)

    image = Image.open(sheet).convert("RGB")
    edges = [round(image.width * i / 3) for i in range(4)]
    views = []
    for index, name in enumerate(("front", "left", "back")):
        box = (
            edges[index] + args.gutter,
            0,
            edges[index + 1] - args.gutter,
            image.height,
        )
        path = output / f"{name}.png"
        square_panel(image.crop(box), args.size).save(path)
        views.append({
            "view": name,
            "role": "generated_turnaround_guidance",
            "crop_box": list(box),
            "path": str(path),
            "sha256": sha256(path),
        })

    report = {
        "schema": "reference-asset-compiler.generated-turnaround-lineage.v1",
        "asset_id": args.asset_id,
        "primary_authority": {
            "path": str(primary),
            "sha256": sha256(primary),
            "role": "artistic_authority",
        },
        "generated_sheet": {
            "path": str(sheet),
            "sha256": sha256(sheet),
            "size": list(image.size),
            "role": "AI-derived multiview depth guidance",
        },
        "views": views,
        "policy": "The supplied primary image controls identity and visible construction. Generated side/back panels are secondary depth guidance and may not override it.",
    }
    report_path = output / "turnaround-lineage.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"RAC_TURNAROUND_SPLIT_OK {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
