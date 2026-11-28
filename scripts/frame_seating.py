"""Measure the bearing surfaces on an already oriented, metre-scale frame."""
import numpy as np


def foot_centres(points, run):
    """Find the underside of each flange in a local window around its declared foot."""
    points = np.asarray(points)
    centres = []
    for station in (0., run):
        region = points[np.abs(points[:, 0] - station) <= run * .075]
        if not len(region):
            raise ValueError("No acquired foot surface near mounting station.")
        bottom = region[:, 2].min()
        bearing = region[region[:, 2] <= bottom + max(.001, run * .005)]
        xy = (bearing[:, :2].min(axis=0) + bearing[:, :2].max(axis=0)) / 2
        centres.append([*xy, bottom])
    return np.asarray(centres)


def seat_transform(points, transform, run):
    oriented = points @ transform[:3, :3].T + transform[:3, 3]
    lower, upper = foot_centres(oriented, run)
    along = upper[:2] - lower[:2]
    span = np.linalg.norm(along)
    if along[0] <= 0 or span <= 0:
        raise ValueError("The mounting surfaces have no horizontal separation.")
    x, y = along / span
    rotation = np.array([[x, y, 0.], [-y, x, 0.], [0., 0., 1.]])
    seat = np.eye(4)
    seat[:3, :3] = rotation * (run / span)
    seat[:3, 3] = -seat[:3, :3] @ lower
    return seat @ transform


def measure_seats(points, run, rise):
    lower, upper = foot_centres(points, run)
    actual_run, side, actual_rise = upper - lower
    reasons = []
    if (abs(actual_run - run) > max(.001, .01 * run)
            or abs(actual_rise - rise) > max(.001, .01 * abs(rise))):
        reasons.append(f"foot spacing {actual_run:.3f} m run, {actual_rise:.3f} m rise is outside tolerance")
    if np.max(np.abs(lower)) > max(.001, .01 * run) or abs(side) > max(.001, .01 * run):
        reasons.append("Foot centres miss the lower pivot or the mounting plane.")
    return {"run_m": actual_run, "rise_m": actual_rise, "lateral_m": side,
            "lower_foot_m": lower.tolist(), "upper_foot_m": upper.tolist()}, reasons
