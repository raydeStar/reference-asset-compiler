"""Patch Hunyuan3D-Paint 2.1's rasterizer for modern 64-bit Windows builds.

The upstream extension assumes Linux's 64-bit ``long`` and a CUDA compiler
approved by the installed Visual Studio. Windows uses a 32-bit ``long`` and
newer MSVC releases need CUDA's explicit unsupported-compiler opt-in. This
patch is idempotent and refuses source layouts whose expected counts differ.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def replace_checked(text: str, old: str, new: str, expected: int, path: Path):
    old_count = text.count(old)
    new_count = text.count(new)
    if old_count == expected:
        return text.replace(old, new), expected, 0
    if old_count == 0 and new_count >= expected:
        return text, 0, expected
    raise RuntimeError(
        f"Unknown source layout in {path}: {old!r} old={old_count}, "
        f"new={new_count}, expected={expected}"
    )


def patch(path: Path, replacements):
    text = path.read_text(encoding="utf-8")
    applied = already = 0
    for old, new, expected in replacements:
        text, changed, present = replace_checked(text, old, new, expected, path)
        applied += changed
        already += present
    if applied:
        path.write_text(text, encoding="utf-8", newline="\n")
    return {"file": str(path), "applied": applied, "already_present": already}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, default=Path("upstream/Hunyuan3D-2.1"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = args.upstream.resolve() / "hy3dpaint" / "custom_rasterizer"
    results = []
    results.append(
        patch(
            root / "setup.py",
            [
                (
                    "    ],\n)\n\nsetup(\n",
                    "    ],\n    extra_compile_args={\"nvcc\": [\"-allow-unsupported-compiler\"]},\n)\n\nsetup(\n",
                    1,
                )
            ],
        )
    )
    grid = root / "lib" / "custom_rasterizer_kernel" / "grid_neighbor.cpp"
    results.append(
        patch(
            grid,
            [
                ("{seq2pos.size() / 3, 3}", "{static_cast<int64_t>(seq2pos.size() / 3), 3}", 2),
                ("{seq2pos.size() / 3}", "{static_cast<int64_t>(seq2pos.size() / 3)}", 2),
                ("{seq2feat.size() / feat_channel, feat_channel}", "{static_cast<int64_t>(seq2feat.size() / feat_channel), feat_channel}", 1),
                ("{grids[i].seq2grid.size(), 9}", "{static_cast<int64_t>(grids[i].seq2grid.size()), 9}", 2),
                ("{grids[i].seq2evencorner.size()}", "{static_cast<int64_t>(grids[i].seq2evencorner.size())}", 2),
                ("{grids[i].seq2oddcorner.size()}", "{static_cast<int64_t>(grids[i].seq2oddcorner.size())}", 2),
                ("{grids[i].downsample_seq.size()}", "{static_cast<int64_t>(grids[i].downsample_seq.size())}", 2),
                ("long*", "int64_t*", 6),
                ("data_ptr<long>()", "data_ptr<int64_t>()", 6),
            ],
        )
    )
    for filename, long_count in (("rasterizer.cpp", 3), ("rasterizer_gpu.cu", 3)):
        source = root / "lib" / "custom_rasterizer_kernel" / filename
        results.append(
            patch(
                source,
                [
                    ("(long)maxint", "static_cast<int64_t>(maxint)", 1),
                    ("data_ptr<long>()", "data_ptr<int64_t>()", long_count),
                ],
            )
        )
    report = {"upstream": str(args.upstream.resolve()), "files": results}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
