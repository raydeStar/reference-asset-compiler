"""Geometric reference-pose alignment; no character-specific signed Euler offsets."""
import numpy as np


def align_segment_rotation(rotation, target_direction, source_direction):
    """Swing a target's world reference onto its mapped source segment.

    Preserve its roll and handedness. Zero-length segments and invalid rotations
    fail closed; a sign convention is not a substitute for measuring the leg.
    """
    rotation = np.asarray(rotation, dtype=float)
    a, b = [np.asarray(v, dtype=float) for v in (target_direction, source_direction)]
    if rotation.shape != (3, 3) or a.shape != (3,) or b.shape != (3,):
        raise ValueError('Expected a 3x3 rotation and two 3D segment vectors')
    if not all(np.isfinite(v).all() for v in (rotation, a, b)):
        raise ValueError('Reference alignment requires finite values')
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-5):
        raise ValueError('Reference rotation must be right-handed and orthonormal')
    lengths = np.linalg.norm(a), np.linalg.norm(b)
    if min(lengths) < 1e-8:
        raise ValueError('Cannot align a zero-length segment')
    a, b = a / lengths[0], b / lengths[1]
    cosine = float(np.clip(a @ b, -1, 1))
    cross = np.cross(a, b)
    if cosine < -1 + 1e-9:
        axis = np.cross(a, np.eye(3)[np.argmin(np.abs(a))])
        axis /= np.linalg.norm(axis)
        swing = 2 * np.outer(axis, axis) - np.eye(3)
    else:
        x, y, z = cross
        skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
        swing = np.eye(3) + skew + skew @ skew / (1 + cosine)
    return swing @ rotation
