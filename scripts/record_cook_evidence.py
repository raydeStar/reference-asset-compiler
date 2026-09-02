"""Record clean cook/package/run evidence and the reviewed packaged frame."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.runtime_evidence import record_cook_stage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", help="source asset id, without -production")
    parser.add_argument("--gallery-report", type=Path, required=True)
    parser.add_argument("--cook-log", type=Path, required=True)
    parser.add_argument("--package-log", type=Path, required=True)
    parser.add_argument("--runtime-log", type=Path, required=True)
    parser.add_argument("--runtime-frame", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--approved-by", required=True)
    args = parser.parse_args()
    production_id = args.asset + "-production"
    manifest = ROOT / "out" / production_id / (production_id + ".ue5import.json")
    try:
        output, audit = record_cook_stage(
            ROOT / "work" / args.asset,
            manifest,
            args.gallery_report,
            args.cook_log,
            args.package_log,
            args.runtime_log,
            args.runtime_frame,
            args.package_root,
            args.approved_by,
        )
    except (OSError, KeyError, ValueError) as error:
        print("RAC_COOK_EVIDENCE_REFUSED {0}".format(error))
        return 2
    print("RAC_PRODUCTION_READY {0} {1}".format(audit["asset_id"], output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
