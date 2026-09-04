# One image to a compiled prop

For the direct Hunyuan, non-Codex route, start here:

```powershell
python scripts\crank_from_image.py my-crate D:\art\crate.png `
    --kind static_prop --height 0.6 `
    --height-reason "Waist height on the 2 m cohort; pelvis measures 0.91 m."
```

It creates the workspace and a hash-bound single-view request, runs Hunyuan
directly, and resumes until the next human visual gate. The older
`compile_from_image.py` route documented below remains the Pixal3D import and
reproduction path; it is not the default user-facing launcher.

The image must enter the geometry generator as conditioning data. This route
does not permit an agent to inspect the image and manually or procedurally
recreate an approximation in Blender. Blender work starts after AI acquisition
and is limited to downstream cleanup, topology, UV/bake, rigging, and evidence.

```powershell
python scripts\compile_from_image.py my-crate D:\art\crate.png `
    --height 0.6 `
    --height-reason "Waist height on the 2 m cohort; pelvis measures 0.91 m."
```

That runs the chain the routing plan already described and nothing performed:

```text
image
  -> rac new              intake: copy, hash, route
  -> generate_geometry    a candidate mesh, from the image
  -> describe_mesh        measure it, unpack its embedded textures
  -> compile_from_image   write recipes/<asset>.json
  -> compile_prop         join, scale, rename, publish the authority
  -> voxel QEM            only when over budget; immutable reduced candidate
  -> fixed views          human modeling approval of the reduced geometry
  -> [ PAUSE ]            modeling approval, by a person
  -> build_production     unwrap prebuilt low, bake dense appearance, gate
  -> promote_production   out/<asset>-production/
```

Every stage after the recipe is the one that already existed, unchanged. The new
route now also inserts an explicit source-hash-bound reduction candidate when
the normalized authority exceeds its budget. Assets already under budget bypass
reduction rather than being needlessly voxelized.

## What it will not do

**It will not substitute a hand-built approximation for AI acquisition.** If
image-conditioned geometry is rejected or generation cannot run, the route
records that state and stops. A cleaner mesh authored by eye is still the wrong
lineage and cannot pass the modeling gate. `--candidate` therefore requires a
sidecar AI-lineage report (or `--candidate-report`) whose geometry-adapter,
candidate hash, and approved-image hash all validate before Blender is invoked.

**It will not invent a scale.** A photograph carries no size — the same chair
image is a doll's chair or a throne. `--height` is required and `--height-reason`
is recorded in the recipe beside it, because every other scale in this repository
carries the measurement that justified it. The office chair's came from putting
its seat top on `field-scout-male`'s knee at 0.489 m.

**It will not call the result approved.** It stops after publishing the authority
so a person can look at fixed views, which is where the routing plan puts
`modeling_approval`. The reviewer must promote the exact candidate plus neutral
front, three-quarter, side, and back views into the hash-audited workspace
ledger. `--yes` only continues noninteractively after that record exists; it
cannot create or bypass approval.

The same boundary exists after UV/bake. Automated coverage, density, and map
checks advance the mechanical stages, then the route pauses at
`texture_approval`. Publishing requires the exact production FBX, baked maps,
gate reports, and lit front, three-quarter, side, and back views in the
hash-audited ledger with an identified human reviewer.

Publishing advances only the declared collision policy and local static-payload
validation. Unreal import is a separate gate. The editor-side verifier records
the SHA-256 of the production manifest it actually consumed; then
`scripts/record_ue5_import.py <asset>` extracts that asset from the mutable batch
report into immutable per-asset evidence before advancing `ue5_import`.

Runtime and cook remain distinct. `scripts/record_runtime_review.py` requires
the production asset to be present in the saved gallery plus an identified
human review of a non-empty editor frame. `scripts/record_cook_evidence.py`
then requires a later clean cook, successful package, packaged executable and
content containers, a packaged run log that loaded the gallery, and a reviewed
non-empty in-game frame. Only that final command can make the workspace audit
report `production_ready: true`.

**It will not compile a character.** A generated humanoid needs the complete
`rig_and_skin` route. Auto-Rig Pro 3.74.40 is installed and its required
operators are operational in Blender 5.2.1. A portable existing-mesh A-pose
candidate driver now exists, but its first retained canary proved that hands
need explicit reviewed landmarks; deformation, ARP game export, Manny FBX, and
UE gates are still separate unfinished work.
AniGen is not a substitute: it regenerates geometry with its rig instead of
skinning the topology that passed approval. A mesh that arrives with an
armature is refused by name rather than compiled into something that is not a
character.

## Before it runs

The generator refuses rather than dying. Pixal3D at 1024 wants most of a 24 GB
card even with `low_vram`, so the driver checks free VRAM first, names the
processes holding it, and stops:

```text
[GEN] free VRAM 5341 MiB, this route wants 20000
[GEN] REFUSED: not enough free VRAM. Held by:
       UnrealEditor.exe  [size needs elevation]
       python.exe  [size needs elevation]
```

An out-of-memory kill half an hour in is indistinguishable from a crash in the
log, and this project does not silently retry crashed inference. `--candidate`
skips generation entirely and compiles a mesh you already have.

## What a raw generation costs

Running the chain against a real Pixal3D chair found two things, and the second
one had been hiding since the first prop.

**QuadriFlow will not reduce a raw generation.** 979,546 triangles, refused
whole-mesh and again shell by shell, 0 quads either way. The mesh falls through
to passthrough at full density. The legacy chair pipeline never hit this because
it reduced 980k to 48k *before* the compiler ever saw it; a one-image flow has no
such step, and adding one is real outstanding work. Decimate is not the answer —
that is a recorded rejection.

**Re-unwrapping it was actively wrong.** The prop route re-unwrapped
unconditionally, which was right for `office-chair` — six materials each tiling
0.55 to 14.6 times the UV square is not a layout to preserve — and wrong here. A
generation arrives as one material on a sane 0.58-of-the-square layout, and
re-unwrapping that soup gave **17 texels/cm² against a source holding 324**. The
texture gate rejected it, correctly, for a layout the stage had just thrown away.
That is the same trap already recorded for characters, arrived at from the other
direction.

The rule now: a kept-geometry prop re-unwraps only when its incoming layout
cannot be kept — materials piled past the UV square, or more than one material
sharing it. `unwrap_reason` is recorded in the report either way.

## The budget gate props never had

With the layout kept, the generated chair passed every remaining check at
**971,442 triangles against a declared budget of 20,000**. Nothing complained,
because the triangle budget is enforced inside `gate_rig` — and the prop route
skips the rig gate, which removed the budget along with the skeleton.

It is checked directly now, with the same waiver rule the rig gate uses: over
budget fails unless the profile records a `tri_budget_waiver` naming a reason and
an approver.

This means the honest current state of a one-image prop is:

| | |
|---|---|
| Generation | works, given a free GPU |
| Recipe drafting | works |
| Authority intake | works |
| Compile and bake | works |
| Texture gate | passes |
| **Triangle budget** | **fails — a raw generation is ~50x over** |

So the chain is complete and the asset is honestly rejected at the end of it.
Closing that gap needs a reduction step between generation and the compiler, and
that is the next real piece of work rather than something to wave through with a
waiver.

An isolated AutoRemesher challenger now exists at
`scripts/run_autoremesher_reduction.ps1`. It targets below the triangle budget,
hashes the dense authority, refuses overwrite, and gates triangle count, quad
fraction, and finite coordinates. It is not the default until a fixed-view A/B
and dense-to-runtime texture bake pass; earlier character evidence shows that
AutoRemesher can either produce a useful clean shell or visibly melt identity.
The first raw-chair canary was rejected without retry: 979,546 source triangles
became 372,317 triangles rather than the requested sub-20k result, only 31.5% of
polygons were quads, and the output retained roughly 156k boundary/non-manifold
edges. AutoRemesher is therefore not the missing default reduction step for this
fragmented Pixal3D output.

The actual legacy reduction lineage was then reproduced more precisely. The
accepted 48,000-triangle chair did not come from a successful QuadriFlow pass:
the old driver voxel-conditioned the raw soup, QuadriFlow cancelled, and an
explicit collapse-QEM fallback produced the all-triangle output. Direct raw
decimation remains rejected; voxel-conditioned QEM is a different operation on
a coherent closed surface.

That route now exists explicitly at `scripts/run_voxel_qem_reduction.ps1` with
no hidden fallback. A retained raw-longsword canary reduced 977,341 triangles to
18,000, with zero boundary or non-manifold edges. Front, three-quarter, side,
and back clay views preserve the accepted 48k silhouette at 512 px; compact
hashes and the bounded agent review are in
`docs/evidence/reduction-voxel-qem-longsword-v1.json`. It is the preferred
reduction challenger, but not yet the default: human modeling approval,
dense-to-runtime UV/texture baking, UE import, collision, and cooked-runtime
evidence remain outstanding.

The separate voxel-to-QuadriFlow reproducer remains diagnostic only. Blender
5.2.1 cancelled on conditioned chair and longsword surfaces even after the
evidence report proved zero boundary and non-manifold edges and forced outward
normals. Those failures were retained without retries.

## Correction

`docs/PROPS.md` records a repeatability test on a 48,000-triangle generated mesh
that "compiled clean, gates passed". That was true when it ran and is no longer
the whole story: at 44,302 output triangles it is over the same 20,000 budget and
would now require a waiver. What the test actually proved — that the route is not
specific to the office chair, and the three bugs it found — is unaffected.
