"""Create immutable side-by-side source/candidate review plates and a hash manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler.io import sha256_file

VIEWS = ("front", "three-quarter", "side", "back")


def labeled_panel(image: Image.Image, label: str, width: int) -> Image.Image:
    source = image.convert("RGB")
    height = round(source.height * width / source.width)
    source = source.resize((width, height), Image.Resampling.LANCZOS)
    panel = Image.new("RGB", (width, height + 52), (28, 28, 30))
    panel.paste(source, (0, 52))
    draw = ImageDraw.Draw(panel)
    draw.text((18, 16), label, fill=(240, 240, 242), font=ImageFont.load_default(size=20))
    return panel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("authority_views", type=Path)
    parser.add_argument("candidate_views", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--panel-width", type=int, default=900)
    parser.add_argument("--wireframe-views", type=Path)
    args = parser.parse_args()
    authority_dir = args.authority_views.resolve()
    candidate_dir = args.candidate_views.resolve()
    output_dir = args.output_directory.resolve()
    if output_dir.exists():
        raise RuntimeError("Refusing to overwrite retopology review evidence")
    output_dir.mkdir(parents=True)
    records = []
    for view in VIEWS:
        authority = authority_dir / "matcap-{0}.png".format(view)
        candidate = candidate_dir / "matcap-{0}.png".format(view)
        if not authority.is_file() or not candidate.is_file():
            raise FileNotFoundError("Missing fixed-view pair for {0}".format(view))
        with Image.open(authority) as authority_image, Image.open(candidate) as candidate_image:
            left = labeled_panel(authority_image, "APPROVED AI AUTHORITY", args.panel_width)
            right = labeled_panel(candidate_image, "RETOPOLOGY CHALLENGER", args.panel_width)
        height = max(left.height, right.height)
        plate = Image.new("RGB", (left.width + right.width, height), (18, 18, 20))
        plate.paste(left, (0, 0))
        plate.paste(right, (left.width, 0))
        output = output_dir / "compare-{0}.png".format(view)
        plate.save(output, optimize=True)
        records.append(
            {
                "view": view,
                "authority": {"path": str(authority), "sha256": sha256_file(authority)},
                "candidate": {"path": str(candidate), "sha256": sha256_file(candidate)},
                "comparison": {"path": str(output), "sha256": sha256_file(output)},
            }
        )
    topology_records = []
    if args.wireframe_views:
        wireframe_dir = args.wireframe_views.resolve()
        topology_dir = output_dir / "topology-views"
        topology_dir.mkdir()
        for view in VIEWS:
            source = wireframe_dir / "beauty-{0}.png".format(view)
            if not source.is_file():
                raise FileNotFoundError("Missing wireframe view for {0}".format(view))
            output = topology_dir / "wireframe-{0}.png".format(view)
            shutil.copy2(source, output)
            topology_records.append(
                {"view": output.name, "path": str(output), "sha256": sha256_file(output)}
            )
    manifest = {
        "schema": "reference-asset-compiler.retopology-review-bundle.v1",
        "decision": "pending_human_review",
        "comparisons": records,
        "topology_views": topology_records,
        "review_questions": [
            "Does the candidate retain the approved silhouette in all four views?",
            "Are hair, face, scarf, pockets, cuffs, hands, and boots acceptably retained?",
            "Is the topology suitable to advance to UV/bake and later deformation testing?",
        ],
        "production_grade": False,
    }
    manifest_path = output_dir / "review-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("RAC_RETOPOLOGY_REVIEW_BUNDLE_OK {0}".format(manifest_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
