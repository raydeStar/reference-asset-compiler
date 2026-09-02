"""Record an identified human review of one imported asset in the UE gallery."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.runtime_evidence import record_runtime_review_stage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", help="source asset id, without -production")
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--gallery-report", type=Path, default=ROOT / "work" / "ue5-gallery.json")
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    production_id = args.asset + "-production"
    manifest = ROOT / "out" / production_id / (production_id + ".ue5import.json")
    try:
        output = record_runtime_review_stage(
            ROOT / "work" / args.asset,
            manifest,
            args.gallery_report,
            args.screenshot,
            args.approved_by,
            args.note,
        )
    except (OSError, KeyError, ValueError) as error:
        print("RAC_RUNTIME_REVIEW_REFUSED {0}".format(error))
        return 2
    print("RAC_RUNTIME_REVIEW_OK {0}".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
