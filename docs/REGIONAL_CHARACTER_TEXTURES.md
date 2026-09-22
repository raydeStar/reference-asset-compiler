# Regional character textures

*Type: reference*

For close-up repair of an existing rigged humanoid, preserve the native geometry
and rig, replace only UVs/materials, and give the head, exposed arms/hands and
clothing independent sheets. This is an operator workflow, not a new default
for every generated asset or a claim of production readiness.
The native stages are exercised with Blender 5.2.2 and its Minimum Stretch
unwrapper; the painter continues to use its separate pinned environment.

## Supported authority and preservation

`scripts/blender/semantic_character_uv.py` accepts one triangular, textured
mesh in a native BLEND, with an armature and the supported Manny-style bone
group vocabulary. Shape keys, missing UVs, incompatible group names, collapsed
proxy faces and nonmanifold proxy edges are refused. A fingerprint protects
vertex order, positions, faces, weights, bone rest transforms, object transform
and modifiers. The old UV layer remains in the native derivative.

Only a temporary exact-position proxy is welded. The authoritative skinned
mesh is never welded or remeshed. Region boundaries and back seams guide the
unwrap. Measured failed folds receive bounded local projection; increased
fragmentation, collapsed UVs and sampled overlap above 0.1% of occupied atlas
pixels refuse the candidate. The sample is 1024 square, not a mathematical
proof that every subpixel overlap is absent.

```powershell
& $blender -b --factory-startup --python-exit-code 1 `
  --python scripts/blender/semantic_character_uv.py -- `
  source.blend work/character/uv-001 --head-from 0.84
```

The output includes `uv-authority.blend`, `uv-report.json`, `layout.npz` and
separate `head.obj`, `skin.obj`, `clothing.obj` paint transports. Head/clothing
use 4096 sheets; exposed skin uses 2048. OBJ export shares exact position/UV
pairs while retaining true UV splits. A separate `vt` for every triangle corner
would turn a continuous surface into disconnected triangles in Trimesh.

An optional clothing challenger uses xatlas already installed in the painter
environment; it performs no inference. It preserves triangle/corner order and
is validated against authority coordinates when imported:

```powershell
& $paintPython scripts/reunwrap_region.py `
  work/character/uv-001/clothing.obj work/character/clothing-uv.npz --max-chart-cost 8
& $blender -b --factory-startup --python-exit-code 1 `
  --python scripts/blender/semantic_character_uv.py -- `
  source.blend work/character/uv-002 --head-from 0.84 `
  --clothing-uv work/character/clothing-uv.npz
```

Do not select by island count alone. Inspect atlas occupancy, overlaps,
distortion, paint alignment and fixed views. Deep folds in generated clothing
can still require hundreds of charts even when the head has two.

## Paint and transfer

Use source-locked head and clothing reference crops, preserve their crop boxes
and hashes, and serialize GPU passes through the guarded launcher. For organic
characters, `-SmoothConditioningNormals` opts into vertex-normal conditioning.
The studio runner calculates those normals across exact-position UV splits;
the UVs and geometry it delivers remain unchanged. Props retain face-normal
conditioning by default. Both runner and normal helper are hash-pinned.

```powershell
./scripts/run_hy3d21_texture.ps1 `
  -Mesh work/character/uv-002/head.obj -Reference reference-head.png `
  -OutputObj work/character/head-attempt001/head.obj `
  -RunnerKind studio -Atlas 4096 -Views 12 -Resolution 768 `
  -SmoothConditioningNormals -LegacyRoot $env:RAC_LEGACY_ROOT
```

`-Views` limits the painter's selected views; it is not a claim that exactly
that many were rendered. On the 24 GB workstation, the clothing pass completed
with `-Views 6 -Resolution 768 -Atlas 4096`. The 12-view clothing attempt
allocated substantial shared GPU memory and made no output after 16 minutes;
its explicitly stopped attempt and the fresh six-view replacement are retained.
Reduce view count before sacrificing the final atlas resolution. A successful
geometry/UV receipt followed by a native teardown crash is still a failed
process exit: preserve it and independently reload/render any proposed maps.

After validating each paint's geometry/UV receipt, pin the chosen PNG paths and
hashes in a JSON config. `layout_report_sha256` pins the target `uv-report.json`.
`maps` is keyed by `head`, `skin` or `clothing`, then `BaseColor`, `Roughness`,
`Metallic`; each leaf contains `path` and `sha256`. Omitted channels are baked
from the original embedded material. If a painter ran against another regional
report, verify that region's OBJ hash is identical before binding its maps.

```powershell
& $blender -b --factory-startup --python-exit-code 1 `
  --python scripts/blender/bake_character_regions.py -- `
  work/character/uv-002/uv-report.json work/character/paint-final-001 `
  --paint-config work/character/paint-config.json --smooth-uv-seams `
  --name character-regional
```

The transfer uses CPU emission baking, independent material images and explicit
UV source nodes. It resets boosted specular settings, floors head/skin roughness
at 0.55 and makes them dielectric. Clothing retains its painted metallic mask
and a 0.35 roughness floor. These are conservative character defaults, unsuitable
for a metallic helmet without a separate material policy.

The head override blends over the original paint within 1% of character
height above the cut. Head/neck bone weights also protect vest and shirt faces
that happen to sit above that horizontal plane. A crop boundary is not a
wardrobe boundary; omitting this protection painted the innkeeper's vest tops
white in the first combined review.

The clothing override fades to the original paint over a surface distance of
2.5% of character height near another atlas. Distances cross exact-position UV
splits and follow the clothing mesh. This protects rolled-cuff and collar joins
from a hard triangle boundary between independent paints; it does not blur the
whole garment or move its vertices.

`--smooth-uv-seams` transfers shading normals from an exact-position proxy,
keeping folds over 75 degrees sharp. It changes normals, not geometry or rig.
The native derivative retains both UV layers; the browser GLB exports just the
new set. Maps remain PNG at their declared resolutions. Three materials and
larger textures cost more GPU memory and draw calls than a one-sheet background
character, so reserve this route for assets that need close-up inspection.

Review both albedo and lit front, three-quarter, side and back views. Check the
actual exported GLB's triangle/weight correspondence, joint order, rest
transforms and inverse bind matrices, plus deformation and browser loading.
Larger maps do not add geometry, repair fingers, or guarantee good paint.
