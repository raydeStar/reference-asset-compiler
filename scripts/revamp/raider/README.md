# Raider revamp scripts (prototype)

The scripts behind `docs/RAIDER_REVAMP.md`, kept so the stage can be rerun.
They are Raider-specific for now: head, collar, belt and knee landmarks are
measured values for CH-03 in the acquired mesh's normalised space (height
about 2, front is -Y). Generalising them into a RAC command is open work.

Inputs live in `work/raider-revamp/` (git-ignored). `$B` is Blender 5.2; the
SAM scripts run under the ComfyUI Python, which has `segment_anything`.

| Order | Script | Runs in | Does |
| --- | --- | --- | --- |
| 1 | `sam_auto.py`, `sam_parts.py`, `sam_fix.py`, `sam_straps*.py` | ComfyUI Python | 2D part map of the reference with Segment Anything ViT-B |
| 2 | `project_parts.py` | `$B -b --factory-startup` | Project the 2D map onto the dense acquired mesh; first labels |
| 3 | `refine_labels.py` | `$B -b --factory-startup` | Head and collar regrown along creases, belt round the back, pouches, knee pads, small islands |
| 4 | `build_parts.py` | `$B -b --factory-startup` | One part per label: cloth continues under overlays, overlays become thin shells, open edges skirted inward, each part reduced to its budget |
| 5 | `fit_head.py` | `$B -b <parts blend>` (needs MPFB 2) | MakeHuman head fitted to the acquired head, 34 expression shape keys, beard as a paint mask |
| 5b | `fit_head_v2.py` | `$B -b <parts blend>` | Tight fit after the face was rejected: skin snapped onto the acquired head except lids, lips, ears |
| 6 | `eyes_and_sheet.py`, `fix_eyes.py`, `expr.py` | `$B -b <head blend>` | Eyeballs, gate renders, expression renders |
| 7 | `face_preview.py` | `$B -b <head blend>` | Reference picture projected front-on as colour, to judge likeness |
| 8 | `head_crop.py`, `head_views.py` | ComfyUI Python; `$B -b --factory-startup` | Head crop of the reference, 4x Real-ESRGAN, for a head-only acquisition; clay views of the candidate |
| 9 | `head_paint_prep.py`, `obj_to_glb.py` | `$B -b --factory-startup` | Reduce and unwrap the accepted head for Hunyuan3D-Paint (`scripts/run_hy3d21_texture.ps1`); pack the painted OBJ and maps into a GLB for `render_turnaround.py` |
| 10 | `body_paint_prep.py`, `part_uv_mask.py`, `calibrate_pbr.py`, `place_head.py` | `$B -b <parts blend>`; plain Python for `calibrate_pbr.py` | Body paint mesh with one tight atlas; which part each painted face is, and the non-metal mask; metallic and roughness fixed on non-metal parts; painted head placed on the painted body |
| 11 | `hand_views.py`, `place_hands.py` | `$B -b <parts blend>` | Views of the hand-only acquisition; the painted hands, with their gauntlets and bare forearms, placed on both arms along each sleeve's centreline |
| 12 | `prep_production.py` | `$B -b --factory-startup` | One real-scale production mesh at the hero budget (seams welded before reduction) |
| 13 | `lengthen_forearms.py` | `$B -b --factory-startup` | Measures the forearm and hand spans of a production mesh (its earlier tube surgery is retired) |
| 14 | `wrap_face.py`, `bake_face.py`, `fix_neck_paint.py` | `$B -b <MakeHuman front blend>` (needs MPFB 2 and the CC0 system assets); ComfyUI Python for `fix_neck_paint.py` | MakeHuman's speaking face wrapped onto the painted head with CC0 eyes, teeth and tongue; its paint baked; the lower neck repainted |
| 15 | `attach_face.py`, `fix_shoulders.py`, `fix_mouth.py` | `$B -b <rigged blend>` | Face attached to the rigged body; shoulder weights repaired; rigid teeth and jaw |
| 16 | `final_renders.py`, `pose_sheet.py`, `face_rig_sheet.py`, `inspect_views.py`, `pose_closeups.py` | `$B -b <rigged blend>` | Review renders: four views, deformation poses, face shapes, loose-piece list |
| 17 | `speak_line.ps1`, `align_visemes.py`, `speak_demo.py` | Windows PowerShell; plain Python; `$B -b <rigged blend>` | A line spoken by Windows' built-in voice with its mouth shapes, aligned to the audio, and the speaking render |

## Rebuilding the rigged Raider

`build_raider.ps1` runs steps 11 to 17 (with the rig, skin and gate stages between them) from the accepted
inputs into `work/raider-revamp/build/<run>/`, and writes nothing outside that folder. Its help lists the
inputs. Steps 1 to 10 and the face bake (14) are recorded in `docs/RAIDER_REVAMP.md`; their outputs are the
inputs here.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\revamp\raider\build_raider.ps1 -Run v2
# resume from a stage when the earlier ones are already in the run folder
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\revamp\raider\build_raider.ps1 -Run v2 -From skin
```

Example, from the repository root:

```bash
W=work/raider-revamp
"$B" -b --factory-startup --python scripts/revamp/raider/refine_labels.py -- $W/sources/raider-dense-acquired.glb $W/parts-v1/face-labels.npy $W/parts-v1/part-names.json $W/parts-v2
"$B" -b --factory-startup --python scripts/revamp/raider/build_parts.py -- $W/sources/raider-dense-acquired.glb $W/parts-v2/face-labels.npy $W/parts-v2/part-names.json $W/parts-v2
"$B" -b $W/parts-v2/raider-parts-v2.blend --python scripts/revamp/raider/fit_head.py -- $W/parts-v2
"$B" -b $W/parts-v2/raider-head-v1.blend --python scripts/revamp/raider/eyes_and_sheet.py -- $W/parts-v2
"$B" -b $W/parts-v2/raider-head-v1.blend --python scripts/revamp/raider/fix_eyes.py -- $W/parts-v2
```
