# Browser studio contract

*Type: reference*

What this compiler publishes for a browser studio to consume, and what that
studio must never re-derive for itself. The first consumer is Framewright, a
browser storyboard and scene studio that imports models, poses rigs, and binds
clips to scene objects; nothing here is specific to it.

The boundary exists because both sides keep ledgers. Two ledgers that both
decide whether an asset is sound will eventually disagree, and nobody will know
which one is lying. So: **this repository decides, and records the decision in a
receipt. A studio records the hash of that receipt and displays what it says.**

## What each side owns

| This repository | A consuming studio |
| --- | --- |
| Geometry, cleanup, retopology, texture, rig, and clips | The library, revisions, scenes, direction, and review |
| Skeleton profiles and what a rig must satisfy | Which object in a scene plays which clip, and how |
| Gates, receipts, and every quality verdict | Showing verdicts, and refusing what has none |
| Whether an asset is production ready | Whether the artist has approved it for their shot |

A studio never re-runs a gate, re-derives a verdict, or upgrades a claim. If it
needs a stronger claim than a receipt makes, the answer is a new compiler stage,
not a second opinion downstream.

## The thirteen things a studio consumes

### 1. Skeleton profiles

`profiles/skeletons/*.json` is the single source of truth for what a skeleton
must contain. A studio reads these files; it does not carry its own copies of
them, and it does not invent profiles of its own.

Binding fields:

| Field | Meaning |
| --- | --- |
| `profile_id` | The stable identity. A studio stores this string against an asset. |
| `required_bones` | Every one must be present, by exact name. |
| `expected_parents` | Each named bone's parent must match. Names alone are not the contract. |
| `optional_bones` | Present or absent, both fine. Absence is a downgrade, not a failure. |
| `allow_unlisted_bones` | Whether bones outside the lists are tolerated. |
| `exact_bone_count` | When present, the count must match exactly. |
| `root_bone`, `root_may_be_armature_object` | What counts as the root, and whether the armature object may stand in for it. |
| `max_influences` | The per-vertex influence ceiling. |
| `tri_budget` | The triangle budget for the payload. |

`static_prop.json` is the no-skeleton case: zero required bones. It is an
ordinary answer for a prop, not a failure.

A studio that cannot read profile data reports that it cannot, and declines to
make profile claims. It does not fall back to a built-in guess.

### 2. The browser payload

A self-contained GLB, exported from the same staged scene the FBX comes from:

- glTF 2.0, binary container, one file. No external URIs for buffers or images.
- **+Y up, metres.** Blender's glTF exporter converts the Z-up staged scene on
  export, so the payload arrives in browser convention. **A studio performs no
  axis or unit conversion on import**; if a payload needs converting, the export
  is wrong, not the import.
- Within the profile's `tri_budget` and within whatever ceilings the consuming
  studio declares. The studio refuses what exceeds them, with the number.
- Textures embedded, and found through the export's own `.ue5import.json`
  rather than by name. A production package renames its textures on the way out
  and packs occlusion, roughness and metallic into one image, so the names the
  FBX carries match nothing on disk; the manifest is the only record of which
  file belongs to which material and slot. The pack's green and blue reach
  roughness and metallic, which is the arrangement glTF stores, so the payload
  carries one `metallicRoughnessTexture` rather than two invented ones. The
  receipt names every slot bound and every one missing, because the failure
  mode here is silent: geometry arrives correct and the model renders white,
  which reads as a broken asset rather than a missing file.
- A lighter derivative may accompany it (see
  `apps/lakeside-village/README.md` for the `.web.glb` precedent: reduced
  textures, every non-image buffer byte preserved, both hashes recorded).

The payload's SHA-256 is what a studio stores. Content addresses the asset;
names do not.

A studio runs it by name, never by path:

```
rac run-stage --list                     # what can run here, and what is missing
rac run-stage browser-payload --source <staged.fbx>     --output <payload.glb> --report <receipt.json> [--textures <manifest.json>] [--repo-root ...] [--blender ...]
rac run-stage geometry        --source <reference.png>  --output <candidate.glb> --report <receipt.json> [--asset-name ...] [--seed ...] [--steps ...] [--octree-resolution ...] [--chunks ...] [--legacy-root ...]
```

`--textures` names the manifest to bind instead of the one beside the source,
for a source that has none of its own. An assembled working file is the case
that needs it: a head fit carries a preview material, and the manifest
describing the paint it should ship with belongs to the package it was exported
as, not to the blend. A material the manifest names is rebuilt before binding
rather than bound over, because a preview's leftover nodes are still something
the exporter reads. A named manifest that does not exist is an error, never a
quiet fall back to name matching: the caller would believe production paint had
been applied while the payload shipped a preview.

`--list` runs nothing and answers the capability question: whether the checkout
and Blender are present, and which stages are therefore available. A stage that
cannot run is refused before any work starts rather than an hour into it. The
run returns the stage's own receipt inline, so one call gives one answer, and a
failure carries its stdout and stderr tail with it: hunting a log on another
machine is not diagnosis. Blender is named by `--blender` or `$RAC_BLENDER` and
never discovered by searching, because a guessed executable is a different
Blender from the one an asset was gated with and that difference is invisible in
a receipt.

Stages are a registry rather than an arbitrary path, so a consumer naming a
stage cannot ask this compiler to execute anything else, and the files can move
without breaking anyone downstream.
`scripts/blender/export_browser_payload.py` writes the payload, from the same
staged scene the FBX comes from, and reports what it exported. The skeleton fingerprint
is then taken from that written file by `glb_skeleton.read_skeleton`, never from
the exporting scene's memory, for the precision reason stated below.

### 3. Receipts

A studio records, per imported revision:

- the payload hash,
- the compiler version that produced it,
- the `profile_id` the rig was gated against,
- the hash of the stage receipt, and
- the ledger's `production_ready` flag, verbatim.

`gate-rig-report.json` and `deform-report.json` are the review evidence a studio
displays for a rig: required-bone counts, parent mismatches, facing, mesh and UV
integrity, and the deformation pose suite with its numbers and rendered views.
A studio shows these; it does not recompute them.

An asset whose ledger is incomplete is displayed as unapproved. `production_ready`
is a separate field from stage completion for exactly this reason.

### 4. Clips

A clip is delivered as a GLB carrying `animations`, authored against a specific
rig. Per clip, a studio needs:

| What | Where it comes from |
| --- | --- |
| Name, duration, target bones, interpolation | Read from the file by the studio |
| Whether the clip translates the root bone | Read from the file; the compiler also declares it |
| The fingerprint of the rig it was authored against | The clip's skeleton, or a receipt beside it |

Two deliveries are valid: a clip GLB that carries the skeleton it was authored
against (the fingerprint is derivable), or a clip-only GLB with a receipt that
states the fingerprint.

**Root motion**: the compiler declares whether a clip moves the root. The studio
decides what to do about it — hold the character in place, or offset the object
once. The compiler never also applies it. Exactly one side moves the object.

Only interpolations a consumer can sample exactly should be published for
browser use: LINEAR and STEP. A clip that needs CUBICSPLINE is reported with the
reason rather than published as an approximation of itself.

For a GLB that carries several named clips, `rac export-animations SOURCE OUTPUT
--clip NAME [--clip NAME ...]` writes a new GLB containing exactly those
animation declarations. Omitting `--clip` writes a rest-pose GLB with no
`animations` field. Names must be unique and present in the source. The command
does not rewrite mesh, skin, material, or texture declarations; it preserves
the binary chunk byte for byte, so unused animation samples may still occupy
space in a selective export. The source and any existing output are never
overwritten. This is a packaging choice, not an approval or quality verdict.

### 5. Geometry candidates

`geometry` is the one stage that needs a GPU, and it is the route from a picture
to a mesh: one reference image in, one candidate out. A studio names an image
and gets a candidate; it does not have to know about workspaces, intakes,
source authorities or attempt numbering, because the stage writes all of that
in the shape the launcher's own preflight demands, before anything is queued.
What the stage does **not** do is judge the result. It produces a
`geometry-candidate.v1` receipt whose status says, in those words, that this is
a candidate and not an asset. Deciding otherwise is a person's job.

Three things about it are worth relying on. Preparation touches no GPU, so a
request that could never be accepted is refused while it is still free to
refuse. Attempts are numbered and never reused, so a disappointing result stays
on disk beside the settings that produced it, and asking again produces a new
attempt rather than overwriting the old one. And a workspace's intake is
immutable: asking for a model from a different image under a name already taken
is an error, because that intake is what binds every later candidate, receipt
and rig back to the picture a person actually chose.

Geometry is absent, not broken, on a machine without the weights. `--list`
reports which of `legacy-root`, `geometry-environment`, `hunyuan-checkout` and
`runners` are missing, by name, so a studio refuses with a reason rather than
queueing work it could never finish.

A candidate is not a payload, and it is not a runtime mesh either. What a
generator produces is dense: the Trial Lantern arrived at 2,380,114 triangles,
and exporting that straight to a payload gave a 198 MB file no browser should
be asked to load. Two stages sit between:

```
rac run-stage stage-mesh  --source <candidate.glb> --output <staged.blend>  --report <r.json> --size knee [--size-adjust 0.85]
rac run-stage remesh      --source <staged.blend>  --output <runtime.glb>   --report <r.json> [--triangle-budget 20000]
```

### 6. Real size, said the way a person can judge it

`stage-mesh` exists because a generator normalises: whatever it makes arrives
about two metres tall, a lantern exactly as much as a person. That matters more
than it sounds, because the reduction gate measures surface deviation in
**absolute metres** — and the same lantern, the same settings and the same reduction were
*rejected* at 1.99 m (p99 5.6 mm, max 217 mm) and passed comfortably at 0.42 m
(p99 1.03 mm, max 2.03 mm). A millimetre gate against an arbitrarily scaled
mesh is not measuring the asset.

Asking for metres is the obvious fix and the wrong one: almost nobody can say
whether a trial lantern is 0.3 m or 0.45 m, and a number invented to get past a
prompt is worse than none. People are good at a different question — standing
next to it, where does it come up to? So `--size` is a landmark on a person
(`ankle`, `mid-calf`, `knee`, `mid-thigh`, `hip`, `waist`, `chest`, `shoulder`,
`eye`, `head`, `overhead`) and `--size-adjust` covers "a bit under the knee"
without inventing a landmark every few inches. The landmarks are fractions of
stature against a declared reference height, so a production working at a
different reference changes one number rather than a table, and the receipt
records the landmark, the adjustment and the reference — not only the metres.

A stage with no size refuses. It does not guess, because a guessed size
silently invalidates every measurement after it.

Both reducing stages take the mesh to a runtime budget, with the V1 cohort
contract as the target: no more than 15,000 vertices and 20,000 triangles.
Which one to use is decided by where the mesh came from, and this is not a
preference.

**`remesh` for a generated surface.** A generator's output is marching cubes:
no edge loops, no flat regions, nothing an edge collapse can hold on to.
Collapsing it directly keeps every bit of that noise, compressed into slivers
and spikes — the Trial Lantern came back creased and pocked across its roof and
shoulders at 20,000 triangles, and the fault was never the budget. `remesh`
rebuilds the surface on a uniform grid first, which throws the noise away
instead of compressing it, and collapses what is then an even surface. Same
silhouette, 9,000 vertices and 18,000 triangles in fourteen seconds, and a
wireframe of even triangles rather than a soup of slivers.

**`reduce-mesh` for an already-clean authority**, where a person chose the
topology and rebuilding would discard it. Its feature-weighted collapse
protects high-curvature regions, which is the right instinct when there is
structure to protect and the wrong one when there is only noise.

Both report `mechanical_pass`, never approval — `production_grade` is false and
`requires_fixed_view_review` is true in every receipt either writes, because low
surface error can still leave a silhouette an artist rejects. Attempts are
numbered and never overwritten, so a rejected reduction stays beside the
settings that produced it and the next settings are chosen by reading it rather
than by guessing again.

### 7. Paint, and the map it needs first

A generated mesh has no colour and no UVs. Nothing in generation makes them and
nothing in reduction keeps them, so the painter fails on a missing attribute
deep inside a mesh library rather than saying what it wants. Two more stages:

```
rac run-stage uv-unwrap --source <runtime.glb> --output <transport.obj> --report <r.json> [--allow-triangulated-glb]
rac run-stage texture   --source <transport.obj> --output <painted.glb> --report <r.json> --reference <image.png> [--views 6] [--resolution 512]
```

`uv-unwrap` unfolds the mesh onto a map and moves no vertex — the transport it
writes is checked against the source to within a micrometre, and its report
carries both hashes. `--allow-triangulated-glb` accepts an approved static
triangle mesh as it stands rather than welding or remeshing it, which is what a
generated prop is.

`texture` is the only stage that takes a second input: the same reference image
the geometry came from, because the paint is conditioned on it. Only the caller
knows which picture an asset is of, so it is named rather than guessed. The
painter needs **21 GiB of free VRAM**, refuses face-order, geometry or UV drift
beyond `1e-6`, and never auto-retries.

It is also the one stage whose exit code is not its verdict. The painter can
fault during teardown *after* writing its maps and passing its own gate; the
launcher says so in as many words, that process health is separate from whether
the paint is sound. So this stage is judged by what it produced, and records
the abnormal exit rather than hiding it. **No other stage gets that leniency**,
and the reason is the reducing stages: a rejected reduction writes both a
candidate and a report and *then* exits nonzero, because that is how it says the
collapse cost too much. Treating "it produced its files" as success there would deliver
a rejection as a finished asset.

Turning the result into something a browser loads is the `browser-payload`
stage above, run on the painted mesh. The stages are separate rather than one
because the mesh a generator produced, the mesh at its real size, the mesh at a
runtime budget, the mesh with a map, the painted mesh and the file a browser
loads are different artifacts with different review.

### 8. Fixed views, for the judgement nothing automatic can make

```
rac run-stage review-views --source <mesh.glb> --output <views/> --report <views.json> [--resolution 768]
```

Every reducing and painting stage in this contract reports `mechanical_pass`
and never approval, and every receipt says `production_grade: false` and
`requires_fixed_view_review: true`. This is the stage that produces what that
review is of.

Four views — front, three-quarter, side, back — in two passes. The beauty pass
is the textured read. The matcap pass is flat clay under a normals matcap,
where faceting and flipped faces have nowhere to hide behind albedo detail. A
good front view cannot conceal a broken side, which is why the set is fixed
rather than chosen.

This is the one stage whose `output` is a **directory**, and it says so:
`output_suffix` is empty. Naming a single file would be choosing in advance
which side of the asset counted. The manifest binds every picture to the hash
of the mesh it is a picture of, because evidence nobody can tie to a source is
a screenshot rather than evidence, and it carries `judged: false` — nothing
here is a verdict.

Evidence is retained, never replaced: rendering into a directory that exists is
refused, so an older judgement can never come to refer to pictures nobody can
see any more.

### 9. Preparing a mesh somebody has already reviewed

```
rac run-stage adopt-mesh  --source <mesh.glb>     --output <adopted.blend> --report <r.json> [--require-uvs]
rac run-stage reduce-mesh --source <adopted.blend> --output <runtime.glb>  --report <r.json> \
    --triangle-budget <n> --runtime-derivative
```

A generated mesh and a library mesh need opposite handling, and getting that
backwards is the mistake this section exists to prevent.

A generator's output has no topology worth keeping: it is a marching-cubes
surface with no edge loops, no UVs and no materials, so it is **rebuilt** on a
uniform grid (`remesh`) and painted from scratch. A mesh already in a studio's
library is the other way round. Its UVs, its materials and its shell are what
somebody looked at and accepted, and a preparation that rebuilt any of them
would be throwing the review away and calling the result a derivative.

So this route **adopts** rather than converts-and-fixes. `adopt-mesh` imports
the transport mesh, bakes the importer's own object scale into the vertex data
and saves a `.blend`. It does not scale to a human landmark -- the size is
already the size -- and it does not weld, triangulate, reorder or reproject.
Its receipt records the counts, the extent, the UV layers and the materials
with their images, because a derivative that quietly lost the second UV map or
half the materials is a real loss and nobody can see a loss without a record of
what was there first. `--require-uvs` refuses a mesh with no UV layer by name,
up front, rather than delivering a derivative nobody can paint.

`reduce-mesh --runtime-derivative` is then the same collapse with the same
deviation thresholds, judged for a different purpose. Three things change,
together, because they only make sense together:

- **Inherited boundaries are not filled.** The authority path closes the
  source's open edges before collapsing, which invents surface the source never
  had and then measures the derivative against an original that does not
  contain it.

  Most of what looked like open edges was never open. See *Seams are not
  holes*, below: once a mesh is welded by position, a sword that read 3,888
  boundary edges reads zero and a lantern that read 12,358 reads six. The
  relaxation below is still right for an asset that is genuinely open -- free
  cloth edges, separate glass, unclosed shells -- but it is needed far less
  often than it first appeared, and it was doing work the measurement should
  have been doing.
- **An open candidate is a recorded finding, not a failure** -- but only where
  the source was open too. Ordinary game art is open: separate glass, free
  cloth edges, unclosed shells. Judged as a production authority it can only
  ever be rejected, for a reason that was true before the reduction ran. A
  reduction that opens a surface which *was* closed is still a failure, because
  that is damage rather than inheritance, and that check is what stops the mode
  from meaning "do not look".
- **The exported GLB keeps its materials.** On the authority path that file is
  a review copy for looking at shape, and the `.blend` beside it is the
  contract. Here it is the deliverable.

Nothing about the deviation thresholds is relaxed, `status` is still only ever
`mechanical_pass`, and `production_grade` is still `false`. The receipt carries
`mode: runtime-derivative` and an `accepted_findings` list naming every
allowance in words, because a relaxation nobody can read in a receipt is a
relaxation nobody can argue with later.

The native `.blend` is retained beside the deliverable, as it is on the
authority path. A derivative is not a replacement, and the thing a later pass
would need to reduce differently is the editable mesh, not the transport.

Fixed views (section 8) are rendered for the **source and the derivative
both**. Comparing the two is the review; a derivative's views on their own show
only that something rendered.

### 10. Surfaces, and the detail a mesh already implies

```
rac run-stage survey-surfaces --source <mesh.glb> --output <survey.json>  --report <r.json>
rac run-stage bake-detail     --source <mesh.glb> --output <lit.glb>      --report <r.json> [--resolution 1024] [--edge-wear 0.25]
rac run-stage assign-surfaces --source <lit.glb>  --output <surfaced.glb> --report <r.json>     --assign blue:dark=crystal --assign teal:bright@0.7-0.82=gemstone
```

A painter answers in one material. A whole sword arrives as a single opaque
surface, and every part of it inherits whatever that paint's roughness and
metallic maps happened to say. Measured on one real asset: metallic 0.99 across
72% of the surface, so the blade, the bright edges and the stone at its throat
were all being rendered as rough metal. Metal cannot transmit light at all,
which is why no amount of adjustment would ever have made that stone read as a
stone. It was the wrong class of material, not the wrong numbers.

**A part** is named the way somebody points at one: a colour family, where that
colour sits in value, and optionally a band of the model's height as a fraction
from foot to crown. Tone is not decoration -- a sword's body and its gem are
both blue, and it is the only thing that separates them. Height is there for
the parts colour cannot reach at all: a gem and the bright edge running down a
blade are painted the same, because to a painter they are the same material.
The most specific part wins, band over tone over colour.

**A surface** is a name, not a set of numbers: crystal, gemstone, glass,
polished metal, brushed metal, cast metal, glossy, matte, leather, cloth. The
numbers live in `profiles/materials/recipes.json`, which both the offer and the
application read, so a name means one thing. A caller asks for a kind of
material because a name is something that can be argued with and a slider is
not.

**The survey** says what a model is currently made of, part by part, and which
named surface each part's measurements are nearest to. That is what a proposal
gets made against: an agent looking at a render can say "the blade reads like
plastic" and be right, and still have no way to say which faces it means. With
`reads_as` in the same vocabulary, judging a part is a comparison -- is this
what it is supposed to be? -- rather than an invention.

**Baking** adds what the geometry already implies and nothing else. Occlusion
is how much of the sky each point can see; curvature is how the surface bends.
Both are measurements of the mesh that is already there. Two things about
where they go:

- Occlusion is written to glTF's **own occlusion slot**, never into the packed
  roughness map. `assign-surfaces` releases the roughness map on any part it
  gives a new surface, and occlusion living in that map would go with it.
- Unreached sheet is filled with the value meaning *nothing here* -- white for
  occlusion, mid grey for curvature -- because only about a quarter of a
  typical sheet is reachable by geometry, and a renderer sampling a hair
  outside an island would otherwise read fully occluded and put a black rim
  around every part.

Run order matters: bake before assigning surfaces, so the copies inherit the
occlusion.

**What the fixed views cannot tell you.** Blender computes real global
illumination, so it ignores a glTF occlusion map entirely -- the review renders
of a baked model and an unbaked one are identical. Occlusion is a real-time
renderer's convention and shows in one. Judge it in the studio's viewer, not in
section 8's evidence.

### 11. Seams are not holes

glTF stores one UV per vertex, so an exporter splits a vertex at every UV and
normal seam. A mesh arrives from any glTF importer already torn apart along
each one, and anything that counts boundary or non-manifold edges on it is
counting seams rather than geometry.

Measured, welding by position and re-counting:

| asset | as imported | welded | what it is |
|---|---|---|---|
| Ayric sword | 3,888 boundary, 3,888 non-manifold | **0 and 0** | closed, fully manifold |
| Trial Lantern | 12,358 and 12,358 | **6 and 6** | closed but for six edges |

Both are sound surfaces. A gate reading the unwelded numbers refuses them for a
defect they do not have, and a repair acting on those numbers does real damage:
filling 5,115 "holes" that were seams welded across them and invented surface,
and a faithful reduction of the lantern came back **263 mm** out on a 424 mm
object. Welding first, the same reduction is **4.5 mm** out, and the sword
passes the strict production gate outright at 1.71 mm on a 1.35 m blade.

The weld is safe because Blender stores a UV per face corner rather than per
vertex: rejoining the split vertices keeps every seam exactly where it was.
Welding is for measuring and for collapsing; the exporter splits them again on
the way out, because that is what the format requires.

The general rule, for anything that measures a mesh that arrived as glTF:
**weld by position before counting anything.** The same trap catches vertex
counts, component counts and watertightness, and it is silent every time.

### 12. Faces nothing can see

A decoded mesh carries geometry nobody will ever look at: interior shells left
where a decoder could not resolve two nearby surfaces, the inward faces of a
hollow body, fragments sealed inside. It costs triangles and texture space, and
it competes for the budget a reduction is trying to spend on the silhouette.

`cull-unseen` stands outside, looks from 64 evenly spread directions, and keeps
what it saw. A ray leaves from just off a face and, if it travels four model
widths without striking the mesh again, that face was visible from somewhere.
Nothing moves: faces are deleted, never repositioned, so every crease stays as
sharp as it was and no UV shifts. There is no threshold and no voxel size to
tune. And because it never asks whether two surfaces are *near* each other, two
coils that nearly touch cannot fuse -- which is the failure mode of
merge-by-distance and of voxel remeshing, and this is immune to it by
construction.

Measured across this library:

| asset | faces | removed | what it is |
|---|---|---|---|
| Trial Lantern (generated) | 591,994 | **47%** | raw decoder output, hollow |
| ninja-man | 54,220 | **35%** | a rigged character under clothing |
| field-scout-male | 67,907 | 1.9% | already clean |
| ayric-head | 19,988 | 1.4% | a little inside the mouth |
| fox-mascot-live | 69,545 | 0.7% | already clean |
| Ayric sword | 18,000 | **0%** | refused: nothing was hidden |

The sword's zero is the answer, not a failure. It came through a reduction that
already produced a closed manifold surface, so there is nothing inside it.

**Four things this got wrong first, each of which looked right in the report.**

*Normals are a hint, not a fact.* Firing only into the hemisphere a face points
at assumes an exporter got the winding right. On a rigged character, 5,950
faces -- a quarter of everything that test called hidden -- were in plain sight
from their other side, and culling on that answer took the boots off and left
the soles floating. Both sides are tried now, and the normal only decides which
ray to try first and which side to lift the origin to.

*The importer's own scaffolding is not the model.* Blender's glTF importer
builds bone display shapes and parks them in a collection named
`glTF_not_exported`. An 80-face probe sphere sitting there wrapped a character
from the waist down; a ray stops at it like anything else, so his legs were
invisible and every number stayed correct while they were deleted. Anything in
that collection is excluded from the occluders.

*A ray cannot see through glass.* Transmission is not something a ray test
models, so on the glazed lantern this would delete exactly what you look at
through the panes. A model with a transmissive or non-opaque material is
refused by name unless `--ignore-transparency` says in as many words that
nothing behind those surfaces matters.

*Deleting faces must not touch the rig.* Exporting the selected meshes leaves
the armature behind, and a character arrives with all 75 joints gone. The whole
scene is exported with `export_skins`, and the joint count is read back out of
the delivered bytes and compared; a mismatch deletes the output and fails.

*And it must not invent vertex data either.* The raw lantern carries POSITION
and nothing else -- 295,768 vertices shared across 592,000 faces. Exported with
normals, every one of them splits three ways into 929,393, and a file that had
just lost 47% of its faces came back **two and a half times larger**. Whatever
attributes came in are the attributes that go out, and every report carries the
byte count before and after, because fewer faces does not always mean fewer
bytes and that is not something anybody should have to discover. Corrected, the
same lantern goes from 10.2 MB to **5.4 MB**, its vertices still shared.

**Three refusals rather than surprises.** More than `--most` (default 0.6) of a
model unseen is not a cleanup -- the usual cause is inward-facing normals -- so
it is refused. A connected part disappearing whole that is larger than
`--largest-part` (default 0.1) of the model is something somebody modelled,
sealed inside something else, rather than debris. And when more than
`--shadowed-by-others` (default 0.1) of the faces are hidden by a *different*
object in the file rather than by the model itself, the stage says so and stops:
the same question is asked again with the rest of the file taken away, and
whatever escapes then was never hidden by the model at all.

**Two honest limits**, both stated in every report. An outward-facing flap
floating just above the true surface *is* seen, so it survives: this removes
interior shells, enclosed fragments and back-facing debris, a large share and
not all of it. And layered cloth loses the sandwiched inner layer, which on the
ninja changed about 1% of the rendered pixels -- the hanging waist strips read
as separate pieces rather than a continuous skirt. It is the first step of a
cleanup, not the whole cleanup, and every result carries
`requires_fixed_view_review` and `production_grade: false`.

Cost is roughly 300,000 rays a second, because an exterior face escapes on its
first ray and only buried faces pay the full sweep: 35 seconds for a 54,000
face character, a few minutes for 592,000.

The method was taken from `visibility_cull.py` in `Bingeljell/image-to-3dlab`,
which reached it first. That repository carries no licence file, so nothing was
copied from it: the reasoning is theirs, the code here is not.

### 13. A hero, painted twice

A generated character is painted once, from twelve views of the whole figure.
That paint is as good as the diffusion behind it, and the diffusion saw the
face as about ninety pixels of a 768 view. Nothing downstream -- no atlas size,
no upscaler, no normal map -- can put back what it never saw, and a face that
survives a pan is what a close-up is of.

So the ninja was measured end to end, and the texture chain turned out to be
leaking in four places before the diffusion's limit was even reached:

| where | what was happening | now |
|---|---|---|
| the painter | computed a 4096 atlas and saved it at 2048, as JPEG | `--atlas 4096`, PNG |
| the bake | re-encoded a changed JPEG base colour as JPEG again: 730 KB became 298 KB | written once, as PNG |
| the relief | read every UV island's edge as a cliff, and outlined all 601 of them | gutter filled first; uncovered texels flat |
| the runner | python-run stages were handed their three paths and no options | options reach them |

And one further up, found only because a mask came out covering 92% of a
sheet: the hi-res paint variant loaded the mesh with `maintain_order=True`,
which keeps the OBJ's positions instead of splitting them per UV corner. One
UV per vertex cannot carry a seam, so on a Smart-Projected mesh **a third of
all faces** spanned the atlas and were painted with whatever the sliver
crossed. The earlier experiment's "the jacket's olive spread across the face"
was this, not the painter. The studio runner loads with `force="mesh"` and no
merging, and the head stage's own mask would have caught it again.

Then the head. `paint-head` reads the painted GLB, keeps every face whose
lowest vertex sits above `--head-from` (default 0.78) of the model's height,
and writes them as an OBJ carrying the file's own UVs. It crops the reference
to the same band from the figure's own silhouette -- background removed,
bounding box measured, a square around the head's columns -- because a crop
done by hand once kept a strip of armour and the painter spread armour colour
over the whole head. It paints that OBJ with that crop through the same
launcher, at the same views and resolution and sheet, so every view is full of
the head. Because no vertex and no UV changed, the second paint lands in
exactly the rectangles the first one did, and laying it back is a mask in UV
space: head texels from the head paint, body texels byte for byte from the
body paint, a `--feather` (default 0.03 of the height) blend across the cut.
The base colour and the metallic-roughness map are both composited; the
weights sheet is kept beside the paint as evidence.

Nothing in it needs Blender. The mesh is read out of the GLB, the OBJ is
written by hand, the composite is numpy, and the images are swapped into the
same file around the same buffer views -- so what went in rigged would come out
rigged, though a freshly painted model never is.

Refusals: fewer than fifty faces above the cut, or more than 60% of the model,
is not a head and says which way to move `--head-from`; a model with more than
one material has already had its surfaces changed and is refused, because a
second paint would fight that; a head paint that moves a vertex or a UV by
more than 1e-6 is refused by the same gate the body paint answers to.

The body's own paint for these faces is still what is under the mask, so a
studio that wants the old head back has it in the previous step's file.

## Skeleton fingerprint

Both sides compute this, so it is specified to the digit. It identifies the
exact skeleton a clip was authored against, which is what lets a rig with no
standard profile — a spider, a machine — still carry clips honestly. A matching
fingerprint means *these clips were made for this skeleton*. It is not a claim
that anything retargets.

Input: the joints of the first skin, and nothing else. Not the mesh, not
materials, not nodes outside the skin.

```
canonical = "rac-skeleton-v1\n"
for each joint, ordered by bone name using ordinal (byte) comparison:
    canonical += name + "|" + parent + "|" + T + "|" + R + "|" + S + "\n"
fingerprint = lowercase hex SHA-256 of canonical encoded as UTF-8
```

- `parent` is the parent joint's name, or the empty string when the joint has no
  parent inside the skin.
- `T` is the rest translation, `S` the rest scale, each three quantized numbers
  joined by `,`. `R` is the rest rotation as a normalized quaternion `x,y,z,w`.
- **Quantization** — to keep two languages agreeing, a value is quantized to an
  integer and written as that integer, never as a formatted decimal:
  `q(v) = floor(v * 1000000 + 0.5)` for `v >= 0`, `ceil(v * 1000000 - 0.5)`
  otherwise. This is round-half-away-from-zero, stated explicitly because
  .NET's `ToString("F6")` and Python's `format(x, '.6f')` round halfway values
  differently. `-0` is written `0`.
- **Quaternion sign** — a quaternion and its negation are the same rotation, so
  canonicalize to `w >= 0`: if `w < 0`, negate all four components before
  quantizing. Without this, the same skeleton can produce two fingerprints.
- A non-finite value anywhere means no fingerprint. Such a rig is already
  failing its gate.
- **Quantize the values as the payload stores them**, which for glTF means
  32-bit floats. Both sides must read the transforms out of the exported file
  rather than out of a higher-precision authoring scene, because two values that
  differ in the seventh significant digit can land on opposite sides of a
  quantization boundary as 64-bit doubles and on the same side as 32-bit floats.
  A fingerprint taken from Blender's in-memory doubles before export is not
  guaranteed to match one taken from the file afterwards. This was found by a
  test, not by reasoning: `0.1234565` and `0.1234575` quantize to `123457` and
  `123458` as doubles, and both to `123457` as floats.

A bone name carrying `|`, a newline or a carriage return is **refused**, not
escaped. Such a name could shift the fields so two different skeletons
canonicalize to the same text. Blender permits them and every engine target
discourages them, so a refusal is honest and identical in both languages,
where an escaping scheme is one more thing for each side to get wrong.

### The worked example both repositories assert

Two joints, supplied out of order, with a rotation that is not the identity and
a translation on a rounding boundary:

| name | parent | translation | rotation (x,y,z,w) | scale |
| --- | --- | --- | --- | --- |
| `Spine` | `Hips` | `0, 0.1234565, 0` | `0, 0, 0.3826834, 0.9238795` | `1, 1, 1` |
| `Hips` | *(none)* | `0, 0.95, 0` | `0, 0, 0, 1` | `1, 1, 1` |

canonicalizes to exactly this text, newline-terminated:

```text
rac-skeleton-v1
Hips||0,950000,0|0,0,0,1000000|1000000,1000000,1000000
Spine|Hips|0,123457,0|0,0,382683,923880|1000000,1000000,1000000
```

```text
18c20df3170c39e2b00a889d44b9f38c2b6309aae636ce1e091e82736058d589
```

Note `0.1234565` quantizing to `123457` rather than `123456`: that is the
halfway case where the two languages' defaults disagree, and it is in the vector
on purpose. The reference implementation is
`src/reference_asset_compiler/skeleton_fingerprint.py`, and
`tests/test_skeleton_fingerprint.py` asserts this hash. A consuming studio keeps
a test asserting the same string against the same skeleton; if the two ever
disagree, compare the canonical text rather than the hashes, because the text
says which field drifted.

## Versions

- The compiler version is recorded on every derivative a studio imports. An
  asset can always say which compiler made it.
- This contract is versioned with the compiler. A studio pins a version and
  reads the contract at that version.
- The fingerprint algorithm is versioned in its own prefix (`rac-skeleton-v1`).
  Changing the algorithm means a new prefix, not a silent change of meaning.

## Running the compiler from a studio

The installed wheel carries the ledger, gates, receipts, planner and adapter
registry. It does **not** carry the Blender stages, the PowerShell runners or
the pinned workflow bundles; `resources.py::checkout_root` is what distinguishes
the two, and it requires `workflows/geometry/` to be present.

So a studio depends on two things: the **pinned package** for contracts and
receipts, and a **configured checkout** for execution. This is the same
relationship a studio already has with Blender, Unreal and a ComfyUI root, and
it is discovered and reported the same way. With no checkout, a studio reports
the capability as unavailable and refuses the work with a reason. It never
half-runs a pipeline.

Long stages are queued work, never a request. Progress is reported from **stage
receipts landing on disk**, because the ledger stages are a known ordered list:
`stage 4 of 9 · retopology` is derivable and true. A percentage interpolated
against a guessed duration is not, and must not be shown.

## What this contract does not cover

- How a studio arranges scenes, directs objects, or reviews shots. Its business.
- Retargeting a clip between different skeletons. A fingerprint match is not
  retargeting, and this contract makes no retargeting promise.
- Motion generation quality. That a clip exists says nothing about whether it is
  worth using; that remains a human gate like every other.
  Authoring guidance and the optional exported standing-idle check are in
  [CHARACTER_ANIMATION.md](CHARACTER_ANIMATION.md). These do not automatically
  gate studio imports or convert technical playback into artistic acceptance.
- Any claim about an asset being finished. `production_ready` is the only field
  that speaks to that, and it is the compiler's to set.


## Browser scene candidates: placement, floors and quadrupeds (2026-09-22)

`profiles/skeletons/quadruped_cat.json` defines a standing domestic quadruped:
30 bones, distinct forelegs and hindlegs, jaw, ears and a four-joint tail. It
requires source-bound landmarks; biped guesses are refused. `run_rig_candidate.ps1`
accepts `-Profile quadruped_cat -Landmarks <json> -Backbone landmark`. GLB input
preserves PBR material in the native Blender authority. The FBX transport is
retained for existing gates. The quadruped suite tests ten poses, and missing
pose bones fail rather than yielding an empty success.

`quadruped_cat_browser` and `ue5_manny_browser` preserve their canonical bone,
parent and weight contracts with a 50,000-triangle budget explicitly for browser
scenes. They do not replace the canonical 20,000-triangle production profiles,
certify deformation quality or imply artistic approval.

Two Blender helpers support already acquired candidates, not AI acquisition:

```text
blender -b --factory-startup --python-exit-code 1 --python scripts/blender/normalize_browser_asset.py -- <source.blend-or.glb> <output.glb> <receipt.json> <height-metres>
blender -b --factory-startup --python-exit-code 1 --python scripts/blender/texture_planar_floor.py -- <room.blend-or.glb> <output.glb> <receipt.json> <conditioned-albedo.png> --tile-metres 3
```

Normalization anchors the floor and applies a uniform size; rigid props centre
their footprint, while rigs preserve their anatomical origin. Rig placement is
baked into the rest mesh and joints; topology, UVs, weights and materials remain.
Native `.blend` files are retained. Importer bone widgets are not asset geometry.
The floor pass changes only the material and UVs of explicitly selected low,
upward faces; it never generates geometry. Both helpers refuse overwrites and
write source/output hashes. Their receipts retain `human_approved: false` and
`production_grade: false` until actual review and the applicable gates.

For an assembled prop, `rac run-stage remesh ... --preserve-components` retains
separate substantive parts. `--smooth-iterations 0` skips Laplacian smoothing
for architecture. Mechanical topology/budget checks and visual review still apply.
