import math
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts/anim'))
from rotation_metrics import rotation_error_degrees


def test_quaternion_sign_flip_does_not_report_full_turn():
    assert rotation_error_degrees((1,0,0,0),(-1,0,0,0)) == 0
    assert rotation_error_degrees((.5,.5,.5,.5),(-.5,-.5,-.5,-.5)) == 0


def test_orientation_uses_shortest_arc_and_normalizes():
    a = (math.cos(math.radians(359/2)),0,0,math.sin(math.radians(359/2)))
    b = (math.cos(math.radians(1/2)),0,0,math.sin(math.radians(1/2)))
    assert rotation_error_degrees(a,tuple(v*1.01 for v in b)) == pytest.approx(2)
    assert rotation_error_degrees((1,0,0,0),(0,1,0,0)) == 180


def test_bad_quaternions_fail():
    for bad in ((0,0,0,0),(float('nan'),0,0,1),(1,2,3)):
        with pytest.raises(ValueError):
            rotation_error_degrees((1,0,0,0),bad)
