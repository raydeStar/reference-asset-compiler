"""Geometry-derived painter normals must not inherit the UV atlas's seams."""
from __future__ import annotations

import numpy as np


def install_seam_normal_repair(geometry_module, positions, reference_faces):
    """Patch only this transport's normal calculation; leave geometry/UVs intact.

    Hunyuan recomputes normals from triangle indices instead of reading authored
    OBJ normals. glTF/Trimesh split positions at UV seams, so averaging on those
    indices bakes artificial shading seams into the generated paint. Calculate
    on an exact-position proxy and expand the result to the original indices.
    """
    points = np.asarray(positions).copy()
    faces_at_start = np.asarray(reference_faces).copy()
    unique, inverse = np.unique(points, axis=0, return_inverse=True)
    welded_faces = inverse[faces_at_start]
    if np.any(np.diff(np.sort(welded_faces, axis=1), axis=1) == 0):
        raise ValueError('Normal proxy would collapse a face')
    original = geometry_module.mean_vertex_normals

    def mean_vertex_normals(vertex_count, faces, face_normals, *args, **kwargs):
        if (vertex_count == len(points) and not args and not kwargs
                and np.array_equal(faces, faces_at_start)):
            return original(len(unique), welded_faces, face_normals)[inverse]
        return original(vertex_count, faces, face_normals, *args, **kwargs)

    geometry_module.mean_vertex_normals = mean_vertex_normals
    return {'transport_vertices': len(points), 'normal_proxy_vertices': len(unique),
            'geometry_uv_unchanged': True}
