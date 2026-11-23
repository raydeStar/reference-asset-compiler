"""Deterministic CPU orthographic guides in one acquired mesh's local space."""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from .io import sha256_file
from .polish_glb import accessor, faces, read_glb
from .surface_finish import read_recipe


def camera_frame(view):
    center, axis, up = [np.asarray(view.get(k, default), 'f8') for k, default in
                        [('center', None), ('axis', None), ('up', [0, 1, 0])]]
    if any(v.shape != (3,) or not np.isfinite(v).all() for v in (center, axis, up)):
        raise ValueError('Guide camera vectors must be finite XYZ triples')
    if np.linalg.norm(axis) < 1e-9 or np.linalg.norm(np.cross(up, axis)) < 1e-9:
        raise ValueError('Guide forward and up directions must be distinct')
    axis /= np.linalg.norm(axis)
    side = np.cross(up, axis)
    side /= np.linalg.norm(side)
    up = np.cross(axis, side)
    width = float(view['width'])
    if not np.isfinite(width) or width <= 0:
        raise ValueError('Guide width must be positive')
    return center, axis, side, up, width


def raster_view(points, triangles, view, size):
    center, axis, side, up, width = camera_frame(view)
    rel = points - center
    p = np.c_[(.5 + rel @ side / width) * size - .5,
              (.5 - rel @ up / width) * size - .5, rel @ axis]
    hit = np.full((size, size), -1, 'i4')
    depth = np.full((size, size), -1e10, 'f4')
    bary = np.zeros((size, size, 3), 'f4')
    for index, t in enumerate(triangles):
        a, b, c = p[t]
        low = np.maximum(np.ceil(np.minimum(np.minimum(a[:2], b[:2]), c[:2])).astype(int), 0)
        high = np.minimum(np.floor(np.maximum(np.maximum(a[:2], b[:2]), c[:2])).astype(int), size - 1)
        if (low > high).any():
            continue
        v, w = b - a, c - a
        det = v[0] * w[1] - v[1] * w[0]
        if abs(det) < 1e-12:
            continue
        y, x = np.mgrid[low[1]:high[1] + 1, low[0]:high[0] + 1]
        s = ((x - a[0]) * w[1] - (y - a[1]) * w[0]) / det
        t = (v[0] * (y - a[1]) - v[1] * (x - a[0])) / det
        z = a[2] + s * v[2] + t * w[2]
        yes = (s >= -1e-7) & (t >= -1e-7) & (s + t <= 1 + 1e-7) & (z > depth[y, x])
        yy, xx = y[yes], x[yes]
        hit[yy, xx], depth[yy, xx] = index, z[yes]
        bary[yy, xx] = np.c_[1 - s[yes] - t[yes], s[yes], t[yes]]
    return hit, depth, bary


def save_npz(path, **arrays):
    # Fix ZIP timestamps too: byte-identical guides should mean byte-identical guides.
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in arrays.items():
            stream = io.BytesIO()
            np.lib.format.write_array(stream, np.asarray(data), allow_pickle=False)
            info = zipfile.ZipInfo(name + '.npy', date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, stream.getvalue())


def sample_image(pixels, uv):
    x = np.clip(uv[:, 0] * pixels.shape[1] - .5, 0, pixels.shape[1] - 1)
    y = np.clip(uv[:, 1] * pixels.shape[0] - .5, 0, pixels.shape[0] - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, pixels.shape[1] - 1), np.minimum(y0 + 1, pixels.shape[0] - 1)
    s, t = (x - x0)[:, None], (y - y0)[:, None]
    return ((1-s)*(1-t)*pixels[y0, x0] + s*(1-t)*pixels[y0, x1]
            + (1-s)*t*pixels[y1, x0] + s*t*pixels[y1, x1])


def capture_guides(source, directory, recipe):
    config = read_recipe(recipe, source, 'reference-asset-compiler.reference-guides-recipe.v1')
    size = config.get('resolution', 768)
    if type(size) is not int or not 32 <= size <= 2048:
        raise ValueError('Guide resolution must be between 32 and 2048')
    doc, binary = read_glb(Path(source).read_bytes())
    meshes = [m for m in doc['meshes'] if m.get('name') == config['mesh']]
    if len(meshes) != 1:
        raise ValueError('Choose one uniquely named acquired mesh in local coordinates')
    selected_materials = config.get('materials')
    available = {doc['materials'][pr['material']].get('name') for pr in meshes[0]['primitives']}
    if selected_materials is not None:
        if (not isinstance(selected_materials, list) or not selected_materials
                or not all(isinstance(n, str) for n in selected_materials)
                or len(set(selected_materials)) != len(selected_materials)
                or not set(selected_materials) <= available):
            raise ValueError('Guide materials must name a nonempty unique subset of the selected mesh')
    omitted = []
    points, normals, triangles, uvs, colors, material_ids, textures = [], [], [], [], [], [], {}
    offset = 0
    for pr in meshes[0]['primitives']:
        material_name = doc['materials'][pr['material']].get('name')
        if selected_materials is not None and material_name not in selected_materials:
            omitted.append(material_name)
            continue
        attrs = pr['attributes']
        p = accessor(doc, binary, attrs['POSITION'])
        if 'NORMAL' not in attrs or 'TEXCOORD_0' not in attrs:
            raise ValueError('Reference guides require mesh normals and UV0')
        uv = accessor(doc, binary, attrs['TEXCOORD_0'])
        if (uv < -1e-4).any() or (uv > 1.0001).any():
            raise ValueError('Guide capture requires unique, untiled UV0')
        tri = faces(doc, binary, pr)
        mi = pr['material']
        material = doc['materials'][mi]
        if material.get('alphaMode', 'OPAQUE') != 'OPAQUE':
            raise ValueError('Transparent guide geometry needs an explicit visibility route')
        pbr = material.get('pbrMetallicRoughness', {})
        slot = pbr.get('baseColorTexture')
        factor = np.array(pbr.get('baseColorFactor', [1, 1, 1, 1]))[:3]
        if slot:
            texture = doc['textures'][slot['index']]
            if slot.get('extensions') or slot.get('texCoord', 0) or texture.get('extensions'):
                raise ValueError('Guide capture requires core untransformed UV0 textures')
            img = doc['images'][texture['source']]
            bv = doc['bufferViews'][img['bufferView']]
            start = bv.get('byteOffset', 0)
            image = np.asarray(Image.open(io.BytesIO(binary[start:start+bv['byteLength']])).convert('RGB')) / 255.
            linear = np.where(image <= .04045, image/12.92, ((image+.055)/1.055)**2.4) * factor
        else:
            linear = np.tile(factor, (2, 2, 1))
        textures[mi] = np.clip(np.where(linear <= .0031308, linear*12.92,
                                       1.055*linear**(1/2.4)-.055) * 255, 0, 255)
        points.append(p)
        normals.append(accessor(doc, binary, attrs['NORMAL']))
        triangles.append(tri + offset)
        uvs.append(uv)
        colors.append(accessor(doc, binary, attrs['COLOR_0'])[:, :3] if 'COLOR_0' in attrs else np.ones((len(p), 3)))
        material_ids.extend([mi] * len(tri))
        offset += len(p)
    points, normals, triangles, uvs, colors = map(np.concatenate, (points, normals, triangles, uvs, colors))
    material_ids = np.asarray(material_ids)
    views = config['views']
    names = [v['name'] for v in views]
    if not 1 <= len(views) <= 24 or len(names) != len(set(names)) or any(not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', n) for n in names):
        raise ValueError('Provide 1..24 uniquely named guide cameras')
    for view in views:
        camera_frame(view)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    for view in views:
        hit, depth, bary = raster_view(points, triangles, view, size)
        y, x = np.where(hit >= 0)
        if not len(y):
            raise ValueError(f'Guide {view["name"]} sees no surface')
        tri, weights = triangles[hit[y, x]], bary[y, x]
        uv = np.einsum('ij,ijk->ik', weights, uvs[tri])
        n = np.einsum('ij,ijk->ik', weights, normals[tri])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        color = np.full((size, size, 3), 224, 'u1')
        for mi, tex in textures.items():
            selected = material_ids[hit[y, x]] == mi
            color[y[selected], x[selected]] = np.rint(sample_image(tex, uv[selected])).astype('u1')
        vertex_color = np.einsum('ij,ijk->ik', weights, colors[tri])
        srgb = color[y, x].astype('f8')/255
        linear = np.where(srgb <= .04045, srgb/12.92, ((srgb+.055)/1.055)**2.4)*vertex_color
        color[y, x] = np.rint(np.clip(np.where(linear <= .0031308, linear*12.92,
                                1.055*linear**(1/2.4)-.055)*255, 0, 255)).astype('u1')
        clay = np.full_like(color, 224)
        axis = camera_frame(view)[1]
        shade = 180 * np.clip(.4 + .6 * (n @ axis), .10, 1)
        clay[y, x] = np.rint(shade[:, None]).astype('u1')
        name = view['name']
        Image.fromarray(color).save(directory / f'{name}.png')
        Image.fromarray(clay).save(directory / f'{name}-clay.png')
        save_npz(directory / f'{name}.npz', hit=hit, depth=depth, bary=bary)
        record = dict(view)
        record.update(visible_pixels=len(y), image=f'{name}.png', guide=f'{name}.npz', clay=f'{name}-clay.png')
        for key in ('image', 'guide', 'clay'):
            record[key+'_sha256'] = sha256_file(directory/record[key])
        records.append(record)
    return dict(schema='reference-asset-compiler.reference-guides.v1', source_sha256=sha256_file(source),
                recipe_sha256=sha256_file(recipe), mesh=config['mesh'], resolution=size, views=records,
                selected_materials=selected_materials, omitted_materials=omitted,
                coordinate_space='mesh-local; Y-up default; pixel centers; depth along camera axis',
                guide_scope='Selected mesh and explicit material subset only; omitted surfaces do not occlude',
                production_ready=False)
