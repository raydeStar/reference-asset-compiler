# Canonical character surface workflow

*Type: reference. Evidence date: 2026-11-06.*

This is the operating standard for finishing an acquired character in RAC. It
consolidates the Raider and Remora work: diagnose the actual defect, preserve
approved parts, repair registered paint, assign material response, inspect the
export in its consumer, and replay the accepted inputs. Use
[POLISH_WORKFLOW.md](POLISH_WORKFLOW.md) for CLI/schema details and
[PIPELINE.md](PIPELINE.md) for the separate approval contracts.

The workflow produces review candidates, not an automatic AAA-quality verdict.
An attractive render does not establish topology, deformation, animation or
cooked-runtime acceptance. Previously delegated visual review remains delegated
within its stated scope; do not ask again merely because the next candidate is new.

## Route the job

| Situation | Route |
|---|---|
| No acquired geometry | Approved concept must first condition an AI geometry or mapping stage. Follow the acquisition route in the playbook. |
| Existing acquired geometry needs a new full PBR texture set | Hunyuan3D-Paint 2.1 through `scripts/run_hy3d21_texture.ps1`; check live GPU ownership and launcher thresholds first. |
| A few seams, misplaced details, exposed paint ghosts or a weak component | `rac polish-init` / `rac polish`: registered concept-conditioned references and bounded projection. CPU mapping/review; the image tool is an explicit AI handoff. |
| Base colour is right, response to light is wrong | `material-sweep` with reviewed semantic classes/masks and a versioned response profile. Keep authored optical materials when necessary. |
| Large hair shape is wrong | Separately acquired head-supported hair, reviewed connected extraction, thin-shell repair before reduction, and rebake. See [CHARACTER_MESH_HAIR.md](CHARACTER_MESH_HAIR.md). |

The core compile/package path consumes authorities. Optional polish stages
create new derivatives; they do not silently repaint a compiled authority.
Do not route a local cloth repair through a fresh whole-character generation.

## 1. Freeze the authority and diagnose the cause

Read the current STATUS entry and preserve the source GLB/native file, concept,
hashes, material settings, fixed cameras and consumer view. Choose one visible
gate. Keep rejected candidates and state why they were rejected. Never overwrite
the accepted source, reset a dirty checkout, or close creative applications.

Inspect the exact exported candidate in:

- Unlit base colour, to separate painted lines/shadows from lighting.
- Clay, normals and wireframe, to locate real holes, overlaps, faceting or lifts.
- Object/component/material IDs, to identify which surface owns a defect.
- The intended pose and actual consumer, including underside and grazing angles.

| Symptom | Evidence and repair |
|---|---|
| Raised border around a segmented part | Compare with the acquired surface. SAM labels do not justify extruding an already modeled strap or hem again. Keep labels on the continuous acquired surface; real separate parts need backing and clearance. |
| A line disappears in clay | Repair paint/response. Do not cut or smooth sound geometry to erase a painted line. |
| A gap is present in clay | Repair the acquired surface first, retaining correspondence and geometry lineage. Paint cannot close a hole. |
| White floating pieces after a hair replacement | Identify connected components/materials before deleting anything. Remora's pieces belonged to the old body acquisition, not the new hair. |
| Marks remain after removing pieces | **Mandatory exposed-surface check:** inspect paint and normal response beneath removed/replaced geometry. Old hair outlines, occlusion shadows and pale strips survive deletion. Reconstruct that cloth/skin through a registered AI patch. |
| Shine cuts across the middle of an object | Overlay material IDs against visible paint before adjusting roughness. A wrong semantic mask makes even good settings wrong. |
| Chin/mouth protrusion | Check active morph weights and pose before editing anatomy. Remora's teeth/tongue had every expression at 1. |

Fix topology/UV allocation before the final paint pass. Declare a character tier;
maximum triangles is a ceiling, never a reduction target. Reducing a painted mesh
requires rebaking and appearance review. Check unique UV occupancy and overlap,
not only summed triangle area. More texture pixels cannot rescue collapsed or
overlapping islands. Use `repack-surface` where supported; retain rig/morph transport.

## 2. Capture registered views of the current mesh

`capture-reference` supplies colour, clay and deterministic hit/depth/barycentric
guides. Bind the source GLB, mesh, explicit material subset, camera center, axis,
width and resolution. Use opposing views when the region wraps around a limb or
ear. Retain all guides with their hashes.

Capture cameras and patch bounds use **mesh-local coordinates**. Review closeups
use the exported model's world coordinates. Node transforms and other meshes are
not included in capture; an excluded eye, hair or mouth mesh does not occlude the
guide. Check those limitations before trusting visibility at a silhouette.

## 3. Make an AI reference that can actually map back

Give the image tool three clearly named roles:

1. Exact current colour guide: camera, framing and surrounding palette.
2. Exact clay guide: surface contours and modeled feature positions.
3. Approved concept: identity, costume construction, stylization and detail.

Ask for diffuse paint with the same framing and silhouette, no new illumination,
cast shadows, hard catchlights, accessories or anatomy. Name the region to change
and the features to preserve. For an exposed-surface repair, explicitly remove
the old object's painted outline **and its shadow**, not just its white fill.
Retain the exact prompt, tool/provider (do not invent an unavailable model ID),
input/output hashes, rejected images and review reason.

Review registration before projection: eyes, nostrils, mouth, brow scar, collar,
stitches, lacing and silhouette must align with the mesh. A beautiful portrait
with displaced features is an unusable texture donor. Do not stamp an entire
concept portrait onto a different head. Keep a hair-acquisition donor's face out
of the character's identity transfer.

`rac polish` can pause at `ai-reference` with exit 3. Supply the hash-bound
response and resume. The runner does not itself invoke a provider. New AI images
are new candidates; reproducibility begins with the retained accepted output.

## 4. Project the smallest sufficient repair

Use `reference-patch` with explicit material names, bounds, feathering, registered
visibility guides and atlas size. Preserve approved features through scope;
include enough space to fade into continuous cloth without erasing real seams.
Prefer separate nose bridge/underside or ear views to one broad projection that
paints the wrong side. Inspect the reverse side after every repair.

Set `retain_normal` and `relief_m` deliberately. Remove obsolete relief inside
an exposed cloth repair rather than preserving the old hair's bump. Do not
derive deep relief from a painted dark line. The projector re-encodes the selected
material's colour/response/normal atlases and normalizes their scalar factors;
it is not a promise that every selected-material image byte is unchanged.
Unselected materials and all geometry/rig/morph/animation data must remain intact.

The optional foreground chroma guard is a **skin-specific, reviewed setting**.
It prevented pale background bleed at Remora's nose. Applying that threshold to
ivory cloth would discard the very surface being repaired. No universal chroma
threshold, cheek rectangle, ear mask or component ID belongs in a generic preset.

## 5. Finish materials by identity

Use the [material sweep](MATERIAL_SWEEP.md) after geometry, UVs, map resolution and
base colour are settled. A single atlas may contain skin, cloth, leather and
metal. Supply reviewed integer ID masks, including the reverse side; do not make
the entire body uniformly shiny because it shares a slot.

The existing surface library and `dry-worn-character` / `framewright-scene`
profiles are adjustable art-direction presets. Preserve the exact profile hash
and any consumer-specific override in the recipe. They are not measured physical
constants or a universal skin shader.

- Keep base colour in its proper colour space. Response and normals are linear.
- RAC response green = roughness, blue = metalness, alpha = dielectric specular
  strength via `KHR_materials_specular`. Alpha is not opacity; red is not source AO.
- Check relief at delivery resolution and under moving light. Reduce or disable
  an inherited noisy normal map when it damages the actual consumer result.
- Skin needs restrained tonal variation and highlight response. Strong noisy
  normals plus uniform colour can read as wood/plastic. This route does not
  invent subsurface scattering or layered eyes.
- Eyes need aligned apertures, restrained geometry and diffuse iris references;
  painted catchlights plus live specular can double the apparent highlight.
- Bare eyeballs read as a doll. Once the eyes are aligned, run
  [`eye-detail`](EYE_DETAIL.md) for lid-margin lashes (pick `pronounced`, `subtle`
  or `none` per character) and the lid shadow over the eyeball.

Verify the **exported GLB**, including scalar factors and extension bindings.
A Blender node adjustment that does not survive glTF export is not a fix.

## 6. Review the transport and the consumer

Run `prune-payload`, `repair-bounds` and `polish-review`. Keep the four body views,
moving-light views and defect-specific closeups. A character review should cover
front/quarter/profile/back, eyes, nostrils and underside of jaw, both ears, hair
back/scalp coverage, collar/armholes, clothing joins and all newly exposed areas.
Use the intended held pose and appropriate joint probes if a rig is present.

Save, pack, reopen and verify actual `packed_file` image data. The imported review
`.blend` is a transport inspection copy; it does not replace the native authored
rig/rest-frame authority. Check geometry/UV/morph/skin preservation and compare
unselected material payloads with the source, not just filenames or counts.

Import the exact candidate into Framewright. Record asset ID, content hash,
viewer mode/build where available, camera/light context and screenshots. Orbit
the model; do not infer a side-view pass from a front render. Inspector lighting
and a saved Scene are different review conditions. Neither proves cooked UE
runtime quality. A localhost HTTP 200 proves none of these visual gates.

If a material needs adjustment, put the actual exported setting back into a
versioned recipe/profile, build a new candidate, and review again. Do not leave
the only fix in a transient viewer control. Preserve the previous candidate.

## 7. Replay and hand off honestly

Run to a fresh output directory from the frozen source, retained AI images and
exact settings. Compare final GLB hashes where deterministic. Record bounded
differences explicitly when a renderer/baker is not byte deterministic. A changed
recipe, code or dependency needs a new attempt; failed runs are retained, not
silently retried. Update STATUS, append HANDOFF, and add surprising failures to
DECISIONS. Carry input/code/environment hashes and commands with the evidence.

| Proven reusable part | Retained example and limit |
|---|---|
| Surface diagnosis, UV/map transport, registered projection, PBR response, review | `rac polish-init` / `rac polish`; [example recipes](../examples/polish/README.md). Semantic selections and reference quality still need judgment. |
| Acquired collar restoration and paint | `raider-collar.json`; frozen Candidate05 replay is byte-identical. |
| Clay-conditioned ear repaint | `raider-ears.json`; source already contains the reviewed acquired-ear fairing. |
| Head-supported braided hair extraction/repair/reduction/rebake | `remora-braided-knot.json` with `scripts/replay_acquired_hair.py`; mesh/base colour replay exact, three normal pixels differ by 1/255 in the retained check, and that normal map is disabled in the consumer. Extraction and assembly remain reviewed decisions. |
| Remora face/collar/neutral-mouth repair | Local `work/remora-airship-20261106/replay65/replay.py`; `replay66/receipt.json` proves the final GLB exact. Its component IDs, jaw bounds and facial masks are asset-specific, not a generic facial-repair stage. |
| Exposed tunic paint after old hair removal | `remora-tunic-ghosts.json`; registered cloth-only region, retained AI guide, four views/closeups/light sweep. Source face/eyes/hair are protected. See the current STATUS/evidence for replay and consumer acceptance. |

Large binaries, AI references and local asset-specific helpers are retained in
the asset workspace and are not distributed with a fresh clone. Missing inputs
must fail hash checks. Do not replace a missing file while retaining its old hash.

## Starting another character or a new region

```powershell
python -m pip install -e ".[polish]"
$env:RAC_BLENDER = 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe'
rac polish-init work/character/acquired.glb --output work/character/tunic.json --concept work/character/concept.png --mesh Body --material Tunic --provenance 'Approved concept conditioned the retained acquisition receipt' --surface-class canvas
rac polish work/character/tunic.json --output work/character/tunic01
# At awaiting_reference, review the request and supply real AI outputs/response.
rac polish work/character/tunic.json --output work/character/tunic01 --resume
```

Use actual material/mesh names; inspect the generated cameras, scope and profile.
Add `--repack` only when UV diagnosis calls for it. To replay Remora's retained
tunic repair instead, use `examples/polish/remora-tunic-ghosts.json` and a fresh
output directory. No new inference is needed for that replay. The tailor may be
mysterious; the recipe must not be.
