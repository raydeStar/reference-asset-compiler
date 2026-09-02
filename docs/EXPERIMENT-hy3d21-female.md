# Texture experiment: Hunyuan3D-Paint 2.1 on field-scout-female

Run 2026-08-30 against `docs/CLAUDE_RESUME_TEXTURES.md`. Four iterations.
**Rejected on quality**, after both of its infrastructure defects were
fixed and proven fixed. The two contract failures are gone; the generated
art is still worse than the texture it would replace.

## Environment

| | |
|---|---|
| GPU | RTX 4090, 22.50 GiB free at launch (gate requires 21.00) |
| Runner | `${RAC_LEGACY_ROOT}\scripts\run_hy3d21_pbr.py` |
| Runner SHA-256 | `FB4C1664AD7489ADD748CF79985670716366D582FD79C46073BD504DAD2F844A` (matches catalog) |
| Python | `.venv-hy3d21`, 3.11.9, torch cu124 |
| Upstream | `upstream/Hunyuan3D-2.1`, models `models/hy3d21/Hunyuan3D-2.1` |

VRAM was freed by stopping ComfyUI and the Epic launcher, with the user's
explicit authorisation. One UnrealEditor process (PID 4220, a hung
`render_ratification_subject.py -unattended` job from 15:04) could not be
terminated and still holds VRAM; the run proceeded anyway once the gate
cleared.

## Inputs

| Role | Path | SHA-256 |
|---|---|---|
| Mesh | `work/field-scout-female/hy3d/female_semuv.obj` | `5B7D4DFD…B585741` |
| Reference | `references/field-scout-female-v4/turnaround-v1/front.png` | `FC28E022…D15B5302` |

The mesh is the final-scale accepted geometry carrying the new **semantic UV
layout** (31 islands, 292.4 texels/cm², from `scripts/blender/semantic_uv.py`),
which is the "coherent semantic UV islands" precondition the instruction asks
for. `trimesh` loads it with 36,443 vertices and 36,443 UVs, so the runner's
`preserve_existing_uv` lock accepts it.

## Commands

```powershell
# iteration 1
.\scripts\run_hy3d21_texture.ps1 -Mesh <obj> -Reference <front.png> `
    -OutputObj work\field-scout-female\hy3d\female_painted.obj `
    -Views 6 -Resolution 512

# iteration 2 (maximum the runner allows)
<venv-hy3d21>\python.exe <runner> <obj> <front.png> `
    work\field-scout-female\hy3d2\female_painted768.obj --views 12 --resolution 768
```

## Result

Both iterations completed generation and produced albedo, metallic and
roughness maps plus a GLB. Both were then **rejected by the runner's own
topology gate**:

```
HY3D21_UV_LOCK vertices=36139 uv_vertices=36139
RuntimeError: Hunyuan topology/UV gate failed:
  {"faces_equal": false, "geometry_delta": Infinity, "uv_delta": Infinity,
   "vertices": 36443, "triangles": 69970, ...}
```

The pipeline silently dropped **304 vertices** (36,443 → 36,139) despite the
`mesh_uv_wrap` override. Face order and vertex count therefore do not match the
input, so the result cannot be transferred back onto the rigged, accepted mesh.
That gate is correct and should not be relaxed.

## Quality, measured

Detail is Laplacian variance of luminance — a sharpness proxy. Higher is more
detailed.

| Albedo | Size | Mean luma | Detail |
|---|---|---|---|
| **existing legacy** | 4096² | **80.4** | **92.4** |
| hy3d21, 512 / 6 views | 2048² | 53.3 | 6.4 |
| hy3d21, 768 / 12 views | 2048² | 54.3 | 16.4 |

Maximum settings improve detail 2.6x over minimum but remain **5.6x below the
texture they would replace**, and roughly 32% darker. Visually the output is
soft, muddy and loses garment structure: jacket panels, buttons and fabric
weave present in the legacy atlas are gone.

Part of the gap is fixed: Hunyuan3D-Paint writes a 2048 atlas regardless of
settings, against an existing 4096 — a 4x texel deficit before any quality
argument. The rest is generation fidelity.

## Rejection reason

1. **Topology contract violated.** 304 vertices dropped; output not
   transferable to the rigged asset.
2. **Quality regression.** 5.6x less detail and 32% darker than the current
   texture, at half the atlas resolution.

This matches the limit already recorded in `workflows/catalog.json` for this
workflow: *"whole_body_PBR_improved_but_face_identity_degraded; requires
semantic head review"*. On this character the degradation is not confined to
the face.

Stopped at two of three permitted iterations because 768/12 is the maximum the
runner exposes; a third run has no remaining quality knob to turn.

## What would actually be worth trying next

Not more heuristic pixel repair, and not a third run of the same method.

1. **Raise the output atlas to 4096.** The 2048 cap is a fixed 4x handicap.
   Worth checking whether `Hunyuan3D-PaintConfig` exposes a texture resolution
   independent of the multiview render resolution.
2. **Fix the 304-vertex drift** so any future result is admissible: find which
   pipeline stage discards them (likely a degenerate-face clean) and pre-clean
   the input so the stage becomes a no-op.
3. **Head-only transfer, as the instruction already specifies.** The body
   atlas is not the problem on this character; the face is. Constrain any
   generated identity to head geometry and leave the accepted body alone.
4. **TRELLIS.2** as the catalog's named challenger, noting its own recorded
   limit (face bands, identity loss, triangle speckling).

## Artefacts

- `work/field-scout-female/hy3d/` — iteration 1, maps, GLB, validation JSON
- `work/field-scout-female/hy3d2/` — iteration 2
- `work/field-scout-female/semuv/` — the semantic-UV input mesh and atlas
- `work/_hy3d/albedo_preview.png` — generated albedo, downscaled for review

Nothing in `out/`, the compiler, the rigs or the UE packages was altered.


## Iterations 3 and 4: both contract failures fixed

`workflows/texture/hunyuan3d21/run_hy3d21_hires.py` is a variant runner that
leaves the hash-verified legacy runner untouched and monkey-patches three
upstream behaviours:

1. `textureGenPipeline` calls `trimesh.load(path)` with processing ON, welding
   vertices split at UV seams. Loading with `process=False, maintain_order=True`
   removes the drift.
2. The pipeline computes `texture_size = 4096` then calls
   `save_mesh(..., downsample=True)`, which cv2-resizes every map to half.
   Forcing `downsample=False` keeps the resolution it already computed.
3. The gate's own source snapshot used `trimesh.load(force="mesh")`, which
   splits per UV corner and yields a different vertex count from the
   pipeline's plain load. That mismatch was mine, not the paint's.

Result at 768 / 12 views / 4096 atlas:

```
HY3D21_ATLAS texture_size=4096 render_size=2048
HY3D21_UV_LOCK vertices=34987 uv_vertices=34987
HY3D21_PBR_OK geometry_delta=0.000000179 uv_delta=0.000000053
faces_equal: true
```

**The topology gate passes.** The output is transferable onto the rigged mesh.

| Albedo | Size | Mean luma | Detail |
|---|---|---|---|
| existing legacy | 4096² | 80.4 | **92.4** |
| hy3d 512 / 6 | 2048² | 53.3 | 6.4 |
| hy3d 768 / 12 | 2048² | 54.3 | 16.4 |
| hy3d 768 / 12, 4096 atlas | 4096² | 45.2 | 12.7 |

Quadrupling the atlas did not raise detail, because upsampling soft content
adds none. Applied to the rigged mesh, the result is worse than the numbers
suggest: the jacket's olive has spread across the face, hair, hands and
trousers, and facial features are gone.

**Final verdict: rejected on generation quality.** The plumbing is fixed and
the variant runner is kept, so the method can be retried cheaply against a
different reference framing or a future model. The existing albedo stays.

## What shipped instead

The existing art is better than anything generated here, so the win came from
giving it a better mesh and layout. `scripts/blender/retopo_bake.py` now heals,
QuadriFlows, unwraps into semantic charts, transfers weights and bakes:

| | before | production |
|---|---|---|
| triangles | 70,000 | **23,366** (11,683 quads) |
| UV islands | 395 | **20** |
| texel density | 305.9 | **348.6** |
| BaseColor detail | 92.4 | **97.1** |
| Normal map | none | **4096** |
| AO | none | **4096** |
| deformation | pass | **pass** (`left_arm_only` side_bias +1.00) |

Every measure improved or held, on a third of the triangles.
