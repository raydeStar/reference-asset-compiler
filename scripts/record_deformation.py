"""Record the complete numeric deformation suite and its fixed pose renders."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.articulated_evidence import (  # noqa: E402
    record_deformation_stage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset")
    parser.add_argument("--rigged-fbx", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--renders", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = record_deformation_stage(
            ROOT / "work" / args.asset, args.rigged_fbx, args.report, args.renders)
    except (OSError, KeyError, ValueError) as error:
        print("RAC_DEFORMATION_REFUSED {0}".format(error))
        return 2
    print("RAC_DEFORMATION_OK {0} -- five poses testified under oath.".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
