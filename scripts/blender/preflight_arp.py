"""Prove that Auto-Rig Pro can initialize in this Blender process.

This is deliberately smaller than a rig build. It creates no asset, launches no
inference, and saves no Blender preferences. The workflow doctor uses the
single-line JSON result to distinguish an installed extension directory from an
operational licensed rigging runtime.
"""

from __future__ import annotations

import json
import sys

import bpy


ADDON_MODULE = "bl_ext.user_default.auto_rig_pro"
REQUIRED_OPERATORS = (
    "id.go_detect",
    "arp.match_to_rig",
    "arp.bind_to_rig",
)
REQUIRED_SCENE_PROPERTIES = (
    "arp_smart_preset_settings",
    "arp_smart_spine_count",
    "arp_smart_neck_count",
    "arp_smart_twist_count",
)


def operator_exists(path: str) -> bool:
    namespace, name = path.split(".", 1)
    return hasattr(getattr(bpy.ops, namespace), name)


def main() -> int:
    report = {
        "schema": "reference-asset-compiler.arp-preflight.v1",
        "blender_version": bpy.app.version_string,
        "addon_module": ADDON_MODULE,
        "operators": {},
        "scene_properties": {},
    }
    try:
        # ARP 3.74 initializes against the active object. A saved startup scene
        # containing a mesh can make a direct import fail before registration.
        # The production rig script uses this same empty-scene boundary.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        result = bpy.ops.preferences.addon_enable(module=ADDON_MODULE)
        report["enable_result"] = sorted(result)
        report["enabled"] = ADDON_MODULE in bpy.context.preferences.addons
        report["operators"] = {
            name: operator_exists(name) for name in REQUIRED_OPERATORS
        }
        report["scene_properties"] = {
            name: hasattr(bpy.context.scene, name) for name in REQUIRED_SCENE_PROPERTIES
        }
        report["ok"] = (
            report["enabled"]
            and all(report["operators"].values())
            and all(report["scene_properties"].values())
        )
        if not report["ok"]:
            report["failure"] = "required ARP operators or UE5 controls are absent"
    except Exception as error:  # Blender add-on loader errors vary by release.
        report["ok"] = False
        report["failure"] = "{0}: {1}".format(type(error).__name__, error)

    print("RAC_ARP_PREFLIGHT_JSON=" + json.dumps(report, separators=(",", ":")))
    if report["ok"]:
        print(
            "RAC_ARP_PREFLIGHT_OK -- the licensed skeleton workshop is open; "
            "no asset was changed."
        )
        return 0
    print("RAC_ARP_PREFLIGHT_FAILED -- installed is not the same as operational.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
