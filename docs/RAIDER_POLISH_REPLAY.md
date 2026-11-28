# Raider polish and replay

*Type: reference. Evidence date: 2026-11-06.*

The artist approved candidate04's appearance apart from exposed skin at the
collar. Candidate05 repairs that defect while preserving existing surfaces,
textures, skeleton, facial controls and held clip. Natural motion and cooked UE
remain separate gates.

## What improved the appearance

- Repair acquired surfaces where segmentation left raised borders and gaps.
- Project concept-conditioned front/side/back references onto the actual model
  to recover stitching, folds, grain and wear while retaining its silhouette.
- Allocate UV space where the cuff and pouch had insufficient texture detail.
- Give cloth, leather, steel and skin distinct roughness, metallic, specular and
  normal response, then inspect under consumer lighting.
- Correct local skin weights and check the garment in posed views.

RAC now includes a [recipe-driven finishing workflow](POLISH_WORKFLOW.md):
`rac polish-init` and `rac polish` coordinate inspection, acquired-face
restoration, UV/map transport, registered guides, explicit AI-reference handoffs,
mapping, material response, bounds and packed review. See also
[registered repairs](REFERENCE_PATCH.md) and [material sweep](MATERIAL_SWEEP.md).
Head/ear fitting and local weight corrections still include Raider-specific
decisions. The full upstream character is not an unattended image-to-hero stage.
Fresh AI generations can differ; repeatable mapping uses saved images and hashes.

## Demonstrated collar replay

From the repository root, use the existing Python environment with NumPy, SciPy,
Pillow and OpenCV. Choose a fresh output name; prior results are retained.

```powershell
rac polish examples/polish/raider-collar.json --output work/raider-polish-20261105/collar-replay-new --blender 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe'
```

The shared `restore-surface` stage restores 12 exact acquired triangles. It checks source/donor hashes,
matches vertices by position and UV, copies current normals and skin weights,
and verifies that the ten boundary edges become manifold. A separate 256px atlas
preserves approved maps. Shared `reference-patch` projects the frozen torso
reference onto that surface with cloth response.

Required inputs under `work/raider-polish-20261105/`:

| Input | Purpose |
|---|---|
| `framewright-review-20261106/Raider - Quality Candidate 04.glb` | Reviewed model with valid POSITION bounds |
| `candidate01/Raider_Refined.glb` | Acquired triangles removed by neck cleanup |
| `references/torso-front.png` | Registered concept-conditioned reference |
| `guides/torso-front.npz` | Visibility/depth guide |

The recipe binds the intermediate surface, reference and guide by SHA-256.
The earlier bespoke runs, `collar-repair01` and `collar-repair-replay01`, and
the final shared RAC runs, `rac-replay03` and `rac-replay04`, produced byte-identical GLBs:

`5136a551e09b2f94a498895b22b9c7fb5cd576767e80dc7640857539d8dea36f`

This demonstrates replay of this repair from frozen inputs. The full upstream
character has not been regenerated from scratch as one automated workflow.
The recipe adds eleven review images, including moving light and collar poses;
open `steps/review/Review.html` in its attempt directory. The packed review copy
does not replace the authored native master. `raider-cuff-repack.json` separately
exercises generic UV/map transport on a retained earlier model.
The [pipeline-port evidence](evidence/raider-polish-pipeline-20261106.json) records
the two fresh runs, unchanged completed files on resume, cuff geometry/rig
preservation and isolated installed-wheel verification.

## Current delivery and evidence

`work/raider-polish-20261105/review-candidate05/` contains the GLB, packed native
Blender file, pose/reopen receipts, import response, downloaded served GLB and
front/quarter Framewright screenshots. The native file reopens with 24 packed
images, 88 bones, 34 facial controls and 66,123 triangles.

The 100x100 close-up ray test found 50 exposed-skin samples inside the reported
gap before repair and zero after. The other 569 lower-neck skin hits are unchanged.
Static head-left/right and arms-raised views retain collar coverage. These are
bounded checks: shoulder/equipment behavior and neckline smoothing remain part
of broader deformation review, and this is not authored natural motion.

Framewright asset `50e09e9a-74a4-48ad-8c1e-1ccf8ef9f538` is **Raider - Quality
Candidate 05 - Collar Repair**. Served bytes match the replay hash. Front and
angled Assets Director Mode inspection passed with `Raider Relaxed Held` selected.
Prior assets and the saved scene remain unchanged. Scene-lighting comparison,
natural motion and cooked UE evidence are still separate gates.
