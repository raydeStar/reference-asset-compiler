# Finishing painted surfaces

Run `rac run-stage material-sweep` once the geometry, UVs, base colour and seam repair look right. This optional CPU stage is for a painted, embedded GLB. A material slot can contain several real materials: the Raider's cheek, brows, beard and jacket collar all share one slot. Give the finish their identities before asking it to shade them. No new image inference, geometry cuts or UV splits are required.

For a character that is still a rigged blend, the [final material pass](WORKFLOW_PLAYBOOK.md#final-material-pass-every-character) is the usual route: it also reads edge wear and crease grime from the geometry. Use this sweep when the asset is already a packaged GLB and its paint must not change. Use one or the other on a given revision.

## Use it on another asset

From this checkout with RAC and its Python dependencies installed:

```powershell
python scripts/material_sweep.py --init painted.glb assignments.json
# Edit assignments.json: give each slot a class, an ID map, or an explicit keep.
rac run-stage material-sweep --source painted.glb --textures assignments.json --output finish-v1.glb --report finish-v1.json
& $env:RAC_BLENDER -b --python-exit-code 1 -P scripts/blender/review_material_response.py -- painted.glb finish-v1.glb review-v1
```

Open `review-v1/Review.html`. Look at the edges where two finishes meet, then step the key light across the surface. Does a glint stop at the leather rim? Does the cloth hold its colour as the light moves? Is the skin highlight smaller on the nose than the cheek? Check the intended engine and lighting before promoting the result. A receipt confirms what was encoded, not how good it looks.

The initializer inventories real slot names, pins the source and profile, and marks every slot `keep` until assigned. The stage refuses an all-kept recipe. Use a new output and receipt for each iteration. If the installed `rac` predates this stage, install the checkout editable (`python -m pip install -e .`) or run `python -m reference_asset_compiler.cli` with `PYTHONPATH=src`. Paths for the ID maps and an optional custom `profile` are relative to the assignment file. The bake needs NumPy, SciPy and Pillow; the optional visual review needs Blender.

## Assigning a surface

In the generated manifest, a separate steel slot can be `{"class":"worn_steel","size":1024}`; an eye can be `{"class":"eye"}`; a custom glass shader can stay `{"keep":true}`. For a shared atlas, use an 8-bit grayscale or indexed palette square PNG in its existing UV layout:

```json
{
  "size": 1024,
  "mask": "torso-id.png",
  "mask_sha256": "<SHA-256 of PNG file bytes>",
  "labels": {"1": "canvas", "2": "worn_steel", "3": "worn_leather"}
}
```

Use literal integer pixel IDs (1, 2, 3), no blended brush edges, antialiasing or JPEG. Every occupied texel needs a declared class. Reuse an existing reviewed segmentation or project face labels into UV space; inspect that projection on the model, including its reverse side. The [Raider recipe and four actual maps](../examples/material-sweep/raider/raider.json) are a worked example. For an edited PNG or deliberately changed profile, update the appropriate SHA with `(Get-FileHash path/to/file -Algorithm SHA256).Hash.ToLowerInvariant()`. A different source GLB requires fresh assignments or a reviewed rebind; matching names alone are insufficient.

The [surface library](../profiles/materials/surface-response.json) provides dry canvas, trousers, two leathers, worn steel, tarnished metal, skin, facial highlights, lips, hair, eye, enamel and wet tissue. These are adjustable art-direction presets, not measured constants. To make wet leather or polished brass, copy the profile, add a named class, set the manifest's `profile` and `profile_sha256`, and review under the same lights. Keep materials with authored optical shaders if the simple model does not fit.

## What reaches the renderer

- Base colour and its factor, original AO binding, geometry, UVs, skinning, morphs and animations remain intact. Original embedded buffers remain byte-for-byte in the new GLB. The cost of keeping this provenance is a larger file.
- The response texture is linear data: green is perceptual roughness, blue is metalness, alpha is dielectric specular strength; red is neutral. The alpha is bound through [KHR_materials_specular](https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_materials_specular). A viewer that ignores the extension still sees roughness, metalness and normals, but loses the authored dielectric strength. Don't import the response as sRGB, use its alpha as transparency, or replace the source AO with its red channel.
- A second linear PNG holds the tangent-space normal. The bake retains class-weighted existing relief and adds class-specific detail in rest-mesh space; it fades detail when the UVs cannot resolve it. Smooth optical presets use scalar controls and keep any existing normal. Skin here is painted skin with a surface response; the stage does not invent subsurface scattering, eye layers, or a strand groom.
- For mapped slots use core, uncompressed triangles, normals, and usable untransformed UV0 within 0–1. Size is 32–4096 square. Use unique UV islands to retain independent detail. Overlapping islands share the same pixels: they cannot express different assignments, and rest-space grain for both sides cannot be guaranteed. Use a unique atlas first if that matters. Supplied tangents take precedence; otherwise the baker derives a frame from UV gradients and vertex normals. Existing normal and roughness images must be embedded core textures. Use `keep` for unsupported materials, unusual IORs or animated shader controls.
- Detail pitch is in millimetres. The default assumes one mesh-local unit is one metre. Set `meters_per_mesh_unit` per mapped slot if the mesh uses a different local scale; bake nonuniform scale first. Run this step **after** reduction, rebaking and delivery texture sizing. Do not downsize the result without rechecking the normal mips and packed alpha in the target renderer.

## Raider replay

For dry, weathered characters intended for Framewright Scene, initialize the
assignment with its optional target. The initializer writes both the target
name and the SHA-256 of the settings into the manifest.

```powershell
python scripts/material_sweep.py --init painted.glb assignments.json --target framewright-scene
```

For an asset that already has reviewed masks, copy its assignment and add the
two target fields from the initializer. The [Raider Framewright assignment](../examples/material-sweep/raider/raider-framewright.json)
reuses the original four PNG masks. The [Framewright target](../profiles/materials/framewright-scene.json)
specifies the effective bare-metal coverage and roughness of worn and tarnished
steel, glove leather roughness and specular strength, and the finish on the
forehead and nose. Its receipt pins the base and target profiles. Select this
finish to suit the asset and its lighting. Polished, clean metal needs a
different treatment.

In the reviewed Framewright build, Assets supplies studio reflections and
Scene uses an ambient light and a directional key. Open the exported model in
both views. In Scene check whether shaded steel retains its shape and the key
produces a localized highlight. Check leather and cloth at the same camera
angle. [Live comparison and settings](evidence/raider-framewright-20261103.json).

### Studio and Framewright examples

Use `work/raider-seams-20261103/delivery/Raider_Seam_Repair.glb` as the source and `examples/material-sweep/raider/raider.json` as the assignment. The [evidence](evidence/raider-material-sweep-20261103.json) records the identical rerun, preserved rig, class pixel checks and a second asset exercise. The actual before/after with close cameras and five key-light positions is in `work/raider-material-sweep-20261103/delivery/Review.html`. The GLB is the transport; the packed Blender derivative retains the original editable rig.

For the Framewright export, use the same source and substitute
`examples/material-sweep/raider/raider-framewright.json`. Open the local
Framewright project on port 5191, select Scene and open **Raider material review**.
**Raider - Weathered Steel** is the retained material-only comparison in the
library, with its captures in `work/raider-framewright-20261103/delivery/`.
The live scene now shows [the fitted outfit](RAIDER_SEAM_REPAIR.md#fitted-outfit-for-framewright).
If the paint reads correctly but a shine line crosses the middle of an object,
overlay the actual material IDs on the visible paint before changing roughness.

For concept-conditioned local repainting, UV coverage checks and lossless payload
cleanup, use the [registered reference repair loop](REFERENCE_PATCH.md). Its
November 5–6 Raider checkpoint retains the material sweep and adds isolated cuff,
skin and deformation repairs; actual-consumer approval of that revision is open.
