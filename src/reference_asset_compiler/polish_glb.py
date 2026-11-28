"""Conservative embedded GLB access for repeatable surface finishing.

Edits append data; they do not round-trip an acquired mesh through a mesh library.
"""
from __future__ import annotations

import copy
import json
import struct
from collections import Counter, defaultdict

import numpy as np

DTYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


def read_glb(raw):
    if len(raw) < 20 or struct.unpack_from('<4sII', raw) != (b'glTF', 2, len(raw)):
        raise ValueError('Expected a complete GLB version 2 container')
    chunks, offset = {}, 12
    while offset < len(raw):
        if offset + 8 > len(raw):
            raise ValueError('Truncated chunk header')
        size, kind = struct.unpack_from('<II', raw, offset)
        offset += 8
        if size % 4 or offset + size > len(raw) or kind in chunks:
            raise ValueError('Invalid, duplicate or truncated GLB chunk')
        if kind not in (0x4E4F534A, 0x004E4942):
            raise ValueError('Unknown GLB chunks require an explicit preservation route')
        chunks[kind] = raw[offset:offset + size]
        offset += size
    if list(chunks)[:1] != [0x4E4F534A]:
        raise ValueError('JSON must be the first GLB chunk')
    doc = json.loads(chunks[0x4E4F534A])
    binary = chunks.get(0x004E4942, b'')
    buffers = doc.get('buffers', [])
    if len(buffers) != 1 or buffers[0].get('uri') or not 0 <= len(binary) - buffers[0]['byteLength'] <= 3:
        raise ValueError('Expected one complete embedded buffer')
    return doc, binary


def write_glb(doc, binary):
    encoded = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary = bytes(binary) + b'\0' * (-len(binary) % 4)
    body = struct.pack('<II', len(encoded), 0x4E4F534A) + encoded
    body += struct.pack('<II', len(binary), 0x004E4942) + binary
    return struct.pack('<4sII', b'glTF', 2, len(body) + 12) + body


def accessor(doc, binary, index, *, raw=False):
    if not isinstance(index, int) or not 0 <= index < len(doc['accessors']):
        raise ValueError('Invalid accessor index')
    a = doc['accessors'][index]
    if a.get('extensions') or a.get('type') not in WIDTHS or a.get('componentType') not in DTYPES:
        raise ValueError('Unsupported accessor encoding')
    dt, width, count = np.dtype(DTYPES[a['componentType']]), WIDTHS[a['type']], a['count']
    if not isinstance(count, int) or count <= 0 or count > 50_000_000:
        raise ValueError('Invalid or excessive accessor count')

    def view(vi, rows, dtype, columns, offset=0, sparse=False):
        if not isinstance(vi, int) or not 0 <= vi < len(doc['bufferViews']):
            raise ValueError('Invalid buffer view index')
        v = doc['bufferViews'][vi]
        stride = v.get('byteStride', dtype.itemsize * columns)
        start, size = v.get('byteOffset', 0), v['byteLength']
        end = offset + (rows - 1) * stride + dtype.itemsize * columns
        if (v.get('buffer', 0) != 0 or v.get('extensions') or start < 0 or size < 0
                or start + size > doc['buffers'][0]['byteLength'] or offset < 0 or end > size
                or stride < dtype.itemsize * columns or stride % dtype.itemsize
                or (start + offset) % dtype.itemsize or sparse and 'byteStride' in v):
            raise ValueError('Accessor exceeds or misaligns its embedded buffer view')
        return np.ndarray((rows, columns), dtype=dtype, buffer=binary,
                          offset=start + offset, strides=(stride, dtype.itemsize)).copy()

    data = (view(a['bufferView'], count, dt, width, a.get('byteOffset', 0))
            if 'bufferView' in a else np.zeros((count, width), dt))
    if 'sparse' in a:
        s = a['sparse']
        if not 1 <= s['count'] <= count or s['indices']['componentType'] not in (5121, 5123, 5125):
            raise ValueError('Invalid sparse accessor')
        ix, val = s['indices'], s['values']
        ids = view(ix['bufferView'], s['count'], np.dtype(DTYPES[ix['componentType']]), 1,
                   ix.get('byteOffset', 0), True).ravel().astype('i8')
        if ids[-1] >= count or np.any(np.diff(ids) <= 0):
            raise ValueError('Sparse indices must be ordered, unique and in range')
        data[ids] = view(val['bufferView'], s['count'], dt, width, val.get('byteOffset', 0), True)
    if a.get('normalized') and not raw:
        if a['componentType'] not in (5120, 5121, 5122, 5123):
            raise ValueError('Invalid normalized component type')
        data = np.maximum(data.astype('f8') / np.iinfo(dt).max, -1)
    if not np.isfinite(data).all():
        raise ValueError('Nonfinite accessor data')
    return data


def faces(doc, binary, primitive):
    if primitive.get('mode', 4) != 4 or primitive.get('extensions'):
        raise ValueError('Expected ordinary triangle primitives')
    count = doc['accessors'][primitive['attributes']['POSITION']]['count']
    if 'indices' in primitive:
        a = doc['accessors'][primitive['indices']]
        if a['type'] != 'SCALAR' or a['componentType'] not in (5121, 5123, 5125) or a.get('normalized'):
            raise ValueError('Invalid triangle index encoding')
        ids = accessor(doc, binary, primitive['indices']).ravel()
    else:
        ids = np.arange(count, dtype='u4')
    if len(ids) % 3 or ids.max(initial=0) >= count:
        raise ValueError('Triangle indices are incomplete or outside their vertex stream')
    return ids.reshape(-1, 3)


def select_primitive(doc, mesh_name, material_name):
    choices = [(m, p) for m in doc['meshes'] if m.get('name') == mesh_name
               for p in m['primitives'] if 'material' in p
               and doc['materials'][p['material']].get('name') == material_name]
    if len(choices) != 1:
        raise ValueError(f'Expected one primitive for mesh {mesh_name!r}, material {material_name!r}')
    return choices[0]


def append_accessor(doc, buffer, values, kind, component=5126, target=34962, normalized=False):
    values = np.asarray(values, dtype=DTYPES[component]).reshape(-1, WIDTHS[kind])
    if not len(values) or not np.isfinite(values).all():
        raise ValueError('Cannot append empty or nonfinite accessor data')
    buffer.extend(b'\0' * (-len(buffer) % 4))
    vi = len(doc['bufferViews'])
    doc['bufferViews'].append(dict(buffer=0, byteOffset=len(buffer), byteLength=values.nbytes, target=target))
    buffer.extend(values.tobytes())
    ai = len(doc['accessors'])
    spec = dict(bufferView=vi, componentType=component, count=len(values), type=kind,
                min=values.min(0).tolist(), max=values.max(0).tolist())
    if normalized:
        spec['normalized'] = True
    doc['accessors'].append(spec)
    return ai


def position_bounds(doc, binary, *, repair=False):
    result, changes = copy.deepcopy(doc), []
    ids = sorted({p['attributes']['POSITION'] for m in doc['meshes'] for p in m['primitives']})
    for ai in ids:
        a = result['accessors'][ai]
        if a['type'] != 'VEC3':
            raise ValueError('POSITION must be VEC3')
        p = accessor(result, binary, ai, raw=True)
        low, high = p.min(0).tolist(), p.max(0).tolist()
        if a.get('min') != low or a.get('max') != high:
            changes.append(dict(accessor=ai, before_min=a.get('min'), before_max=a.get('max'),
                                min=low, max=high))
            if repair:
                a['min'], a['max'] = low, high
    return result, changes


def topology(points, triangles, decimals=6):
    """Position-welded advisory topology; coincident shells still need visual review."""
    vertices, welded = np.unique(np.round(points, decimals), axis=0, return_inverse=True)
    tri = welded[triangles]
    edges = Counter(tuple(sorted(e)) for f in tri for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])))
    adjacency = defaultdict(set)
    for (a, b), n in edges.items():
        if n == 1:
            adjacency[a].add(b)
            adjacency[b].add(a)
    unseen, components = set(adjacency), []
    while unseen:
        start = min(unseen)
        stack, component = [start], set()
        while stack:
            node = stack.pop()
            if node not in component:
                component.add(node)
                stack.extend(adjacency[node] - component)
        unseen -= component
        xyz = vertices[sorted(component)]
        components.append(dict(vertices=len(component), closed_loop=all(len(adjacency[x]) == 2 for x in component),
                               min=xyz.min(0).tolist(), max=xyz.max(0).tolist()))
    return dict(boundary_edges=sum(n == 1 for n in edges.values()),
                nonmanifold_edges=sum(n > 2 for n in edges.values()),
                degenerate_faces=int(np.sum((tri[:, 0] == tri[:, 1]) | (tri[:, 0] == tri[:, 2]) | (tri[:, 1] == tri[:, 2]))),
                boundary_components=components)
