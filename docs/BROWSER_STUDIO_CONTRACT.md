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

## The ten things a studio consumes

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
  source's open edges before collapsing. That invents surface the source never
  had and then measures the derivative against an original that does not
  contain it -- which is how a faithful reduction came back 128 mm out on a
  424 mm lantern.
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
- Any claim about an asset being finished. `production_ready` is the only field
  that speaks to that, and it is the compiler's to set.
