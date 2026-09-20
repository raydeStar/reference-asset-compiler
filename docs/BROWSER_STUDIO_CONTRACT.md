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

## The four things a studio consumes

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
- Textures embedded. A lighter derivative may accompany it (see
  `apps/lakeside-village/README.md` for the `.web.glb` precedent: reduced
  textures, every non-image buffer byte preserved, both hashes recorded).

The payload's SHA-256 is what a studio stores. Content addresses the asset;
names do not.

A studio runs it by name, never by path:

```
rac run-stage --list                     # what can run here, and what is missing
rac run-stage browser-payload --source <staged.fbx>     --output <payload.glb> --report <receipt.json> [--repo-root ...] [--blender ...]
```

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
