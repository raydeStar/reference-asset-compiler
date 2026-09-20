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

Both implementations must agree on a checked-in fixture. The compiler writes the
fingerprint into its rig report; the consuming studio computes it independently
from the same GLB; both repositories keep a test asserting the same expected
hex string, including one value that lands exactly on a rounding boundary.

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
