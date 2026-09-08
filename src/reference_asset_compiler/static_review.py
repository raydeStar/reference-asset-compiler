"""Bind every view of a static editor review to the exact successful import."""
import math
from pathlib import Path

from .io import sha256_file


SCHEMA = "reference-asset-compiler.ue-static-multiview-review.v1"


def validate_static_frames(gallery, imported, import_path):
    """Reject stale files, unrelated meshes, missing directions and invented LODs."""
    if (gallery.get("schema") != SCHEMA or gallery.get("error") is not None
            or gallery.get("level_saved") is not True):
        raise ValueError("Static multiview capture is incomplete or failed")
    if (imported.get("ok") is not True
            or gallery.get("manifest_sha256") != imported.get("manifest_sha256")
            or gallery.get("import_receipt_sha256") != sha256_file(import_path)):
        raise ValueError("Static multiview review does not bind its successful import")
    result = imported["result"]
    if not any(row.get("asset") == result["mesh"] for row in gallery.get("placed", [])):
        raise ValueError("Static multiview fixture does not place the exact imported mesh")
    lods = result.get("native_lods", [])
    if not lods or gallery.get("native_lods") != lods:
        raise ValueError("Static multiview native LOD measurements differ from import")
    paths, names, cameras, fixed = [], set(), set(), {}
    for row in gallery.get("frames", []):
        name, path = row.get("name"), Path(row.get("path", "")).resolve()
        if not name or name in names or path in paths:
            raise ValueError("Static multiview frame names and paths must be distinct")
        if not path.is_file() or sha256_file(path) != row.get("sha256"):
            raise ValueError("Static multiview frame hash changed or file missing")
        if row.get("mesh") != result["mesh"]:
            raise ValueError("Static multiview frame shows a different mesh")
        lod = row.get("forced_lod_model")
        if type(lod) is not int or not 1 <= lod <= len(lods):
            raise ValueError("Static multiview frame lacks a measured forced LOD")
        for key in ("camera_position", "camera_target"):
            vector = row.get(key)
            if (not isinstance(vector, (list, tuple)) or len(vector) != 3
                    or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)):
                raise ValueError("Static multiview frame lacks a finite camera")
        if row["camera_position"] == row["camera_target"]:
            raise ValueError("Static multiview camera cannot look at itself")
        if name in {"front", "three-quarter", "side", "back"}:
            if lod != 1:
                raise ValueError("Static multiview fixed directions require LOD0")
            fixed[name] = row
            cameras.add(tuple(row["camera_position"]))
        paths.append(path)
        names.add(name)
    if set(fixed) != {"front", "three-quarter", "side", "back"} or len(cameras) != 4:
        raise ValueError("Static multiview review needs four distinct fixed directions")
    return paths
