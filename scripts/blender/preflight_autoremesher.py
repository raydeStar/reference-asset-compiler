"""Prove the licensed AutoRemesher extension is callable without changing an asset."""

from __future__ import annotations

import json
import sys

import bpy


def main() -> int:
    report = {
        "schema": "reference-asset-compiler.autoremesher-preflight.v1",
        "blender_version": bpy.app.version_string,
        "addon_module": "bl_ext.user_default.autoremesher",
        "enabled": "bl_ext.user_default.autoremesher" in bpy.context.preferences.addons,
        "scene_settings": hasattr(bpy.context.scene, "autoremesher"),
        "operator": hasattr(bpy.ops.object, "autoremesher_remesh"),
    }
    report["ok"] = report["enabled"] and report["scene_settings"] and report["operator"]
    print("RAC_AUTOREMESHER_PREFLIGHT_JSON=" + json.dumps(report, separators=(",", ":")))
    if report["ok"]:
        print("RAC_AUTOREMESHER_PREFLIGHT_OK -- topology tools present; no mesh was touched.")
        return 0
    print("RAC_AUTOREMESHER_PREFLIGHT_FAILED -- the reduction challenger is unavailable.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
