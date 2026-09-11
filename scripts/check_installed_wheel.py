"""Exercise the shipped CLI in a fresh environment outside the source checkout."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import venv


def check_wheel(wheel: Path) -> dict:
    wheel = wheel.resolve()
    with tempfile.TemporaryDirectory(prefix="rac-wheel-smoke-") as raw:
        root = Path(raw)
        environment = root / "environment"
        venv.EnvBuilder(with_pip=True).create(environment)
        bins = environment / ("Scripts" if os.name == "nt" else "bin")
        python = bins / ("python.exe" if os.name == "nt" else "python")
        rac = bins / ("rac.exe" if os.name == "nt" else "rac")
        env = dict(os.environ)
        for key in ("PYTHONPATH", "PYTHONHOME"):
            env.pop(key, None)

        def run(args, expected=0, timeout=90):
            result = subprocess.run([str(v) for v in args], cwd=root, env=env,
                                    capture_output=True, text=True, errors="replace",
                                    timeout=timeout)
            if result.returncode != expected:
                raise RuntimeError(f"Installed CLI check failed ({result.returncode}): {args}\n"
                                   f"{result.stdout}\n{result.stderr}")
            return result

        # Install declared runtime dependencies too, with no inherited editable install.
        # numpy, Pillow and scipy come from the index on a cold cache; 90 s is the
        # budget for the CLI calls below, not for a download.
        run([python, "-m", "pip", "install", wheel], timeout=600)
        location = run([python, "-I", "-c", "import reference_asset_compiler as p; "
                        "from importlib.metadata import version; "
                        "assert p.__version__ == version('reference-asset-compiler'); "
                        "print(p.__file__)"]).stdout.strip()
        if not Path(location).resolve().is_relative_to(environment.resolve()):
            raise RuntimeError("Wheel check imported from outside its isolated environment")
        run([rac, "--help"])
        manifest = root / "intake.json"
        manifest.write_text(json.dumps({"asset_id": "wheel-canary", "asset_kind": "static_prop",
                                        "articulation": "static"}), encoding="utf-8")
        routing = json.loads(run([rac, "plan", manifest]).stdout)
        if "cook" not in routing["stages"] or routing["articulated"]:
            raise RuntimeError("Installed planner returned an incorrect static pipeline")
        reference = root / "reference.png"
        reference.write_bytes(b"wheel-intake-fixture")
        run([rac, "new", "wheel-canary", reference, "--kind", "static_prop",
             "--workspace-root", root / "jobs"])
        audit = json.loads(run([rac, "audit", root / "jobs/wheel-canary"]).stdout)
        if not audit["ok"] or audit["production_ready"]:
            raise RuntimeError("Installed audit misclassified an incomplete workspace")
        missing_checkout = run([rac, "geometry-preflight", "request.json", "--legacy-root", "studio"], 2)
        if "--repo-root" not in missing_checkout.stderr:
            raise RuntimeError("Installed geometry preflight did not explain its checkout requirement")
        return {"ok": True, "wheel": wheel.name, "isolated_install": True,
                "checks": ["help", "plan", "new", "audit", "checkout-required-error"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(check_wheel(args.wheel), indent=2))
    print("RAC_INSTALLED_WHEEL_OK -- the suitcase contains the spellbook.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
