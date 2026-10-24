import numpy as np
import pytest

from reference_asset_compiler.animation_calibration import align_segment_rotation, transport_skin_pose


@pytest.mark.parametrize('side', [-1, 1])
def test_splayed_downward_leg_aligns_inward_without_mirroring(side):
    # This reproduces the sign-sensitive geometry that made the old gait wider.
    target = np.array([side * .05273, .07809, -.43402])
    source = np.array([0., .03440, -.42810])
    corrected = align_segment_rotation(np.eye(3), target, source)
    np.testing.assert_allclose(corrected @ target / np.linalg.norm(target),
                               source / np.linalg.norm(source), atol=1e-10)
    assert np.linalg.det(corrected) == pytest.approx(1)


def test_opposite_segments_and_invalid_inputs():
    corrected = align_segment_rotation(np.eye(3), [0, 0, -1], [0, 0, 1])
    np.testing.assert_allclose(corrected @ [0, 0, -1], [0, 0, 1], atol=1e-10)
    with pytest.raises(ValueError, match='zero-length'):
        align_segment_rotation(np.eye(3), [0, 0, 0], [0, 0, 1])
    with pytest.raises(ValueError, match='right-handed'):
        align_segment_rotation(np.diag([-1, 1, 1]), [0, 0, -1], [0, 0, 1])


def test_bind_transport_preserves_skinning_and_inverts():
    source = np.eye(4)
    source[:3, 3] = [12, 3, 8]
    target = np.eye(4)
    target[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    target[:3, 3] = [10, 5, 9]
    world = source.copy()
    world[:3, :3] = [[1, 0, 0], [0, 0, -1], [0, 1, 0]]
    world[:3, 3] += [2, 0, 4]
    carried = transport_skin_pose(world, source, target)
    vertex = np.array([1.2, 2, 3, 1])
    expected = world @ np.linalg.inv(source) @ vertex
    np.testing.assert_allclose(carried @ np.linalg.inv(target) @ vertex, expected)
    np.testing.assert_allclose(transport_skin_pose(carried, target, source), world)
    np.testing.assert_allclose(transport_skin_pose(source, source, target), target)
    with pytest.raises(ValueError, match='invertible'):
        transport_skin_pose(world, np.zeros((4,4)), target)
