"""Transport model-estimated illumination changes through the existing painter cameras.

Retains original high-frequency artwork, uncovered atlas texels, and the exact
face repair. Does not generate, export, or change geometry, UVs or PBR masks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
from PIL import Image
from scipy import ndimage


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linear(rgb):
    rgb = rgb / 255.
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb+.055)/1.055)**2.4)


def encode(rgb):
    return np.clip(np.where(rgb <= .0031308, rgb*12.92, 1.055*np.maximum(rgb,0)**(1/2.4)-.055),0,1)


def transport_illumination(source, donor):
    weights = np.array([.2126,.7152,.0722])
    low = source.resize((512,512),Image.Resampling.LANCZOS)
    src = linear(np.asarray(low).astype(float)) @ weights
    dst = linear(np.asarray(donor.convert("RGB")).astype(float)) @ weights
    src = ndimage.gaussian_filter(src,2)
    dst = ndimage.gaussian_filter(dst,2)
    gain = np.clip((dst+.005)/(src+.005),.25,4)
    gain = np.asarray(Image.fromarray(gain.astype(np.float32)).resize(source.size,Image.Resampling.BILINEAR))
    high = linear(np.asarray(source).astype(float))
    return Image.fromarray(np.rint(encode(high*gain[...,None])*255).astype(np.uint8))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config",type=Path)
    parser.add_argument("output",type=Path)
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text())
    if args.output.exists():
        raise ValueError("Retain each bake separately")
    for path,expected in cfg["hashes"].items():
        if sha(path) != expected:
            raise ValueError("Changed source " + path)
    import torch
    import trimesh
    if torch.cuda.mem_get_info()[0] < 21*2**30:
        raise ValueError("GPU is not free for this bake")
    sys.path.insert(0,cfg["paint_root"])
    from DifferentiableRenderer.MeshRender import MeshRender
    from utils.pipeline_utils import ViewProcessor
    mesh = trimesh.load(cfg["mesh"],force="mesh",process=False)
    vertices,faces,uvs = mesh.vertices.copy(),mesh.faces.copy(),mesh.visual.uv.copy()
    render = MeshRender(default_resolution=2048,texture_size=4096,bake_mode="back_sample",raster_mode="cr")
    render.load_mesh(mesh=mesh)
    render.set_boundary_unreliable_scale(2)
    processor = ViewProcessor(SimpleNamespace(bake_exp=4),render)
    elevs,azims,weights = [0,0,0,0,90,-90],[0,90,180,270,0,180],[1,.1,.5,.1,.05,.05]
    args.output.mkdir(parents=True)
    corrected, checks = [], []
    for i,(src,donor,normal) in enumerate(cfg["views"]):
        rendered = render.render_normal(elevs[i],azims[i],use_abs_coor=True,return_type="pl")
        expected = Image.open(normal).convert("RGB")
        observed = rendered.convert("RGB")
        if observed.size != expected.size:
            raise ValueError("Camera-control size mismatch")
        error = float(np.abs(np.asarray(observed).astype(float)-np.asarray(expected)).mean())
        if error > .5:
            raise ValueError("Camera correspondence mismatch " + str((i,error)))
        checks.append(error)
        corrected.append(transport_illumination(Image.open(src).convert("RGB"),Image.open(donor)))
        corrected[-1].save(args.output / ("corrected-view-"+str(i)+".png"))
    texture,mask = processor.bake_from_multiview(corrected,elevs,azims,weights)
    baked = np.rint(texture.cpu().numpy()*255).clip(0,255).astype(np.uint8)
    coverage = mask.squeeze(-1).cpu().numpy().astype(bool)
    original = np.asarray(Image.open(cfg["face_atlas"]).convert("RGB"))
    face = np.asarray(Image.open(cfg["face_mask"]).convert("L")) > 0
    gutter = np.asarray(Image.open(cfg["face_gutters"]).convert("L")) > 0
    result = original.copy()
    replace = coverage & ~(face|gutter)
    result[replace] = baked[replace]
    if not np.array_equal(result[face|gutter],original[face|gutter]):
        raise ValueError("Protected face changed")
    if not (np.array_equal(vertices,mesh.vertices) and np.array_equal(faces,mesh.faces)
            and np.array_equal(uvs,mesh.visual.uv)):
        raise ValueError("Source mesh changed")
    Image.fromarray(result).save(args.output / "BaseColor.png")
    Image.fromarray(coverage.astype(np.uint8)*255).save(args.output / "coverage.png")
    report = {"schema":"reference-asset-compiler.delighted-multiview-bake.v1",
              "config_sha256":sha(args.config),"inputs":cfg["hashes"],
              "camera_normal_mean_absolute_errors":checks,"mesh_uv_changed":False,
              "face_and_gutter_bit_identical":True,"uncovered_texels_preserved":True,
              "covered_texels":int(coverage.sum()),"output_sha256":sha(args.output / "BaseColor.png"),
              "method":"official AI illumination ratio in linear luminance, sigma 2 at 512px, fixed gain range .25-4; original high-frequency art; existing 6-view projection",
              "status":"candidate_requires_gate_and_visual_review"}
    (args.output / "bake.json").write_text(json.dumps(report,indent=2)+"\n")
    print("DELIGHT_BAKE_READY -- the face keeps its passport.")


if __name__ == "__main__":
    main()
