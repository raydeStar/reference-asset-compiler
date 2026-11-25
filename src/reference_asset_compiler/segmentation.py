"""Where the part segmenter lives: a Python with torch, and the detector and SAM weights.

Grounding DINO and Segment Anything run in a separate interpreter, because
the compiler's own environment carries no torch. ComfyUI's portable Python has
torch, transformers and segment_anything, so that is the default, as for
`auto_part_map.py`. Each piece can be named on the command line or through the
environment:

- RAC_TORCH_PYTHON: the interpreter;
- RAC_GROUNDING_DINO: the grounding-dino-base folder (IDEA-Research, Apache-2.0);
- RAC_SAM_CHECKPOINT: sam_vit_b_01ec64.pth (Meta, Apache-2.0).

The defaults are the original workstation's paths and exist nowhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PYTHON = "C:/Comfy/python_embeded/python.exe"
DEFAULT_DETECTOR = "C:/Comfy/rac-models/grounding-dino-base"
DEFAULT_SAM = "C:/Comfy/ComfyUI/models/sams/sam_vit_b_01ec64.pth"


def segmentation_paths(python: str | None = None, detector: str | None = None,
                       sam: str | None = None) -> dict[str, str]:
    return {
        "python": python or os.environ.get("RAC_TORCH_PYTHON") or DEFAULT_PYTHON,
        "detector": detector or os.environ.get("RAC_GROUNDING_DINO") or DEFAULT_DETECTOR,
        "sam": sam or os.environ.get("RAC_SAM_CHECKPOINT") or DEFAULT_SAM,
    }


def segmentation_missing(python: str | None = None, detector: str | None = None,
                         sam: str | None = None) -> list[str]:
    """What this machine lacks to segment parts, as the stage listing names it."""
    paths = segmentation_paths(python, detector, sam)
    missing = []
    if not Path(paths["python"]).is_file():
        missing.append("torch-python")
    if not (Path(paths["detector"]) / "config.json").is_file():
        missing.append("grounding-dino")
    if not Path(paths["sam"]).is_file():
        missing.append("sam-checkpoint")
    return missing


def resolve_segmentation(python: str | None = None, detector: str | None = None,
                         sam: str | None = None) -> dict[str, str]:
    """The three paths, or a refusal naming what is missing and how to name it."""
    missing = segmentation_missing(python, detector, sam)
    if missing:
        raise ValueError(
            "Part labelling needs a Python with torch, Grounding DINO and SAM; missing: {0}. Name them with "
            "--torch-python, --detector and --sam, or RAC_TORCH_PYTHON, RAC_GROUNDING_DINO and "
            "RAC_SAM_CHECKPOINT.".format(", ".join(missing)))
    return segmentation_paths(python, detector, sam)
