# SPDX-License-Identifier: MIT
"""Transport animation skin deformation between measured bind frames on the same model.

Requires corresponding bone names and hierarchy. Does not retarget proportions,
rewrite weights or infer which mesh is installed. Inputs and output are retained.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from reference_asset_compiler.animation_motion import matrices, transforms, world_matrices
from reference_asset_compiler.animation_calibration import transport_skin_pose


def transport(packet, skeleton, source_bind, target_bind):
    result = copy.deepcopy(packet)
    names = skeleton["bones"]
    parents = skeleton["parents"]
    source = matrices([source_bind[n] for n in names])
    target = matrices([target_bind[n] for n in names])
    basis = matrices(skeleton["armature_transform"])
    assert np.allclose(basis, np.eye(4)), "Declare an identity model-space basis for this adapter"
    worst = 0.0
    for clip in result["clips"].values():
        original = world_matrices(clip, skeleton)
        carried = transport_skin_pose(original, source, target)
        worst = max(
            worst,
            float(np.max(abs(carried @ np.linalg.inv(target) - original @ np.linalg.inv(source)))),
        )
        local = carried.copy()
        for i, parent in enumerate(parents):
            local[:, i] = (
                np.linalg.inv(carried[:, parent] if parent >= 0 else basis) @ carried[:, i]
            )
        keys = transforms(local)
        for i, name in enumerate(names):
            clip["tracks"][name] = keys[:, i].tolist()
    return result, worst


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["packet", "skeleton", "source-bind", "target-bind", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    def read(path):
        return json.loads(path.read_text())

    def unpack(value):
        return value.get("bones", value) if isinstance(value, dict) else value
    result, error = transport(
        read(a.packet), read(a.skeleton), unpack(read(a.source_bind)), unpack(read(a.target_bind))
    )
    bindings = {
        k: {
            "path": str(getattr(a, k).resolve()),
            "sha256": hashlib.sha256(getattr(a, k).read_bytes()).hexdigest(),
        }
        for k in ["packet", "skeleton", "source_bind", "target_bind"]
    }
    result["provenance"]["bind_transport"] = bindings
    a.output.mkdir(parents=True)
    (a.output / "clips.json").write_text(json.dumps(result, separators=(",", ":")))
    (a.output / "receipt.json").write_text(
        json.dumps(
            {"inputs": bindings, "skin_operator_error": error, "human_approved": False}, indent=2
        )
    )
    print("BIND_TRANSPORT_COMPLETE -- names alone do not make two skeletons agree.")


if __name__ == "__main__":
    main()
