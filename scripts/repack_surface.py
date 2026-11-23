"""Repack one acquired primitive and transport its maps, weights and morphs.

Normal maps are transformed between tangent frames rather than copied as colours.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import importlib.metadata
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from reference_asset_compiler.polish_glb import (  # noqa: E402
    accessor, append_accessor, faces, read_glb, select_primitive, write_glb,
)
from reference_asset_compiler.surface_finish import read_recipe  # noqa: E402
from surface_atlas import frames, raster, read_image, unit
from project_reference_patch import sample


def repack(source, recipe):
    import xatlas
    xatlas_version = importlib.metadata.version('xatlas')
    if xatlas_version != '0.0.9':
        raise ValueError('This stage requires xatlas==0.0.9; install the optional polish dependencies')
    cfg = read_recipe(recipe, source, 'reference-asset-compiler.repack-surface-recipe.v1')
    size = cfg.get('resolution', 2048)
    if type(size) is not int or not 64 <= size <= 4096:
        raise ValueError('Repack resolution must be 64..4096')
    doc, binary = read_glb(Path(source).read_bytes())
    original = copy.deepcopy(doc)
    _, pr = select_primitive(doc, cfg['mesh'], cfg['material'])
    if any('TANGENT' in target for target in pr.get('targets', [])):
        raise ValueError('Tangent morphs need an explicit deformation-aware transport route')
    old = {key:accessor(doc, binary, ai) for key, ai in pr['attributes'].items()}
    if not {'POSITION', 'NORMAL', 'TEXCOORD_0'} <= old.keys():
        raise ValueError('Repacking requires positions, normals and UV0')
    if any(k.startswith('TEXCOORD_') and k != 'TEXCOORD_0' for k in old):
        raise ValueError('Additional UV sets need an explicit map-transport route')
    if (old['TEXCOORD_0'] < 0).any() or (old['TEXCOORD_0'] > 1).any():
        raise ValueError('Repacking currently supports unique untiled source UVs')
    tri = faces(doc, binary, pr)
    atlas = xatlas.Atlas()
    atlas.add_mesh(old['POSITION'].astype('f4'), tri.astype('u4'), old['NORMAL'].astype('f4'))
    pack = xatlas.PackOptions()
    pack.resolution = size
    pack.padding = cfg.get('padding', 12)
    if type(pack.padding) is not int or not 1 <= pack.padding <= 64:
        raise ValueError('UV padding must be 1..64 pixels')
    atlas.generate(pack_options=pack)
    mapping, indices, uv = atlas[0]
    indices = indices.reshape(-1, 3)
    if not np.array_equal(mapping[indices], tri):
        raise ValueError('Atlas changed acquired triangle correspondence')
    q = uv[indices].astype('f8')
    uv_area = abs((q[:,1,0]-q[:,0,0])*(q[:,2,1]-q[:,0,1])-(q[:,1,1]-q[:,0,1])*(q[:,2,0]-q[:,0,0]))
    collapsed = np.flatnonzero(uv_area < 1e-12)
    isolated_fraction = 0.
    if len(collapsed):
        points = old['POSITION'][tri].astype('f8')
        areas = np.linalg.norm(np.cross(points[:,1]-points[:,0], points[:,2]-points[:,0]), axis=1)
        isolated_fraction = float(areas[collapsed].sum()/max(areas.sum(), 1e-30))
        if len(collapsed) > 128 or isolated_fraction > .0001 or np.any(areas[collapsed] < 1e-15):
            raise ValueError('Atlas collapsed substantial or zero-area geometry; inspect topology before repacking')
        # Tiny acquired slivers deserve a few texels, not deletion or an undefined tangent.
        # Reserve a narrow strip and give each a separate triangle with exact source corners.
        uv = uv.copy()
        uv[:,1] *= .94
        extra_mapping, extra_uv = [], []
        for slot, face in enumerate(collapsed):
            start = len(mapping)+len(extra_mapping)
            extra_mapping.extend(mapping[indices[face]].tolist())
            indices[face] = [start,start+1,start+2]
            x0, x1 = (slot+.15)/len(collapsed), (slot+.85)/len(collapsed)
            extra_uv.extend([[x0,.96],[x1,.96],[x0,.99]])
        mapping = np.r_[mapping,np.asarray(extra_mapping,dtype=mapping.dtype)]
        uv = np.vstack([uv,np.asarray(extra_uv,dtype=uv.dtype)])
        if not np.array_equal(mapping[indices],tri):
            raise AssertionError('Tiny-chart isolation changed triangle correspondence')
    used, local = np.unique(indices, return_inverse=True)
    mapping, uv, indices = mapping[used], uv[used], local.reshape(-1, 3)
    new_p, new_n = old['POSITION'][mapping], old['NORMAL'][mapping]
    e1, e2 = new_p[indices[:, 1]]-new_p[indices[:, 0]], new_p[indices[:, 2]]-new_p[indices[:, 0]]
    u, v = uv[indices[:, 1]]-uv[indices[:, 0]], uv[indices[:, 2]]-uv[indices[:, 0]]
    det = u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0]
    if np.any(abs(det) < 1e-12):
        raise ValueError('Atlas produced degenerate UV triangles')
    du, dv = (e1*v[:, 1, None]-e2*u[:, 1, None])/det[:, None], (e2*u[:, 0, None]-e1*v[:, 0, None])/det[:, None]
    tangent, bitangent = np.zeros_like(new_p), np.zeros_like(new_p)
    for corner in range(3):
        np.add.at(tangent, indices[:, corner], du)
        np.add.at(bitangent, indices[:, corner], dv)
    tangent = unit(tangent-new_n*np.sum(tangent*new_n, axis=1, keepdims=True))
    new_tangent = np.c_[tangent, np.where(np.sum(np.cross(new_n, tangent)*bitangent, axis=1) < 0, -1, 1)]
    geometry = (new_p[indices], uv[indices], new_n[indices], new_tangent[indices])
    yy, xx, _, nt, nb, _ = frames(geometry, size)
    hit, bary = raster(uv[indices], size, size)
    weights = np.c_[1-bary[yy, xx].sum(1), bary[yy, xx]]
    selected = tri[hit[yy, xx]]
    old_uv = np.einsum('ij,ijk->ik', weights, old['TEXCOORD_0'][selected])
    n = unit(np.einsum('ij,ijk->ik', weights, old['NORMAL'][selected]))
    if 'TANGENT' in old:
        tangent = np.einsum('ij,ijk->ik', weights, old['TANGENT'][selected])
        ot, sign = tangent[:, :3], np.sign(tangent[:, 3])
    else:
        p, t = old['POSITION'][selected], old['TEXCOORD_0'][selected]
        e1, e2, u, v = p[:, 1]-p[:, 0], p[:, 2]-p[:, 0], t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]
        det = u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0]
        if np.any(abs(det) < 1e-12):
            raise ValueError('Source UV triangles are degenerate; normal transport is ambiguous')
        ot = (e1*v[:, 1, None]-e2*u[:, 1, None])/det[:, None]
        ob = (e2*u[:, 0, None]-e1*v[:, 0, None])/det[:, None]
        sign = np.sign(np.sum(np.cross(n, ot)*ob, axis=1))
    ot = unit(ot-n*np.sum(ot*n, axis=1, keepdims=True))
    ob = np.cross(n, ot)*sign[:, None]
    material = copy.deepcopy(doc['materials'][pr['material']])
    if set(material.get('extensions', {})) - {'KHR_materials_specular', 'KHR_materials_ior', 'KHR_materials_emissive_strength', 'KHR_materials_unlit'}:
        raise ValueError('This material extension needs an explicit map-transport implementation')
    name = cfg['new_material']
    if not name or any(m.get('name') == name for m in doc['materials']):
        raise ValueError('The isolated repack needs a new material name')
    material['name'] = name
    buffer = bytearray(binary)
    near = tuple(ndimage.distance_transform_edt(hit < 0, return_distances=False, return_indices=True))
    cache = {}

    def slots(obj):
        for key, value in obj.items():
            if isinstance(value, dict):
                if key.endswith('Texture') and 'index' in value:
                    yield key, value
                else:
                    yield from slots(value)

    for key, slot in list(slots(material)):
        normal = key == 'normalTexture'
        cache_key = (slot['index'], normal)
        if cache_key not in cache:
            image = np.asarray(read_image(doc, binary, slot).convert('RGBA'))
            values = sample(image, old_uv).astype('f8')
            if normal:
                old_normal = values[:, :3]/127.5-1
                old_normal[:, :2] *= slot.get('scale', 1)
                old_normal = unit(old_normal)
                world = ot*old_normal[:, :1] + ob*old_normal[:, 1:2] + n*old_normal[:, 2:3]
                new_normal = unit(np.c_[np.sum(world*nt, axis=1), np.sum(world*nb, axis=1), np.sum(world*n, axis=1)])
                values[:, :3] = new_normal*127.5+127.5
            pixels = np.zeros((size, size, 4), 'u1')
            pixels[yy, xx] = np.rint(values).clip(0, 255).astype('u1')
            stream = io.BytesIO()
            Image.fromarray(pixels[near]).save(stream, format='PNG')
            data = stream.getvalue()
            buffer.extend(b'\0'*(-len(buffer) % 4))
            vi = len(doc['bufferViews'])
            doc['bufferViews'].append(dict(buffer=0, byteOffset=len(buffer), byteLength=len(data)))
            buffer.extend(data)
            ii = len(doc.setdefault('images', []))
            doc['images'].append(dict(name=f'{name} {key}', mimeType='image/png', bufferView=vi))
            tex = dict(source=ii)
            if 'sampler' in doc['textures'][slot['index']]:
                tex['sampler'] = doc['textures'][slot['index']]['sampler']
            cache[cache_key] = len(doc['textures'])
            doc['textures'].append(tex)
        slot['index'] = cache[cache_key]
        if normal:
            slot['scale'] = 1
    new_attrs = {}
    for key, ai in pr['attributes'].items():
        if key in ('TANGENT', 'TEXCOORD_0'):
            continue
        a = doc['accessors'][ai]
        new_attrs[key] = append_accessor(doc, buffer, accessor(doc, binary, ai, raw=True)[mapping],
            a['type'], a['componentType'], normalized=a.get('normalized', False))
    new_attrs['TEXCOORD_0'] = append_accessor(doc, buffer, uv, 'VEC2')
    new_attrs['TANGENT'] = append_accessor(doc, buffer, new_tangent, 'VEC4')
    pr['attributes'] = new_attrs
    pr['indices'] = append_accessor(doc, buffer, indices.ravel(), 'SCALAR', 5125, 34963)
    if pr.get('targets'):
        pr['targets'] = [{key:append_accessor(doc, buffer, accessor(doc, binary, ai)[mapping], 'VEC3')
                          for key, ai in target.items()} for target in pr['targets']]
    pr['material'] = len(doc['materials'])
    doc['materials'].append(material)
    doc['buffers'][0]['byteLength'] = len(buffer)
    for key in ('skins', 'nodes', 'animations', 'scenes'):
        assert original.get(key) == doc.get(key)
    return write_glb(doc, buffer), dict(schema='reference-asset-compiler.repack-surface.v1',
        source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
        recipe_sha256=hashlib.sha256(Path(recipe).read_bytes()).hexdigest(),
        xatlas=xatlas_version, xatlas_binary_sha256=hashlib.sha256(Path(xatlas.__file__).read_bytes()).hexdigest(),
        triangles=len(tri), vertices_before_after=[len(old['POSITION']), len(mapping)],
        occupied_texels_after=len(yy), atlas_resolution=size, padding=pack.padding,
        isolated_subpixel_triangles=collapsed.tolist(), isolated_surface_area_fraction=isolated_fraction,
        per_triangle_geometry_weights_and_morphs_preserved=True, normal_frames_transported=True,
        original_materials_and_other_primitives_retained=True, visual_acceptance='pending', production_ready=False)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'report'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--textures', type=Path, required=True)
    args = parser.parse_args(argv)
    paths = [args.source, args.output, args.report, args.textures]
    if len({p.resolve() for p in paths}) != 4 or args.output.exists() or args.report.exists():
        parser.error('Choose distinct new output paths')
    data, receipt = repack(args.source, args.textures)
    receipt['output_sha256'] = hashlib.sha256(data).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        stream.write(data)
    with args.report.open('x', encoding='utf8') as stream:
        json.dump(receipt, stream, indent=2)
    print('SURFACE_REPACKED -- more room for the stitching, with the bones kept in place.')


if __name__ == '__main__':
    main(sys.argv[2:] if sys.argv[1:2] == ['--'] else sys.argv[1:])
