# Static props

The compiler was built for characters, and every stage of it assumed one. This
is the route for things that do not have a skeleton, and what it did and did
not take to add it.

First asset through it: `office-chair`, the lineage `HANDOFF.md` records as
explicitly passed.

## The route

```powershell
python scripts\compile_prop.py recipes\office-chair.json
python scripts\build_production.py office-chair
python scripts\promote_production.py office-chair
```

Then the same UE5 import, verify and gallery scripts the characters use — they
now branch on the manifest's `ue5_mesh_type`.

| Stage | Characters | Props |
|---|---|---|
| Intake | `scripts/compile_asset.ps1` -> `normalize_ue5.py` | `scripts/compile_prop.py` -> `normalize_prop.py` |
| Build | `build_production.py` -> `retopo_bake.py` | same, with `--kind static_prop` |
| Rig gate | `gate_rig.py` against a skeleton profile | skipped, recorded as skipped |
| Deformation | `deform_test.py` | skipped, recorded as skipped |
| Texture gate | `gate_texture.py` | same, against `profiles/skeletons/static_prop.json` |
| Publish | `promote_production.py` | same |
| Engine | imports as `SkeletalMesh` | imports as `StaticMesh`, with collision |

## What actually differs, and why

**Intake is a separate script, not a flag.** `normalize_ue5.py` requires exactly
one armature, derives its pivot from that armature, and exports ARMATURE plus
MESH. Three of its assumptions are the skeleton. What it does that a prop also
needs — bake scale and origin into mesh DATA rather than leaving them on object
transforms, rename materials to the shipped convention, point materials at the
files that ship beside the FBX — is about twenty lines, and duplicating those
was cheaper than making the humanoid path read as a two-kind path.

Props also arrive as many objects where a character arrives as one. The chair is
38: five casters, five spokes, five caster forks, seat, back, arms, and a dozen
decorative seams, fasteners and torn patches. The compiler downstream takes
`max(meshes, key=polygons)`, so without a join it would have compiled the seat
cushion on its own and reported success.

**The build stage is the same stage with the skeleton removed.** `--kind
static_prop` turns off weight transfer, the influence cap, the armature
modifier and parent, and the semantic UV charts that are cut at body-region
boundaries. It does not turn off healing, unwrapping, packing, baking, the
atlas sizing rule, or the export. Those are the parts worth having, and they
are worth having on a prop for the same reasons.

**A prop is always re-unwrapped, even when its geometry is kept.** For a
character the rule is the opposite, and deliberately so: where the geometry did
not change, the layout it shipped with is a good one that still fits, and
replacing it took field-scout-male from a clean atlas to 499 shattered islands.
A prop's incoming layout is not a layout. The chair's six materials each tile
their own 256px texture across the surface, covering between 0.55 and 14.6
times the UV square. There is nothing there to preserve, and collapsing six
tiling materials into one atlas is most of why compiling it is worth doing.

**The atlas ceiling is area-weighted, not the maximum.** For a character the
maximum source density is the right ceiling: it carries a body atlas and maybe
a face projection, and the face legitimately sets the bar for the whole sheet.
A prop carries one small tiling texture per surface type, and the maximum lets
the smallest of them decide — the chair's rust patch reads 11,518 texels/cm2
because a 256px tile repeats 2.7 times across a few square centimetres, which
says nothing about what the chair holds. Weighted by the area each material
covers, it holds 62.

**The atlas is bounded from below as well as above.** The ceiling rule alone
would have taken the chair to 1024, which delivers 26 texels/cm2, and the
texture gate would then have rejected it for being soft. The stage is now told
the gate's own floor and will not step below it. The chair lands at 2048: 103
texels/cm2, against a source that holds 62 and a floor of 90.

## Sizing a prop

A character's height is inherited — the cohort is 2 m. A prop has no such
convention, so the recipe has to say what height and why, and "why" has to be a
measurement.

For the chair, two independent rules agree within a centimetre:

- **Anatomy.** The seat top sits at 48.0% of the authority's height. Scaling
  0.414x puts it at 0.489 m, which is exactly field-scout-male's knee — his
  `calf_l` bone head measures 0.4890 m. A seat that meets the knee is what a
  chair is.
- **Manufacture.** The same factor takes the five-star base from 1.62 m across
  to 0.67 m. A real office chair base is 0.65–0.70 m.

The authority was modelled 2.46 m tall, which is not a scale, it is whatever
the generator produced.

## Engine

A prop imports as a `StaticMesh`. Imported as skeletal it acquires a
single-bone skeleton, a physics asset built for a body that does not exist, and
a skeletal mesh component that costs a skinning pass every frame for geometry
that never moves — and it stops being placeable as ordinary level geometry.

Collision is auto-generated from the mesh. A five-spoke base is not convex, so
the hull bridges between the spokes; for something you walk into rather than
roll under, that is the right trade, and it is recorded in the manifest rather
than left to be discovered.

Material slots are bound by NAME, not by index. The chair authority has six,
and assigning the first material to all of them would paint the whole thing in
black frame vinyl and still report success.

## Measured result

| | |
|---|---|
| Source | 38 objects, 10,520 verts, 5,464 tris, 6 materials, 2.460 m |
| Compiled | 1 mesh, 5,336 tris, 1 material, 1.019 m, base on Z=0 |
| Atlas | 2048, 103 texels/cm2, 183 islands, 63.4% coverage |
| Silhouette IoU | 1.000 |
| Gates | texture PASS; rig and deformation skipped by kind |
| UE 5.8.2 | StaticMesh, 101.9 cm, 3 LODs, materials assigned and sampling their textures, 0 failed checks |

The six 256px tiling textures collapse to one 2048 BaseColor plus a packed ORM,
so the chair went from six materials to one.

## Repeatability

The original chair is a hand-authored mesh with 38 named parts and a reference
manifest, so it was a friendly compiler mechanics case. It is now regression
evidence only: the later AI-conditioned geometry contract disqualifies it from
the V1 cohort regardless of its earlier visual approval. The route was also
run against a deliberately
unfriendly one: a 48,000-triangle Pixal3D generation of the same chair, one
material, one UV set, no manifest, no named parts, and no entry in any table in
this repository.

It compiled from a recipe alone -- 48,000 -> 44,302 triangles, one atlas, every
gate of the day passed (see the correction in `docs/FROM-IMAGE.md`: a
triangle-budget gate has since been added, and 44,302 is over it) -- and it
found three things that only ever worked because the chair
happened to be shaped conveniently:

- Textures were staged under the material's name *before* renaming, so the
  build could not match them to the renamed materials in the FBX and reported
  them as untextured. It would have baked flat colour and produced a grey
  asset, with no error anywhere.
- `material_textures` had to be keyed by the post-rename name. Keying it by the
  name actually in the source file -- the obvious thing to write -- failed with
  "material not found", naming a material the recipe never mentioned.
- The asset kind was read from a hard-coded table in `build_production.py`, so
  any prop not listed there was compiled as a character and died several
  minutes in with "need a mesh and an armature". The kind is now read from the
  asset's own manifest, which is where the recipe already declared it.

All three are fixed. None of them was visible while there was one prop.

## What is not done

- **The shipped chair is not V1-eligible geometry.** Its 38-part source was
  hand-authored. A preserved Hunyuan multiview generation is now hash-bound to
  the approved turnaround and all three conditioned views in
  `work/office-chair-ai-v2`; it still requires a reviewed runtime derivative,
  human modeling approval, a new texture approval, and fresh UE/cook proof.
- **The currently shipped chair still loses per-material metallic.** The new
  production route now bakes the authority's six roughness constants and its
  0.18 frame/0.25 rust metallic values through the UV layout, packs them into
  ORM, and wires the same maps into the review FBX. The isolated canary passed
  mechanics and agent fixed-view review; human texture approval plus fresh UE
  import/cook proof remain before replacing the shipped chair.
- **Collision is a convex hull**, so you cannot walk between the spokes of the
  base. Fine for review, wrong for a chair you can push around.
- **One prop has been through this.** The sword and the guitar in `HANDOFF.md`
  have not. The guitar's melted generated mesh remains a recorded rejection;
  the later procedural Blender replacement was also rejected because the image
  did not condition its geometry. A new AI-derived candidate is required and is
  not yet eligible for UV, texture, or compiler work.
