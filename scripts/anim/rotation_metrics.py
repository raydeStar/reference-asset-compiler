"""Sign-invariant quaternion distance for export verification (no DCC imports)."""
import math


def rotation_error_degrees(a, b):
    """Return the shortest orientation angle; q and -q are the same rotation."""
    a, b = tuple(a), tuple(b)
    if len(a) != 4 or len(b) != 4 or not all(math.isfinite(v) for v in (*a, *b)):
        raise ValueError('finite four-component quaternions required')
    lengths = math.sqrt(sum(v*v for v in a)) * math.sqrt(sum(v*v for v in b))
    if lengths < 1e-12:
        raise ValueError('zero quaternion has no orientation')
    dot = abs(sum(x*y for x, y in zip(a, b)) / lengths)
    return math.degrees(2 * math.acos(min(1., dot)))
