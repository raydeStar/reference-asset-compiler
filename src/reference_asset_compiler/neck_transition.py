"""CPU-only colour-space and bounded seam-weight contracts; no image synthesis."""
from __future__ import annotations

import math


def validate_config(config: dict) -> None:
    """Reject unsafe bounds before loading a creative application or asset."""
    if config.get('schema') != 'reference-asset-compiler.neck-transition.v1':
        raise ValueError('Unsupported neck transition recipe')
    for key in ('bounds_min_m','bounds_max_m'):
        if len(config[key]) != 3 or not all(math.isfinite(v) for v in config[key]):
            raise ValueError('Seam bounds require three finite coordinates')
    if any(a >= b for a,b in zip(config['bounds_min_m'],config['bounds_max_m'])):
        raise ValueError('Seam bounds must increase on every axis')
    for key in ('fade_bottom_m','pixel_fade_bottom_m'):
        values=config[key]
        if len(values)!=2:
            raise ValueError('A feather needs exactly two bounds')
        smoothstep(*values,values[0])
    distance=config['maximum_surface_distance_m']
    if not math.isfinite(distance) or distance <= 0:
        raise ValueError('Surface distance must be positive and finite')
    for key in ('target_roughness','target_metallic'):
        if not math.isfinite(config[key]) or not 0 <= config[key] <= 1:
            raise ValueError('PBR target must be in [0, 1]')
    for key in ('source_blend','body_texture','head_texture'):
        digest=config.get(key+'_sha256','')
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Every authority must have a lowercase SHA256: '+key)
    if not config.get('attribute'):
        raise ValueError('The colour attribute must be named')


def smoothstep(low: float, high: float, value: float) -> float:
    if not all(math.isfinite(x) for x in (low, high, value)) or high <= low:
        raise ValueError('A feather needs finite, increasing bounds')
    t = min(1.0, max(0.0, (value-low)/(high-low)))
    return t*t*(3.0-2.0*t)


def srgb_to_linear(value: float) -> float:
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Texture sample must be finite normalized sRGB')
    return value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4


def geometry_seam_weight(point, distance: float, config: dict) -> float:
    if len(point)!=3 or not all(math.isfinite(v) for v in (*point, distance)) or distance < 0:
        raise ValueError('Non-finite or negative seam measurement')
    if any(v < lo or v > hi for v,lo,hi in zip(point,config['bounds_min_m'],config['bounds_max_m'])):
        return 0.0
    proximity = 1-smoothstep(config['maximum_surface_distance_m']*.75,config['maximum_surface_distance_m'],distance)
    return proximity * smoothstep(*config['fade_bottom_m'],point[2])


def seam_weight(point, color, distance: float, config: dict) -> float:
    if len(color)!=3 or any(not math.isfinite(v) or v<0 or v>1 for v in color):
        raise ValueError('Expected normalized finite RGB')
    geometry = geometry_seam_weight(point,distance,config)
    r,g,b = color
    skin = smoothstep(1.15,1.35,r/max(g,.001)) * smoothstep(1.05,1.25,g/max(b,.001))
    return skin * geometry
