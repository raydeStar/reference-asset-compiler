"""CPU-only atmosphere planning and portable, pending-approval scene reviews."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_asset_compiler.scene_tools import (  # noqa: E402
    bundle_scene_review, plan_atmosphere, read_utf8,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Validate recipe and show UE values; no editor/GPU")
    plan.add_argument("recipe", type=Path)
    bundle = commands.add_parser("bundle", help="Rehash existing evidence and build portable review")
    bundle.add_argument("receipt", type=Path)
    bundle.add_argument("--root", type=Path, required=True)
    bundle.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            print(json.dumps(plan_atmosphere(read_utf8(args.recipe)), indent=2))
        else:
            result = bundle_scene_review(args.receipt.resolve(), args.root, args.output)
            print("SCENE_REVIEW_READY {0}: {1} frames, human approval PENDING -- the guest decides.".format(
                args.output, len(result["frames"])))
    except (ValueError, OSError, TypeError, KeyError) as error:
        print("SCENE_TOOLS_REFUSED: {0} -- the butler keeps the receipts.".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
