"""The Raider's skin correction, shared by look_face.py (the baked face) and tone_skin.py (arms and chest).

The painted and baked skin ran redder and more saturated than the reference (hue 19 against 22 degrees,
saturation 0.64 against about 0.50). tone() desaturates by SAT, turns HUE degrees towards yellow and lifts by VAL,
each faded in by a per-texel weight; skin_weight() is the weight for skin-like texels (hue under 45 degrees,
saturation over 0.3, brightness over a floor that keeps dark leather and hair out).
"""
import numpy as np

SAT, HUE, VAL = 0.8, 3.0, 1.08


def hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = np.maximum(mx - mn, 1e-6)
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    s = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
    return h, s, mx


def skin_weight(rgb, value_floor=0.3):
    h, s, v = hsv(rgb)
    return np.clip((45 - h) / 10, 0, 1) * np.clip((s - 0.3) / 0.1, 0, 1) * np.clip((v - value_floor) / 0.1, 0, 1)


def tone(rgb, w):
    """rgb: (..., 3) floats in 0-1; w: (...) weights. Returns the toned colours."""
    h, s, v = hsv(rgb)
    h2 = h + HUE * w
    s2 = s * (1 - (1 - SAT) * w)
    v2 = np.clip(v * (1 + (VAL - 1) * w), 0, 1)
    c = v2 * s2
    x = c * (1 - np.abs((h2 / 60) % 2 - 1))
    m = v2 - c
    k = (h2 // 60).astype(int) % 6
    zero = np.zeros_like(c)
    table = ((c, x, zero), (x, c, zero), (zero, c, x), (zero, x, c), (x, zero, c), (c, zero, x))
    out = np.zeros(rgb.shape, np.float32)
    for i, comps in enumerate(table):
        sel = k == i
        for ch in range(3):
            out[..., ch][sel] = comps[ch][sel] + m[sel]
    return np.where(w[..., None] > 0, out, rgb)
