# Escalation: the texture stage, not the assets

Raised 2026-08-30 by the compiler after direct investigation. This is the
`ESCALATE.md` the brief asks for when a rubric item cannot be met within three
iterations. It is filed once for all four characters because they share one
root cause.

## What was asked

Fix the visible texture problems: the ninja's poor texture, and the female,
who "needs the most work".

## What is actually wrong

### 1. Facial art is painted into the body atlas on clothed geometry

The female has two flat cartoon eye decals painted into her body albedo, at UV
`(0.366, 0.784)` and `(0.689, 0.428)`. They land on her thighs. Each is a
hard-edged salmon patch with a cream sclera, maroon outline and blue iris —
vector-flat shapes sitting on an otherwise painterly texture. The ninja has two
of the same. The male and the fox have none.

Ruled out by direct measurement, so nobody re-investigates these:

| Hypothesis | Verdict |
|---|---|
| Face material assigned to thigh polygons | **No.** A material-ID render shows the thigh is 100% body material. |
| Head and leg UV islands overlap | **No.** 27 shared texels out of 151,762 leg texels, 0.0%. |
| Wrong colour space on the atlas | **No.** The ninja's dark atlas matches its reference turnaround, which is a black-and-navy outfit. |
| Art is genuinely painted into the leg islands | **Yes.** An unlit albedo render shows the decals with no lighting involved. |

### 2. Lighting is baked into the albedo

Measured as the correlation between albedo luminance and a best-fit directional
light, using surface normals only:

| Asset | correlation | light direction |
|---|---|---|
| fox-mascot | **-0.33** | (-0.21, 0.15, -0.97) |
| field-scout-female | **+0.28** | (0.02, -0.26, 0.97) |
| field-scout-male | **+0.18** | (0.04, -0.71, 0.71) |
| ninja-man | +0.08 | (0.04, -0.71, 0.71) |

A clean albedo has no such direction. Three of four have one. This is the
brief's rule I7, and it was skipped.

### 3. The UV layout is per-patch confetti

| Asset | islands | median island | islands < 64 px |
|---|---|---|---|
| ninja-man | 942 | 24 px | 733 |
| fox-mascot | 515 | 66 px | 250 |
| field-scout-male | 503 | 62 px | 253 |
| field-scout-female | 395 | 74 px | 177 |

Produced by `apply_xatlas_uv.py` in the legacy studio. Every island edge is a
seam and a bleed boundary, which is why detail smears across the ninja's arm
and why the generator was able to paint face pixels into a trouser island in
the first place.

### 4. Texel density is too low on two assets

| Asset | texels/cm² | atlas |
|---|---|---|
| field-scout-female | 306–349 | 4096 |
| field-scout-male | 303–316 | 4096 |
| ninja-man | 145–151 | 4096 |
| fox-mascot | **42–44** | 2048 |

The fox is soft everywhere because a 2048 atlas is spread over a 2 m subject.
The ninja halved when the compiler rescaled it from 0.95 m to 1.80 m — correct
for the character, but it spreads the same texels over 3.6x the surface.

### 5. The female's face is a flat projection

Rendered at 35° it reads as a sticker: the eyes stay flat, the nose has no
dimension, hair fragments float above the scalp, and skin bleeds onto the
scarf. This matches the "stamped or doubled face, landmark displacement" that
`HANDOFF.md` already recorded as rejected. It has not improved.

## What was tried and rejected

Two heuristic repairs were built, tested, and **deleted** rather than shipped:

1. **Mesh-space skin detection and inpainting.** Flagged 7.4% of clothed
   triangles, smeared the female's shirt, and left the thigh decals untouched.
   Strictly worse than doing nothing.
2. **Palette-and-flatness decal removal.** Did cleanly remove the blue irises,
   but the surrounding salmon patches survive as separate islands, and widening
   the sweep started eroding the hands. Partial removal leaves pink tabs on the
   trousers, which is not a shippable state either.

The reason both failed is the same: the flat trouser paint around a decal has a
median local variance of 1.3 against the decal's 0.0, and its colour overlaps
the decal palette. There is no image-space rule that separates them reliably.

## What should actually be done

Patching pixels is the wrong layer. The defects are all produced upstream, in
the back-projection stage, and all four are fixed by the same work:

1. **Give each character a coherent UV layout** — contiguous islands per body
   part, not per-patch xatlas. This alone removes the mechanism that let face
   pixels land on a trouser island.
2. **Delight the reference before projection and the albedo after it**, which
   is what the brief already requires and what the correlation numbers show was
   skipped.
3. **Re-project with the face constrained to head geometry**, so the female's
   face follows her modelled sockets instead of being stamped flat.
4. **Raise the fox to a 4096 atlas** and either accept the ninja at 145
   texels/cm² or re-project it at its final 1.80 m scale.

The legacy studio has roughly seventy scripts for this stage
(`bake_*`, `compose_*`, `apply_*_uv.py` under
`${RAC_LEGACY_ROOT}\scripts`). ComfyUI is installed at
`C:\Comfy\ComfyUI` with models present but is **not running**, and it was not
started: the user's Unreal Editor was open throughout and starting a GPU
service was not authorised for this session.

This is a multi-day stage rebuild, not a fix that belongs inside a compile run.

## What the compiler does about it meanwhile

`scripts/gate_texture.py` measures all four defects on every build and records
them in the shipped manifest. Each asset carries an explicit `texture_waiver`
naming a reason and an approver, so an asset with bad textures ships visibly
flagged rather than silently passing. Tighten the thresholds in
`profiles/skeletons/*.json` as the numbers improve, and delete the waivers when
they are no longer needed.
