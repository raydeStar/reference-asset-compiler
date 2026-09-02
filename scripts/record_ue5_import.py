"""Record one immutable, manifest-bound UE import result in its workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reference_asset_compiler.runtime_evidence import record_ue5_import_stage  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", help="source asset id, without -production")
    parser.add_argument("--report", type=Path, default=ROOT / "work" / "ue5-verify.json")
    args = parser.parse_args()
    job = ROOT / "work" / args.asset
    production_id = args.asset + "-production"
    manifest = ROOT / "out" / production_id / (production_id + ".ue5import.json")
    try:
        output = record_ue5_import_stage(job, manifest, args.report)
    except (OSError, KeyError, ValueError) as error:
        print("RAC_UE5_IMPORT_EVIDENCE_REFUSED {0}".format(error))
        return 2
    print("RAC_UE5_IMPORT_EVIDENCE_OK {0}".format(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
