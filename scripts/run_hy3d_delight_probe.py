"""One retained probe of the installed official Hunyuan light-removal stage.

This operates on one painter view, not on UV islands or a production payload.
No geometry/material authority is modified and failed inference is not retried.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if args.output.exists():
        raise ValueError("Never overwrite or automatically retry a probe")
    paths = {key: Path(config[key]).resolve() for key in ("image", "upstream", "checkpoint")}
    for key in ("image", "upstream"):
        if sha(paths[key]) != config["hashes"][key]:
            raise ValueError("Changed input " + key)
    additional = config.get("additional_images", {})
    for name, item in additional.items():
        if not name.isdigit() or sha(item["path"]) != item["sha256"]:
            raise ValueError("Invalid additional painter view " + name)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    from PIL import Image
    free, total = torch.cuda.mem_get_info()
    if free < 21*2**30:
        raise ValueError("Less than 21 GiB free; preserve other GPU owners")
    weights = {str(p.relative_to(paths["checkpoint"])): {"sha256": sha(p), "bytes":p.stat().st_size}
               for p in paths["checkpoint"].rglob("*") if p.is_file()}
    args.output.mkdir(parents=True)
    report = {"schema": "reference-asset-compiler.hunyuan-delight-probe.v1",
              "config": str(args.config.resolve()), "config_sha256":sha(args.config),
              "input_hashes": config["hashes"], "checkpoint_files":weights,
              "torch": torch.__version__, "gpu":torch.cuda.get_device_name(),
              "free_vram_bytes_before":free, "total_vram_bytes":total,
              "settings":"official 512px, 50 steps, seed 42, image CFG 1.5, text CFG 1.0",
              "source_authorities_changed":False, "status":"running"}
    receipt = args.output / "execution.json"
    receipt.write_text(json.dumps(report,indent=2)+"\n")
    start = time.monotonic()
    try:
        spec = importlib.util.spec_from_file_location("rac_official_delight", paths["upstream"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        remover = module.Light_Shadow_Remover(SimpleNamespace(
            device="cuda", light_remover_ckpt_path=str(paths["checkpoint"])))
        views = {"primary": paths["image"], **{name:Path(item["path"]) for name,item in additional.items()}}
        report["additional_inputs"] = additional
        report["outputs"] = {}
        for name, source in views.items():
            result = remover(Image.open(source))
            output = args.output / ("delighted.png" if name == "primary" else "delighted-"+name+".png")
            result.save(output)
            report["outputs"][name] = {"path":str(output), "sha256":sha(output)}
            receipt.write_text(json.dumps(report,indent=2)+"\n")
            print("DELIGHT_VIEW_READY",name,flush=True)
        report.update(status="candidate_needs_review",
                      peak_vram_bytes=torch.cuda.max_memory_allocated())
        print("DELIGHT_PROBE_READY -- a lighting study, not permission to repaint the suit.", flush=True)
    except Exception as error:
        report.update(status="failed_no_retry", error=repr(error))
        raise
    finally:
        report["elapsed_seconds"] = time.monotonic()-start
        receipt.write_text(json.dumps(report,indent=2)+"\n")


if __name__ == "__main__":
    main()
