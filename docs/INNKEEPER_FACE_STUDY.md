# Innkeeper close-up study

2026-09-22. Local evidence is under ignored
`work/moonlit-tavern/innkeeper/face-v4/`. This is a browser working-candidate
study, not human approval or a production face-rig claim.

## What the close-up exposed

The v3 texture pass improved readability, but fixed untextured front, three-quarter,
side and back views still show soft eyelids, lips and hair volumes. Painted
forehead bands also extend into the hair. The existing head atlas already has
two coherent charts: enlarging the atlas again does not solve those shape errors.

The source-derived `reference-head.png` was made with built-in image generation,
using the original innkeeper head crop as the identity reference. The exact
request and source/output hashes are retained in `reference-prompt.txt` and
`reference-lineage.json`. It is a new candidate reference, not an approved redesign.

## Geometry experiments rejected

The pinned Hunyuan single-view runner acquired a separate head from this image.
Its workspace is `work/moonlit-innkeeper-head-v4/`; the generated GLB has
2,230,828 faces. A 6,500-triangle reduction loses too much detail. A 24,000-triangle
reduction preserves the acquired shape at sampled P99 0.642 mm and maximum
1.438 mm deviation, and has no measured boundary or nonmanifold edges.

Those numbers are not an appearance verdict. The isolated painted head is a
better face study, but its attempted attachments leave exposed old-neck remnants,
gaps or stretched joins. Nearest-surface and radial shape transfer into the
original head also fail visual review: they do not establish correspondence
between eyelids, nostrils, lips and the two different hair volumes. Dense sampling,
valid skin weights and an unchanged skeleton cannot make that mapping correct.

The generated hair also makes unwrapping difficult. Minimum-stretch attempts
collapse; an xatlas alternative fragments into thousands of charts. An angle-based
candidate passes sampled numerical UV bounds but still distributes texels poorly.
Do not substitute that layout for the existing two-chart head merely because its
overlap counter passes.

All geometry candidates are rejected for delivery. `geometry-review.json` names
the attempts and reasons. Experimental scripts, their unit checks and the proposed
72k profile are retained in `rejected-tools/`; none is promoted into the maintained
pipeline. They are evidence, not a supported automatic face-replacement feature.

## Useful boundaries for the next geometry attempt

- Match facial landmarks before transferring topology. A nearest-surface hit is
  not a correspondence between anatomical features.
- Retain a continuous, reviewed neck transition. A front face crop cannot prove
  that an attached character is acceptable.
- Use head **and neck** influences for skin masks. The lower face is partly
  weighted to neck bones; a head-bone-only mask leaves old facial paint visible.
- Judge geometry in clay before painting. Reject pinched nostrils, stretched
  cheeks, elongated jaws and intersections even when mechanical rig gates pass.
- The present character has body/head skinning, not separate eyeballs, eyelid
  topology or a facial-expression rig. Texture repair does not supply those.

## Selected repair: camera-aligned colour transfer

Direct full-head Hunyuan repainting was also rejected: the painter placed extra
facial features in the hair. `paint-original-attempt001/`, `original-repaint-v1/`
and its fixed views retain that failure. Successful file validation did not make
this paint visually acceptable. The head painters in this study wrote validated
maps, then exited with native access violation -1073741819; those execution
failures are retained and were not silently retried.

The selected working revision uses the original v3 mesh and two-chart head UVs.
`projection-v1/front-albedo.png` is an unlit render from a known camera. Built-in
image generation edited that render with the original identity crop as a second
reference; `projection-v1/prompt.txt` retains the exact request. The resulting
`donor.png` has SHA256
`d0e3fb8c41fcda4135f365ab5ac495317f5d92954f2d2ad1ba31f9f9da2d1a18`.
This corrected image is a texture donor, not the delivered 3D result.

The existing `map_multiview_face_repair.py` transports it through camera
landmarks into head-only surface correspondence. The first pass selects
1,894,352 texels, 11.29% of the 4096 sheet. Existing `map_face_donor.py` then
repairs the hair band using per-pixel depth visibility without the normal fade
that left grazing hair surfaces unpainted. A tiny side-fold patch transports
hair from the same AI donor through the left camera (12,672 texels). These
hair-only masks do not include the facial landmarks. Full-body geometry supplies
the depth occlusion buffer; UV correspondence includes only the head material.
Each pass proves pixels outside its support and unoccupied gutters unchanged.

The attempted expansion of atlas coverage limits was unnecessary: the selected
passes fit existing limits. That experiment and its checks remain local in
`rejected-tools/`; there is no shipped runtime or automatic-generation change.

Selected files:

- `projected-final-v3/innkeeper.blend`: packed native authority.
- `projected-final-v3/innkeeper.glb`: 33,751,708 bytes, SHA256
  `5c0c4949e9e5e8d6553a7d605c3ae5eb36e5bda5fcb876c5fdbd36fa33d83dbc`.
- `projected-final-v3/export-audit.json` and `material-audit.json`: all vertex
  attributes, indices, UVs, normals, skin weights, rest transforms, hierarchy and
  inverse binds unchanged; five other embedded images bit-identical. Only the
  head BaseColor changes. The 48k triangles and 86-bone body rig remain intact.
- `review-projected-final-v3/`: front, both three-quarters, side, back and two
  body renders. `visual-review.json` records AI review and remaining limitations.
- `projection-v1/`, `projection-left-v2/`, `projected-v1/`, `projected-hair-v2/`
  and `projected-hair-v3/`: input hashes, correspondence, masks and mapping receipts.
- `import_candidate.py`, `database-backup.json`, `library-revision.json` and
  `delivery-checks.json`: revision 4, asset
  `d8a5560a-772d-4b74-87aa-9febcf3816dd`, scene v12. All 62 placements, lighting,
  camera and earlier revisions are retained; only the innkeeper asset binding changed.

The new colour reads more naturally at the face, with softer creases and better
beard/skin detail. It does not add eye geometry, eyelid articulation or a facial
rig. Soft source facial shapes, the coarse rear hair volume and original neck
and clothing paint remain. Human creative approval is still open.
