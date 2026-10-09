"""grow_hair_groom.py's --cap-front-inset on a real conformed head (RAC_BLENDER and a frozen bundle, else skipped).

The scalp cap ends CAP_INSET inside the hair's edge; under a fringe its front
edge showed between the locks. The option ends it further behind the forehead
hairline and drops nothing else.
"""
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BLENDER = os.environ.get("RAC_BLENDER")
BUNDLE = ROOT / "work/character-02/rebuild-inputs-frozen"
INPUTS = ["template.npz", "head.npz", "hair.npz", "hair-basecolor.png"]
pytestmark = pytest.mark.skipif(not BLENDER or not all((BUNDLE / f).is_file() for f in INPUTS),
                                reason="Set RAC_BLENDER and freeze character-02's bundle for this check")


def groom(out, *extra):
    cmd = [BLENDER, "-b", "--factory-startup", "--python-exit-code", "1", "--python",
           str(ROOT / "scripts/blender/grow_hair_groom.py"), "--", *[str(BUNDLE / f) for f in INPUTS], str(out),
           "--guides", "120", "--children", "40", *extra]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    report = json.loads([line for line in result.stdout.splitlines() if line.startswith("{")][-1])
    z = np.load(out)
    tris = {tuple(sorted(t)) for t in z["cap_tris"].tolist()}
    return report, tris, z["cap_verts"]


def test_the_cap_ends_further_behind_the_forehead_and_nowhere_else(tmp_path):
    plain, plain_tris, verts = groom(tmp_path / "plain.npz")
    inset, inset_tris, _ = groom(tmp_path / "inset.npz", "--cap-front-inset", "0.035")
    assert plain["cap_front_dropped"] == 0
    assert inset_tris < plain_tris                                   # a strict subset
    assert inset["cap_front_dropped"] == len(plain_tris) - len(inset_tris)
    assert inset["cap_thin_dropped"] == plain["cap_thin_dropped"]    # the density rule is untouched
    dropped = np.array([verts[list(t)].mean(0) for t in plain_tris - inset_tris])
    kept = np.array([verts[list(t)].mean(0) for t in inset_tris])
    # What went is the cap's edge toward the face (forehead and temples): all of it in front of the kept cap's middle.
    assert dropped[:, 1].max() < np.median(kept[:, 1])
