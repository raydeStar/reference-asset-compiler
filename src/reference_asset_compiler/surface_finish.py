"""Bounded, acquired-surface repairs and diagnostics; no inferred anatomy."""
from __future__ import annotations

import copy
import hashlib
import io
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

from .io import read_json, sha256_file
from .polish_glb import (accessor, append_accessor, faces, position_bounds, read_glb,
                         select_primitive, topology, write_glb)


def bound_file(root, value, digest):
    path = (Path(root) / value).resolve()
    if sha256_file(path) != digest:
        raise ValueError(f'Input hash mismatch: {path}')
    return path


def read_recipe(path, source, schema):
    config = read_json(Path(path))
    if config.get('schema') != schema:
        raise ValueError(f'Expected recipe schema {schema}')
    if sha256_file(source) != config.get('source_sha256'):
        raise ValueError('Recipe belongs to a different source revision')
    if not config.get('acquisition_provenance', '').strip():
        raise ValueError('The acquired-source provenance must be recorded')
    return config


def inspect_surface(source):
    doc, binary = read_glb(Path(source).read_bytes())
    _, bounds = position_bounds(doc, binary)
    records, mesh_records = [], []
    for mi, mesh in enumerate(doc['meshes']):
        mesh_points, mesh_faces, offset = [], [], 0
        for pi, primitive in enumerate(mesh['primitives']):
            attrs = primitive['attributes']
            pos = accessor(doc, binary, attrs['POSITION'])
            tri = faces(doc, binary, primitive)
            mesh_points.append(pos)
            mesh_faces.append(tri + offset)
            offset += len(pos)
            material = doc.get('materials', [])[primitive['material']] if 'material' in primitive else {}
            pbr = material.get('pbrMetallicRoughness', {})
            record = dict(mesh=mesh.get('name', str(mi)), primitive=pi,
                          material=material.get('name', str(primitive.get('material'))),
                          vertices=len(pos), triangles=len(tri), topology=topology(pos, tri),
                          normal_map='normalTexture' in material,
                          response_map='metallicRoughnessTexture' in pbr,
                          specular='KHR_materials_specular' in material.get('extensions', {}),
                          skin_weights='WEIGHTS_0' in attrs,
                          morph_targets=len(primitive.get('targets', [])))
            if 'TEXCOORD_0' in attrs:
                uv = accessor(doc, binary, attrs['TEXCOORD_0'])[tri]
                e, f = uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]
                area_uv = abs(e[:, 0] * f[:, 1] - e[:, 1] * f[:, 0]).sum() / 2
                xyz = pos[tri]
                area = np.linalg.norm(np.cross(xyz[:, 1] - xyz[:, 0], xyz[:, 2] - xyz[:, 0]), axis=1).sum() / 2
                record['uv'] = dict(summed_triangle_area=float(area_uv), surface_area_local_units2=float(area),
                                    tiled=bool((uv < 0).any() or (uv > 1).any()),
                                    area_is_not_unique_coverage=True)
                slot = pbr.get('baseColorTexture')
                if slot:
                    tex = doc['textures'][slot['index']]
                    img = doc['images'][tex['source']]
                    if 'bufferView' in img:
                        v = doc['bufferViews'][img['bufferView']]
                        start = v.get('byteOffset', 0)
                        with Image.open(io.BytesIO(binary[start:start + v['byteLength']])) as picture:
                            w, h = picture.size
                        record['uv'].update(texture_size=[w, h],
                            estimated_texels_per_local_unit=float(np.sqrt(area_uv * w * h / max(area, 1e-12))))
            records.append(record)
        mesh_records.append(dict(mesh=mesh.get('name', str(mi)),
            topology=topology(np.concatenate(mesh_points), np.concatenate(mesh_faces))))
    return dict(schema='reference-asset-compiler.surface-inspection.v1', source_sha256=sha256_file(source),
                primitives=records, meshes=mesh_records, position_bounds_issues=bounds,
                topology_scope='Mesh summaries join material boundaries; primitive boundaries alone are not holes.',
                triangles=sum(r['triangles'] for r in records),
                recommendations=[
                    'Inspect new closed boundary loops against intended garment openings; do not auto-fill every loop.',
                    'Compare albedo, clay and material response before classifying a seam.',
                    'Use UV density to select regions for repack/rebake, then review side and reverse references.',
                    'Boundary counts and texel estimates are diagnostics, not visual acceptance.'],
                coordinate_space='mesh local; node transforms are not applied', production_ready=False)


def repair_bounds(source):
    raw = Path(source).read_bytes()
    doc, binary = read_glb(raw)
    fixed, changes = position_bounds(doc, binary, repair=True)
    # The spell touches metadata only; the suitcase keeps every original byte.
    output = write_glb(fixed, binary)
    assert read_glb(output)[1] == binary
    return output, dict(schema='reference-asset-compiler.position-bounds.v1',
                        source_sha256=hashlib.sha256(raw).hexdigest(), changes=changes,
                        binary_byte_identical=True, production_ready=False)


def restore_surface(source, recipe):
    config = read_recipe(recipe, source, 'reference-asset-compiler.restore-surface-recipe.v1')
    donor = bound_file(Path(recipe).parent, config['donor'], config['donor_sha256'])
    doc, binary = read_glb(Path(source).read_bytes())
    dd, db = read_glb(donor.read_bytes())
    mesh, pr = select_primitive(doc, config['mesh'], config['material'])
    if any('TANGENT' in target for target in pr.get('targets', [])):
        raise ValueError('Tangent morphs need an explicit deformation-aware transport route')
    _, dp = select_primitive(dd, config.get('donor_mesh', config['mesh']),
                             config.get('donor_material', config['material']))
    if doc['accessors'][pr['attributes']['POSITION']]['componentType'] != 5126:
        raise ValueError('Restore needs float positions in the same mesh coordinate space')
    p = accessor(doc, binary, pr['attributes']['POSITION'])
    uv = accessor(doc, binary, pr['attributes']['TEXCOORD_0'])
    q = accessor(dd, db, dp['attributes']['POSITION'])
    quv = accessor(dd, db, dp['attributes']['TEXCOORD_0'])
    old_faces, donor_faces = faces(doc, binary, pr), faces(dd, db, dp)
    chosen = config['donor_faces']
    if (not chosen or any(type(i) is not int or not 0 <= i < len(donor_faces) for i in chosen)
            or len(set(chosen)) != len(chosen)):
        raise ValueError('Select unique, explicit donor triangle indices')
    selected = donor_faces[chosen]
    points = q[selected].reshape(-1, 3)
    low, high = np.asarray(config['bounds'], 'f8')
    if (low.shape != (3,) or high.shape != (3,) or not np.isfinite([low, high]).all()
            or np.any(low >= high) or (points < low).any() or (points > high).any()):
        raise ValueError('Selected donor faces exceed the declared repair bounds')
    tolerance = float(config.get('match_tolerance', 1e-7))
    if not 0 <= tolerance <= 1e-5:
        raise ValueError('Restore only supports coincident existing vertices, not shape fitting')
    dist, ids = cKDTree(np.c_[p, uv]).query(np.c_[points, quv[selected].reshape(-1, 2)])
    if dist.max() > tolerance:
        raise ValueError('Donor position/UV vertices do not match the current acquired surface')
    restored = ids.reshape(-1, 3)
    _, weld = np.unique(np.round(p, 6), axis=0, return_inverse=True)

    def edges(tri):
        return Counter(tuple(sorted(e)) for f in weld[tri]
                       for e in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])))

    existing = {tuple(sorted(f)) for f in weld[old_faces]}
    added = [tuple(sorted(f)) for f in weld[restored]]
    if len(set(added)) != len(added) or any(f in existing or len(set(f)) != 3 for f in added):
        raise ValueError('Repair contains existing, duplicate or degenerate triangles')
    before, patch = edges(old_faces), edges(restored)
    border = [edge for edge, n in patch.items() if n == 1]
    if (len(border) != config['expected_boundary_edges'] or not border
            or any(before[e] != 1 for e in border)
            or any(before[e] + n != 2 for e, n in patch.items())):
        raise ValueError('Restoration must close the declared hole without a flap or triple edge')
    directed = Counter(tuple(e) for f in weld[np.vstack([old_faces, restored])]
                       for e in ((f[0],f[1]),(f[1],f[2]),(f[2],f[0])))
    if any(directed[(a,b)] != 1 or directed[(b,a)] != 1 for a,b in patch):
        raise ValueError('Restored faces must have consistent winding across the closed patch')
    original = copy.deepcopy(doc)
    buffer = bytearray(binary)
    unique, inverse = np.unique(ids, return_inverse=True)
    attributes = {}
    for key, ai in pr['attributes'].items():
        if key in ('TANGENT', 'TEXCOORD_0'):
            continue
        spec = doc['accessors'][ai]
        attributes[key] = append_accessor(doc, buffer, accessor(doc, binary, ai, raw=True)[unique],
            spec['type'], spec['componentType'], normalized=spec.get('normalized', False))
    axes = config.get('uv_axes', [0, 1])
    if len(axes) != 2 or len(set(axes)) != 2 or any(x not in (0, 1, 2) for x in axes):
        raise ValueError('Choose two distinct mesh-space axes for this bounded planar patch')
    xy = p[unique][:, axes]
    span = np.ptp(xy, axis=0)
    if (span <= 1e-9).any():
        raise ValueError('Patch is degenerate in the chosen UV projection')
    new_uv = .1 + .8 * (xy - xy.min(0)) / span
    if config.get('flip_v', True):
        new_uv[:, 1] = 1 - new_uv[:, 1]
    attributes['TEXCOORD_0'] = append_accessor(doc, buffer, new_uv, 'VEC2')
    name = config['patch_material']
    if not name or any(m.get('name') == name for m in doc.get('materials', [])):
        raise ValueError('The restored patch needs a new unique material name')
    material = len(doc.setdefault('materials', []))
    response = config.get('response', dict(roughness=.86, metallic=0, specular=.42))
    if any(not np.isfinite(v) or not 0 <= v <= 1 for v in response.values()):
        raise ValueError('Material response values must be within 0..1')
    doc['materials'].append(dict(name=name, doubleSided=True,
        pbrMetallicRoughness=dict(baseColorFactor=[.015, .028, .030, 1],
            roughnessFactor=response.get('roughness', .86), metallicFactor=response.get('metallic', 0)),
        extensions={'KHR_materials_specular':dict(specularFactor=response.get('specular', .42))}))
    if 'KHR_materials_specular' not in doc.setdefault('extensionsUsed', []):
        doc['extensionsUsed'].append('KHR_materials_specular')
    new = dict(attributes=attributes, indices=append_accessor(doc, buffer, inverse, 'SCALAR', 5125, 34963),
               material=material, mode=4)
    if pr.get('targets'):
        new['targets'] = [{k: append_accessor(doc, buffer, accessor(doc, binary, ai)[unique], 'VEC3')
                           for k, ai in target.items()} for target in pr['targets']]
    mesh['primitives'].append(new)
    for key in ('nodes', 'skins', 'animations', 'scenes'):
        if doc.get(key) != original.get(key):
            raise AssertionError(f'Restoration changed {key}')
    doc['buffers'][0]['byteLength'] = len(buffer)
    result = write_glb(doc, buffer)
    return result, dict(schema='reference-asset-compiler.restore-surface.v1',
        source_sha256=sha256_file(source), donor_sha256=sha256_file(donor), recipe_sha256=sha256_file(recipe),
        restored_donor_faces=chosen, restored_triangles=len(restored), closed_boundary_edges=len(border),
        vertex_match_max_error=float(dist.max()), original_binary_prefix_retained=True,
        original_materials_and_primitives_unchanged=True, inherited_current_weights_and_morphs=True,
        patch_material=name, needs_reference_projection=True, visual_acceptance='pending', production_ready=False)
