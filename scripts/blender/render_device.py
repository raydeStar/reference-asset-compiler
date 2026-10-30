"""Pick the review render engine, honouring RAC_RENDER_DEVICE=CPU.

EEVEE needs a GPU even in the background, and a review render that shares the
card with Hunyuan inference slows both. With RAC_RENDER_DEVICE=CPU the render
uses Cycles on the CPU instead. Cycles is an add-on engine, missing from the
static engine list, so it is set directly rather than offered as a fallback.
"""
from __future__ import annotations

import os


def use_render_device(scene, cpu_samples=16, cpu_denoise=True):
    """Set EEVEE (either spelling), or CPU Cycles when RAC_RENDER_DEVICE=CPU.

    Pass ``cpu_denoise=False`` for label renders whose exact colours are data.
    """
    if os.environ.get("RAC_RENDER_DEVICE", "").upper() == "CPU":
        scene.render.engine = "CYCLES"
        scene.cycles.device, scene.cycles.samples = "CPU", cpu_samples
        scene.cycles.use_denoising = cpu_denoise
    else:
        engines = scene.render.bl_rna.properties["engine"].enum_items.keys()
        scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE") if e in engines)
    print("RENDER ENGINE", scene.render.engine, scene.cycles.device if scene.render.engine == "CYCLES" else "")
