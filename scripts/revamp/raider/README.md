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

Example, from the repository root:

```bash
W=work/raider-revamp
"$B" -b --factory-startup --python scripts/revamp/raider/refine_labels.py -- $W/sources/raider-dense-acquired.glb $W/parts-v1/face-labels.npy $W/parts-v1/part-names.json $W/parts-v2
"$B" -b --factory-startup --python scripts/revamp/raider/build_parts.py -- $W/sources/raider-dense-acquired.glb $W/parts-v2/face-labels.npy $W/parts-v2/part-names.json $W/parts-v2
"$B" -b $W/parts-v2/raider-parts-v2.blend --python scripts/revamp/raider/fit_head.py -- $W/parts-v2
"$B" -b $W/parts-v2/raider-head-v1.blend --python scripts/revamp/raider/eyes_and_sheet.py -- $W/parts-v2
"$B" -b $W/parts-v2/raider-head-v1.blend --python scripts/revamp/raider/fix_eyes.py -- $W/parts-v2
```
