import numpy as np
import pytest

from reference_asset_compiler.animation_calibration import align_segment_rotation


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
