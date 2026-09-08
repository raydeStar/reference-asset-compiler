# Sunset character lighting route: retained failure, not an approved texture

2026-09-05. The user wants the entire polished workshop demo and recognizable
playable Ayric. That objective remains active. This escalation concerns the
IntrinsicAnything lighting-estimation route, not permission to reduce scope.

## Current authority

`work/sunset-ayric-v2/prod-collar-v001` remains unchanged. Head mapping is
preserved. The existing lighting measurement remains -0.23785 versus absolute
.12; no waiver or rig promotion. The scene, independent sword and other props
are not altered by these experiments.

## Three bounded orbit trials

1. `texture/intrinsic-orbit-estimate-v001`: six cameras, original100DDIM
   baseline. Front/back/overhead retain color, exact sides become near-black
   silhouettes. Colored input crops are present; no runtime exception.
2. `intrinsic-orbit-estimate-v002`: replace exact sides with60/300-degree
   obliques. One side improves; the other still loses almost all armor color.
   This falsifies camera angle alone as a sufficient repair.
3. `intrinsic-orbit-estimate-v003`: same oblique inputs, unguided3x1 splits,
   overlap1,100DDIM. Side color returns but large horizontal bands and black
   lower-leg/foot patches appear. Do not average these defects into an atlas.

All runs completed normally; these are visual failures, not missing outputs.
The neural/numerical cause of the collapsed estimates is not proven. Do not
claim it is exclusively aspect ratio, a UV defect or an out-of-memory event.

Hash-bound review: `work/sunset-workshop/evidence/intrinsic-orbit-rejections-v001.json`.
Browsable actual outputs: matching `.html`. Source RGBA renders and exact
camera/UV/depth correspondence are in `intrinsic-orbit-v001/v002`. The earlier
successful front-only base/guided trials remain retained separately.

## Transfer infrastructure, not a transferred asset

`scripts/transfer_intrinsic_illumination.py` implements bounded low-frequency
log-luminance gains, perspective/depth-aware UV transport, head/neck protection,
and unchanged outside-region bytes. Seven tests cover color roundtrip,
background exclusion, gain bounds, invalid/collapsed donors, and a synthetic
full transfer preserving head/source bytes. It was **not run against Ayric**:
the donor review rejected the required inputs first. Do not present synthetic
coverage tests as a corrected character, or use gain clamping to disguise a
black-output failure.

## Next boundary

Stop prompt/angle/crop retries of this same estimator. Any resumed attempt
needs a concrete diagnosed model/preprocessing defect and independent evidence
that the repair fixes it, or a materially different licensed estimation stage.
Do not repeat whole-body Hunyuan Delight, direct donor face replacement, color
tuning to the correlation score, or manual reference reconstruction.

The alternative [compphoto/Intrinsic implementation](https://github.com/compphoto/Intrinsic#license)
states academic use only. It was inspected, not installed or used for this
shareable demo pipeline. Do not silently add it as a production dependency.

Other demo gates remain available: rejected foliage acquisition, sofa material
work, room composition and later custom-character rig/attachment/cooked proof.
Advance an independent asset gate while the character's material route is
reconsidered. This is not evidence that the full goal is blocked or complete.

## 2026-09-05 — new ImageGen brightness-only canary, not promoted

A read-only fixed-height diagnostic rules out removing the old head as a
lighting fix. `work/sunset-ayric-v2/texture/modular-body-diagnostic-v001.json`
measures below-head correlation -0.24840, torso/arms -0.28455 and legs -0.28585.
These are diagnostic sections, not geometry cuts or exemptions from the gate.

One built-in ImageGen edit conditioned on the actual front unlit render:
`texture/imagegen-light-front-v001.png`, exact prompt adjacent. This is a
different estimator from the rejected IntrinsicAnything trials. The donor is
1254x1254; fixed normalized registration to the1024 source has silhouette
IoU0.940865. It supplies only broad scalar linear-RGB luminance gains, not
replacement artwork, hues, facial pixels, geometry or UVs.

`map_imagegen_light_front_v001.py` uses the exact subpixel visibility helper,
fixed16px smoothing and0.5-2x gain bounds. The front-only derivative maps
2,851,469 supported texels. Head/collar and outside-support-plus-gutters bytes
are unchanged. Source FBX and atlas hashes remain unchanged. This job-local
canary does not fake the six-view receipt required by the shared transfer CLI.

Twelve paired actual-FBX CPU renders are retained. Inspection of front/oblique
albedo and diagnostic back/beauty views does not show sufficient delighting;
original side fragmentation remains. Whole-body correlation worsens from
-0.2378495671 to-0.2444257550, still outside the unchanged absolute0.12 limit.
Retain as `rejected_for_production_insufficient_delighting`, not an accepted
partial texture. Do not commission five more donors on this result alone.
The next body attempt needs a materially different, explained repair method;
do not tune smoothing or colors to the score.

Report: `texture/imagegen-light-front-transfer-v001/review.json`.
Panel: `work/sunset-workshop/evidence/body-lighting-canary-v001.html` and JSON.
The accepted rigid-head texture and all live body/workshop/sword authorities
remain preserved. No body gate, rig or gameplay state was advanced.
