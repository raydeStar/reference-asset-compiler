"""Record native UE animation checks and human-reviewed motion frames."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.articulated_evidence import (  # noqa: E402
    record_ue5_motion_review_stage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", help="source asset id, without -production")
    parser.add_argument("--motion-report", type=Path, required=True)
    parser.add_argument("--frame", type=Path, action="append", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--note", required=True)
    args = parser.parse_args()
    production_id = args.asset + "-production"
    manifest = ROOT / "out" / production_id / (production_id + ".ue5import.json")
    try:
        output = record_ue5_motion_review_stage(
            ROOT / "work" / args.asset, manifest, args.motion_report, args.frame,
            args.approved_by, args.note)
    except (OSError, KeyError, ValueError) as error:
        print("RAC_UE5_MOTION_REVIEW_REFUSED {0}".format(error))
        return 2
    print("RAC_UE5_MOTION_REVIEW_OK {0}".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
