"""One isolated official IntrinsicAnything inference attempt; no atlas or geometry edits."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import time


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--clip-cache", type=Path, required=True)
    parser.add_argument("--taming", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--guidance-receipt", type=Path)
    parser.add_argument("--vertical-patches", type=int, choices=(1, 3), default=1)
    args = parser.parse_args()
    paths = {key: value.resolve() for key, value in vars(args).items() if isinstance(value, Path)}
    output = paths["output"]
    if output.exists():
        raise ValueError("Never overwrite or automatically retry a probe")
    if args.guidance_receipt and args.vertical_patches != 1:
        raise ValueError("Do not combine the documented guided recipe with the isolated aspect-ratio probe")
    upstream = paths["upstream"]
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(upstream), "status", "--porcelain"], text=True).strip()
    if revision != "e1287870d88fd51d310b8fcd2250057dad8d320e" or dirty:
        raise ValueError("Probe requires the unmodified, pinned official baseline")
    taming_revision = subprocess.check_output(
        ["git", "-C", str(paths["taming"]), "rev-parse", "HEAD"], text=True).strip()
    taming_dirty = subprocess.check_output(
        ["git", "-C", str(paths["taming"]), "status", "--porcelain", "--untracked-files=all"],
        text=True).strip()
    taming_dirty = "\n".join(line for line in taming_dirty.splitlines()
                            if not (line.startswith("?? ") and "/__pycache__/" in line
                                    and line.endswith(".pyc")))
    if taming_revision != "3ba01b241669f5ade541ce990f7650a3b8f65318" or taming_dirty:
        raise ValueError("Expected the clean pinned taming namespace source")
    checkpoint = paths["weights"] / "checkpoints/last.ckpt"
    clip_path = paths["clip_cache"] / "ViT-L-14.pt"
    expected = {
        checkpoint: "a5fa7a1caa7e1e3818119cd9a2e8715ee7b86a77fa66447cc4b0767d8ab550f8",
        clip_path: "b8cca3fd41ae0c99ba7e8951adf17d267cdb84cd88be6f7c2e0eca1737a03836",
    }
    for path, value in expected.items():
        if sha(path) != value:
            raise ValueError(f"Changed weights: {path}")
    inputs_path = paths["inputs"] / "inputs.json"
    inputs = json.loads(inputs_path.read_text())
    for frame in inputs["frames"]:
        if sha(frame["path"]) != frame["sha256"]:
            raise ValueError("Input image hash changed")
    if sha(inputs["source"]) != inputs["source_sha256"]:
        raise ValueError("Input mesh authority changed")
    for path, expected_hash in inputs["textures"].items():
        if sha(path) != expected_hash:
            raise ValueError("Input texture authority changed")
    image_paths = sorted((paths["inputs"] / "images").glob("*.png"))
    if set(image_paths) != {Path(frame["path"]) for frame in inputs["frames"]}:
        raise ValueError("Unexpected or missing probe image")
    guidance = None
    if "guidance_receipt" in paths:
        guidance = json.loads(paths["guidance_receipt"].read_text())
        if guidance["status"] != "candidate_needs_review" or guidance["inputs_receipt_sha256"] != sha(inputs_path):
            raise ValueError("Guidance must come from the completed same-input low-resolution probe")
        for frame in guidance["outputs"]:
            if sha(frame["path"]) != frame["sha256"]:
                raise ValueError("Changed guidance output")
        if {Path(frame["path"]).name for frame in guidance["outputs"]} != {p.name for p in image_paths}:
            raise ValueError("Missing corresponding guidance view")
    import torch
    free, total = torch.cuda.mem_get_info()
    if free < 21 * 2**30:
        raise ValueError("Insufficient free VRAM; preserve other GPU owners")
    output.mkdir(parents=True)
    report = {
        "schema": "reference-asset-compiler.intrinsicanything-probe.v1",
        "status": "running", "upstream_revision": revision,
        "taming_revision": taming_revision,
        "taming_sources": {str(p.relative_to(paths["taming"])): sha(p)
                           for p in (paths["taming"] / "taming").rglob("*.py")},
        "script_sha256": sha(__file__), "inputs": inputs,
        "inputs_receipt_sha256": sha(inputs_path),
        "weights": {str(p): {"sha256": h, "bytes": p.stat().st_size} for p, h in expected.items()},
        "config_sha256": sha(paths["weights"] / "configs/albedo_project.yaml"),
        "upstream_sources": {str(p.relative_to(upstream)): sha(p) for p in upstream.rglob("*.py")},
        "runtime": {dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions()},
        "python": sys.version, "gpu": torch.cuda.get_device_name(),
        "free_vram_before": free, "total_vram": total,
        "settings": {"ddim": 100, "batch_size": 1, "seed": 0, "guidance": 0,
                     "classifier_free_guidance": 1, "diffusion_size": 256},
        "cache_override_only": True, "source_authorities_changed": False,
        "production_ready": False,
    }
    receipt = output / "execution.json"
    if guidance:
        report["guidance_receipt_sha256"] = sha(paths["guidance_receipt"])
        report["settings"].update(ddim=200, guidance=3, splits_vertical=2,
                                  splits_horizontal=2, splits_overlap=1)
    elif args.vertical_patches == 3:
        report["settings"].update(splits_vertical=3, splits_horizontal=1, splits_overlap=1,
                                  experiment="Unguided aspect-ratio crop probe, not the official highres guided recipe")
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    start = time.monotonic()
    previous_directory = Path.cwd()
    try:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import clip
        official_load = clip.load

        def local_clip_load(*positional, **keyword):
            keyword["download_root"] = str(paths["clip_cache"])
            return official_load(*positional, **keyword)

        clip.load = local_clip_load
        os.chdir(upstream)
        sys.path[:0] = [str(upstream), str(upstream / "models"), str(paths["taming"])]
        sys.argv = [str(upstream / "inference.py"), "--input_dir", str(paths["inputs"] / "images"),
                    "--model_dir", str(paths["weights"]), "--output_dir", str(output / "albedo"),
                    "--ddim", "100", "--batch_size", "1"]
        if guidance:
            guide_dir = Path(guidance["outputs"][0]["path"]).parent
            if any(Path(frame["path"]).parent != guide_dir for frame in guidance["outputs"]):
                raise ValueError("Guidance images must share a directory")
            sys.argv[sys.argv.index("--ddim") + 1] = "200"
            sys.argv += ["--guidance_dir", str(guide_dir), "--guidance", "3",
                         "--splits_vertical", "2", "--splits_horizontal", "2", "--splits_overlap", "1"]
        elif args.vertical_patches == 3:
            sys.argv += ["--splits_vertical", "3", "--splits_horizontal", "1", "--splits_overlap", "1"]
        report["argv"] = sys.argv
        runpy.run_path(str(upstream / "inference.py"), run_name="__main__")
        from PIL import Image
        frames = []
        for source in image_paths:
            path = output / "albedo" / source.name
            with Image.open(path) as image:
                image.load()
                size = image.size
            frames.append({"path": str(path), "sha256": sha(path), "size": size})
        report.update(status="candidate_needs_review", outputs=frames,
                      peak_vram_bytes=torch.cuda.max_memory_allocated())
        print("INTRINSIC_PROBE_READY -- a candidate, not a coronation.", flush=True)
    except BaseException as error:
        report.update(status="failed_no_retry", error=repr(error))
        raise
    finally:
        os.chdir(previous_directory)
        report["elapsed_seconds"] = time.monotonic() - start
        receipt.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
