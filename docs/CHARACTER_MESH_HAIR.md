# Mesh hair from a scanned head

A stylised character's hair as sculpted mesh locks, cut from a generated head
scan, instead of a strand groom grown from parameters. The groom never
reproduced the reference's locks and read as fur in a painted world; the scan
already has them. On character-02 (2026-10-09) a Pixal3D single-view scan of
the head picture gave Arcane-like blade locks with their own painted colour
(near-black brown, caramel highlights); Hunyuan3D-2mv gave a mop of thin
tendrils, which as a mesh reads as dreadlocks.

Status: the stages below run end to end on the CPU in about 15 seconds. Wiring
the result into `rebuild_character.py` and the game install is the next step
(see the end).

## 1. Scan the head (GPU, about 2 to 4 minutes)

Use the head's front picture as a cut-out (the Hunyuan request's
`prepared/front.png` is one). Pixal3D needs about 20 GiB of free VRAM; from
Git Bash set `MSYS_NO_PATHCONV=1`.

```powershell
python scripts/generate_geometry.py $C-head-pixal3d <prepared/front.png> --seed 42 --resolution 1024
```

## 2. Conform the template to the scan (CPU, under a minute)

Pixal3D delivers figures facing +y: turn the arrays 180 degrees about z before
conforming (x and y negated), and pass the same `--yaw-deg 180` to step 3.

```powershell
& $B -b --factory-startup --python scripts/blender/export_mesh_arrays.py -- <scan.glb> $W/hair/scan.npz
py -3.12 -c "import numpy as np; z=dict(np.load('$W/hair/scan.npz')); z['verts'][:, :2] *= -1; np.savez('$W/hair/scan-r.npz', **z)"
& $B -b --factory-startup --python scripts/blender/render_mesh_view.py -- "<abs>\scan-r.npz" "<abs>\acq-front.png" "<abs>\acq-front-camera.json" --arrays
& $Torch scripts/detect_face_landmarks_dwpose.py $W/hair/acq-front.png $W/hair/dw-acq-front.json --model $DW
python scripts/conform_head_template.py $Ref/template/hm08-male.npz $W/hair/scan-r.npz $W/hair/conform.npz $W/hair/conform.json `
  --picture-landmarks $W/head/dw-front.json --template-landmarks $Ref/landmarks/dw-template-front.json `
  --template-camera $Ref/landmarks/template-front-camera.json `
  --acquisition-landmarks $W/hair/dw-acq-front.json --acquisition-camera $W/hair/acq-front-camera.json
```

## 3. Build the hair (CPU, about 15 seconds)

```powershell
py -3.12 scripts/build_mesh_hair.py --template $Ref/template/hm08-male.npz --scan <scan.glb> `
  --scan-conform $W/hair/conform.npz --scan-receipt $W/hair/conform.json `
  --head $W/head/finish/head.npz --out $W/hair/mesh --blender $B --yaw-deg 180 --triangles 60000
```

It runs, in order:

- `classify_scan_hair.py`: scan triangles outside the conformed skin, over the
  scalp or far out; never the ears, inside layers or the neck.
- `blender/cut_scan_hair.py`: those triangles, minus any the scan's texture
  paints as skin close to the skin (an ear scrap), welded, in template metres,
  with the scan's base colour.
- `transfer_mesh_hair.py`: carried onto the character's own head (`--head`),
  which is conformed from the same template: each vertex follows the skin
  under it. On character-02 the hair moved 17 mm (median) from the Pixal3D
  head onto his Hunyuan-built head. The same step puts one character's hair
  on another's head.
- `reduce_mesh_hair.py`: fast-simplification (MIT, optional dependency:
  `pip install fast-simplification`) to `--triangles`. It keeps the blades at
  60k where Blender's collapse decimator turned them into shards at 134k.
- `blender/bake_mesh_hair.py`: new UVs and a selected-to-active bake of the
  full-resolution colour and a tangent normal map. The cage reaches 15 mm; at
  4 mm most rays missed the thin blades.

Outputs: `hair-mesh.npz` (verts, tris, loop_uv in the head's template space),
`hair-mesh-basecolor.png`, `hair-mesh-normal.png`, and the receipt
`mesh-hair.json`. character-02: 830,860 triangles cut, 56,032 shipped.

Review: `render_painted_head.py` without `--strands` draws `hair-mesh.npz` as
a textured mesh (pass it as the hair NPZ, the base colour as the hair
texture).

## 4. Next: the build and the game

- `rebuild_character.py`, a recipe `hair: {"mode": "mesh"}`. Freeze
  `hair-mesh.npz` and its two maps as bundle inputs. Skip `grow_hair_groom.py`
  and both `export_groom_alembic.py` calls. Pass the hair mesh to
  `render_painted_head.py` (no `--strands`). Have `assemble_character.py` load
  its `hair` object. `bind_assembly_to_rig.py` already weights every mesh
  other than the body and head 100% to `head`, so the rig, the review poses and
  the UE5 FBX carry the hair unchanged.
- Game: the character JSON gets a mesh-hair material role (base colour, normal,
  two-sided) and skips the groom step.
- A dark scalp under the locks (the strand path's scalp cap) so skin does not
  show between them.
