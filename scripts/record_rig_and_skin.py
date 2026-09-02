"""Record a profile-gated rigged FBX bound to the exact approved mesh."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.articulated_evidence import (  # noqa: E402
    record_rig_and_skin_stage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset")
    parser.add_argument("--approved-mesh", type=Path, required=True)
    parser.add_argument("--rigged-fbx", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--gate-report", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = record_rig_and_skin_stage(
            ROOT / "work" / args.asset, args.approved_mesh, args.rigged_fbx,
            args.profile, args.gate_report)
    except (OSError, KeyError, ValueError) as error:
        print("RAC_RIG_AND_SKIN_REFUSED {0}".format(error))
        return 2
    print("RAC_RIG_AND_SKIN_OK {0} -- the bones have papers, not merely posture.".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
