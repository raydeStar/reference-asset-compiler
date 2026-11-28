# Repeatable surface finishing

*Type: reference. Evidence date: 2026-11-06.*

`rac polish-init` creates a finishing recipe for an acquired material region.
`rac polish` runs its registered stages, retains each result, pauses at an explicit
AI-reference request, and resumes after the returned images are bound by hash.
The output is a review candidate. It does not approve a ledger gate.

Follow [CHARACTER_SURFACE_WORKFLOW.md](CHARACTER_SURFACE_WORKFLOW.md) for the
canonical artistic/technical sequence and the Raider/Remora lessons. This document
is the command, schema and retention reference.

This packages the repeatable parts of the Raider and Remora work: surface diagnosis,
acquired-face restoration, UV repacking, reference capture and projection,
material response, export bounds, and a packed review with fixed cameras.
The Raider collar recipe reproduces the delivered Candidate05 GLB byte for byte.
This is not a claim that the entire character can be regenerated from one image
without artistic decisions.

## Start a new region

Install from a RAC checkout into the intended Python environment:

```powershell
python -m pip install -e ".[polish]"
$env:RAC_BLENDER = 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe'
rac polish-init work/my-character/acquired.glb --output work/my-character/polish.json --concept work/my-character/concept.png --mesh Body --material Coat --provenance 'Approved concept conditioned the recorded geometry acquisition' --surface-class canvas --repack
rac polish work/my-character/polish.json --output work/my-character/finish01
```

Use the actual mesh/material names. The initializer selects one primitive; it
refuses ambiguous names. Review the recipe's cameras, material class and scope
before running. Omit `--repack` when the existing UV allocation is sufficient.
Repacking transports existing paint; it cannot invent missing detail.

For a character with a reviewed clip, add `--clip EXACT_GLTF_CLIP_NAME` at init.
Without a clip, the review uses the bind pose. Use
`--response-profile profiles/materials/dry-worn-character.json` for the retained
Raider-derived dry finish, or use the standard response profile with
`--response-target framewright-scene`. That target binds the standard profile's
hash; it is not silently applied to a different profile.

The installed CLI still needs the registered scripts in a checkout. Supply
`--repo-root C:/path/to/reference-asset-compiler` when running elsewhere.
Python 3.11+ is required. The optional `polish` dependencies include OpenCV and
the pinned `xatlas==0.0.9`. The review uses Blender/Cycles on CPU. No GPU inference
is started by either command.

## What runs automatically

| Stage | Behavior and boundary |
|---|---|
| `inspect-surface` | Reports material response, texture density estimates, degenerate faces and position-welded boundaries. Mesh summaries join material splits. Open boundaries can be intentional; the report does not automatically call them defects. UV area is summed triangle area, not unique occupancy. |
| `repair-bounds` | Computes finite POSITION min/max while preserving every binary payload byte. Initializer recipes run it before and after finishing. This does not retrofit unrelated legacy exporters. |
| `restore-surface` | Restores explicitly selected triangles from a hash-bound acquired donor, with coincident position/UV correspondence, region bounds, boundary-count and winding checks. Copies current skin data and position/normal morphs. It does not synthesize replacement anatomy or infer which hole to close. |
| `repack-surface` | Isolates one primitive's atlas, rebakes supported maps, and transports normal maps between tangent frames. Preserves per-triangle geometry, weights and position/normal morphs. Leaves other primitives/materials unchanged. |
| `capture-reference` | Produces registered color/clay PNGs and deterministic depth/triangle/barycentric NPZ guides. Cameras are in the selected mesh's local coordinates; other meshes, node transforms and posed occlusion are not included. |
| `ai-reference` | Writes a concept-bound editing request, then pauses. A human or an AI-equipped agent supplies the images and response receipt. |
| `reference-patch` | Projects saved registered images into scoped material regions, with visibility guidance and declared normal relief/response. See [reference mapping](REFERENCE_PATCH.md). |
| `material-sweep` | Applies explicit material classes and optional masks to metallic, roughness, specular and normal response. Unselected materials remain marked `keep`. See [material sweep](MATERIAL_SWEEP.md). |
| `eye-detail` | Appends lid-margin lash cards (`pronounced`/`subtle`/`none`) and an eye-occlusion shell that follow the head morphs. Append-only. See [eye detail](EYE_DETAIL.md). |
| `prune-payload` | Removes unreachable replaced payload without re-encoding retained images or geometry. |
| `polish-review` | Renders front/quarter/side/back, three key-light positions, optional closeups and explicit bone-rotation cases. Saves and reopens a packed GLB-import review `.blend`. |

UV repacking supports embedded GLB triangles with normals and untiled UV0, core
PBR textures and the supported specular/IOR/emissive-strength/unlit extensions.
Additional UV sets, texture transforms, unsupported material extensions and
tangent morphs require another transport route and are refused. Very small
positive-area faces collapsed by xatlas are isolated into valid tiny charts only
when they total at most 0.01% of surface area and number at most 128. Substantial
collapse or zero-area geometry stops the stage. No faces are deleted to obtain a
passing result. Normal transport without authored tangents derives the source
frame from UV derivatives; inspect the result in the actual consumer.

The review `.blend` is a packed transport inspection copy. Preserve the original
authored native file as skeleton/rest-frame authority. Diagnostic poses are
bounded probes, not natural motion or game deformation acceptance.

For a mesh that combines opaque skin with transparent eyes or mouth surfaces,
`capture-reference` accepts an explicit `materials` list in its config, for
example `"materials": ["FACE_skin", "Raider repaired ear"]`. Names must exist
on the selected mesh. The receipt lists selected and omitted materials; omitted
surfaces do not occlude the guide. Without this explicit subset, transparent
primitives still stop capture. Review whether excluded surfaces could hide the
region being painted before using the resulting visibility guide.

## The AI handoff

An intentional wait returns exit code **3** with `status: awaiting_reference`.
The request is at `finish01/steps/references/request.json`. It includes the actual
concept, guide paths/hashes, instructions and output filenames. Give the image
editing agent the concept and registered color/clay views; preserving camera
registration and silhouette is essential.

Write `response.json` beside the request. The returned state includes a template;
replace all placeholders with actual provider/model, paths and SHA-256 values:

```json
{
  "schema": "reference-asset-compiler.ai-reference-response.v1",
  "request_sha256": "SHA256_OF_REQUEST_JSON",
  "provider": "actual image provider and model",
  "files": {
    "front.png": {"path": "front.png", "sha256": "SHA256_OF_FRONT"},
    "back.png": {"path": "back.png", "sha256": "SHA256_OF_BACK"},
    "left.png": {"path": "left.png", "sha256": "SHA256_OF_LEFT"},
    "right.png": {"path": "right.png", "sha256": "SHA256_OF_RIGHT"}
  }
}
```

The filenames must exactly match the request. Relative paths are resolved beside
`response.json`. Each image must be a valid 16..8192px PNG. Record actual AI use;
the runner validates provenance bindings, not the truth or quality of the provider
claim. For an automatic integration, an agent reads this request, uses its approved
image tool, writes the response, then executes:

```powershell
rac polish work/my-character/polish.json --output work/my-character/finish01 --resume
```

Completed stages are hash-checked and reused. The images are retained locally.
For later deterministic replays, reference those retained images directly with
`{"path":"...","sha256":"..."}` bindings in `reference-patch`, as in the collar
example. New AI generations are new candidates, not deterministic replays.

## Recipes and retention

The root schema is `reference-asset-compiler.polish-recipe.v1` and requires a
source `{path, sha256}`, `acquisition_provenance`, and ordered unique step IDs.
Each step names a registered stage and, when needed, its stage-specific `config`.
External config files use `{path, sha256}`. Completed stage artifacts use
`{"step":"guides","file":"views/front.npz"}`. The runner resolves these and
binds each stage to its current upstream GLB automatically.

Every attempt contains a frozen recipe, used inputs, stage configs/receipts/logs,
artifact hashes, and `state.json`. Recipe/code/dependency changes require a fresh
attempt; mid-run code changes stop the run. Blender executable hash is retained
when a review is requested. Rendering can vary across Blender builds/platforms;
binary model replay is the stronger demonstrated invariant here.

Exit code **0** means `ready_for_review`; **2** reports a rejected/failed run.
An existing directory is never silently overwritten. Failed or interrupted
attempts are retained and cannot be automatically retried with `--resume`.
Investigate their receipts, change the cause, and choose a new attempt directory.
Completed artifacts that have changed also block resume.

Final `state.json` names the GLB candidate and its hash. When a review step is
present, open `steps/review/Review.html`. Copy/import that exact GLB into
Framewright for the consumer-lighting review. The runner does not replace catalog
assets or scenes. Carry approved scalar/material changes back into a versioned
profile or patch recipe, retain its hash, and replay to a fresh candidate.

## Demonstrated cases and remaining decisions

See [example recipes](../examples/polish/README.md) and
[Raider replay](RAIDER_POLISH_REPLAY.md). The real collar run preserves the
Candidate05 GLB hash; the real cuff run exercises an earlier acquired primitive,
including normal transport and tiny-chart isolation. Neither replaces the
approved Framewright asset. Unit/integration tests also exercise the full
guide -> wait -> response -> projection -> material-finish path using explicitly
synthetic images; that proves orchestration, not new AI quality.

Still asset-specific: choosing good AI results, identifying semantic material
regions, deciding whether a border is intentional, selecting donor faces,
substantial anatomy repair, ear/head fitting, weight correction and natural
motion. Those choices can be retained as recipe inputs as they become stable.
The initializer processes one region at a time so approved surfaces can remain
intact. Full scene lighting, human visual acceptance, engine deformation and
cooked-runtime gates remain separate. Every polish run keeps
`production_ready: false` and leaves the ledger untouched.
